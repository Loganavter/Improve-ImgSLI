"""QRhi render pass for the drag_drop_overlay feature.

Rasterizes live drag/drop affordances into their own overlay texture and
draws them through the shared textured engine shell
(``engine.overlay.TexturedOverlayShell``). No GPU allocation, no bespoke
pipeline builders, no draw-recorder calls here -- those live in the
shell; this pass only declares its binding, resolves per-frame raster
bytes through a ctx-first resolver, and stages them.

DPR behavior is unchanged from the retired mirror (R0): the painter is
scaled by the host DPR before ``DragDropOverlaySource.paint`` (unlike
labels, which are source-owned). Do NOT unify DPR handling across passes.

Live-only, interaction-driven — uses ``TRANSIENT_PREVIEW`` stacking (B1: the
drop hint is chrome, not scene content, so it sorts with the HUD). Does *not*
set
``visibility = SceneVisibility.INTERACTIVE``: ``MultiCompareRenderContext``
carries no render-mode signal (no ``render_metrics``/``render_intent``),
so ``iter_active_render_passes``' visibility resolver always defaults to
``PREVIEW`` here — an ``INTERACTIVE``-only flag would silently disable
this pass permanently, including during real drags. `should_paint`'s own
`state.drag_active` check already gates this correctly (only true during
an actual interactive drag), so the default `SceneVisibility.ALL` is
correct and sufficient.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPainter

from engine.overlay import (
    TexturedOverlayBinding,
    TexturedOverlayResolver,
    TexturedOverlayShell,
)
from engine.frame.context import make_ids
from tabs.multi_compare.debug import mc_dnd_debug, mc_dnd_debug_enabled
from tabs.multi_compare.scene.passes.drag_overlay import DragDropOverlaySource
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _shader_dir() -> Path:
    # Mirrors the retired ``scene.resources.load_shader`` location: the
    # shared multi_compare QRhi shader dir holding overlay.vert/frag.qsb.
    return Path(__file__).resolve().parents[3] / "shaders" / "qrhi"


BINDING = TexturedOverlayBinding(
    shader_dir=_shader_dir(),
    shader_stem="overlay",
)

# Single source instance shared by the class seam and the ctx-first
# raster resolver below. DragDropOverlaySource carries edge-triggered
# debug state (last logged paint/skip signature), so the resolver and
# the pass must share one instance -- exactly as the retired mirror did
# with its per-pass ``self._source`` (RENDER_PASSES holds one pass).
_SOURCE = DragDropOverlaySource()


def _resolve_host(widget, ctx):
    """Resolve the canvas host from the prepare arg or the frame context."""
    w = widget
    if w is None:
        w = getattr(ctx, "widget", None)
    return w


def _raster_image(host, ctx) -> QImage | None:
    """Rasterize the drag affordances for ``host`` into a premultiplied image."""
    state = host.state
    if not _SOURCE.should_paint(ctx.composition, state):
        if getattr(host, "_dbg_was_active", False):
            host._dbg_was_active = False
            _SOURCE.reset_debug_state()
            if mc_dnd_debug_enabled():
                mc_dnd_debug(
                    "overlay HIDDEN (drag_active=%s presents=%s)",
                    state.drag_active,
                    getattr(host, "_rhi_presents_completed", "?"),
                )
        return None
    host._dbg_was_active = True
    t0 = time.monotonic()
    fb_w, fb_h = ctx.framebuffer_size
    img = QImage(
        max(1, int(fb_w)),
        max(1, int(fb_h)),
        QImage.Format.Format_RGBA8888_Premultiplied,
    )
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    dpr = max(1.0, float(host.devicePixelRatioF()))
    painter.save()
    painter.scale(dpr, dpr)
    _SOURCE.paint(painter, host=host)
    painter.restore()
    painter.end()
    raster_ms = (time.monotonic() - t0) * 1000.0
    facc = getattr(host, "_dnd_frame_stats", None)
    if isinstance(facc, dict):
        facc["frames"] += 1
        facc["raster_ms"] += raster_ms
    return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


def _image_to_frame(img: QImage) -> tuple[int, int, bytes] | None:
    """Convert a premultiplied host image to shell bytes (tab-side seam).

    The engine takes bytes, never host images: this snapshot owns its
    copy, so the shell can wrap it for the synchronous upload call
    without holding any host image type.
    """
    width, height = int(img.width()), int(img.height())
    if width <= 0 or height <= 0:
        return None
    stride = width * 4
    try:
        raw = bytes(img.constBits())
    except Exception:
        return None
    bytes_per_line = int(img.bytesPerLine())
    if bytes_per_line == stride:
        pixels = raw[: stride * height]
    else:
        pixels = b"".join(
            raw[y * bytes_per_line : y * bytes_per_line + stride] for y in range(height)
        )
    if len(pixels) != stride * height:
        return None
    return (width, height, pixels)


def resolve(ctx: Any) -> tuple[int, int, bytes] | None:
    """Ctx-first raster resolver: ctx in, framebuffer bytes out (or None)."""
    host = _resolve_host(None, ctx)
    if host is None:
        return None
    img = _raster_image(host, ctx)
    if img is None or img.isNull():
        return None
    return _image_to_frame(img)


def _frame_resolver() -> TexturedOverlayResolver:
    """Resolver factory: the raster arrives via ``ctx``, nothing is captured."""
    return resolve


class DragDropOverlayPass(CanvasRenderPass):
    """Rasterizes live drag/drop affordances into their own overlay texture."""

    stack_role = CanvasStackRole.TRANSIENT_PREVIEW
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = TexturedOverlayShell()
        self._source = _SOURCE
        self._dbg_recorded = False

    def should_paint(self, ctx) -> bool:
        if ctx.widget is None:
            return False
        return self._source.should_paint(ctx.composition, ctx.widget.state)

    def _raster(self, widget, ctx) -> QImage | None:
        host = _resolve_host(widget, ctx)
        if host is None:
            return None
        return _raster_image(host, ctx)

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

    def prepare(self, widget, ctx, resource_updates, frame_context=None) -> None:
        self._shell.stage_quad(resource_updates)
        self._shell.stage_clip(resource_updates, ctx.clip_matrix)
        frame = _frame_resolver()(ctx)
        try:
            rt = widget.renderTarget() if widget is not None else None
        except Exception:
            rt = None
        self._shell.upload_frame(resource_updates, rt, frame)
        if getattr(widget, "_mc_overlay_debug", False):
            if frame is None:
                logger.info(
                    "[mc-overlay-debug] %s.prepare: no overlay image (None=%s)",
                    type(self).__name__,
                    True,
                )
            else:
                logger.info(
                    "[mc-overlay-debug] %s.prepare: uploaded texture size=%s active=%s",
                    type(self).__name__,
                    QSize(frame[0], frame[1]),
                    self._shell.active,
                )

    def record(self, command_buffer, widget, ctx, frame_context=None) -> None:
        # Frame bus: overlay fact (record only, never instead). Verdict
        # from this pass's own should_paint gate; None-safe (unwired
        # callers stay silent). Existing mc_dnd_debug logic below stays.
        if frame_context is not None:
            _gate = self.should_paint(ctx)
            _count = 1 if self._shell.active else 0
            frame_context.record(
                "overlay.drag",
                "ran" if _gate else "skipped",
                f"overlay.drag items={_count}",
                ids=make_ids(frame_context.frame_id, _count),
            )
        if getattr(widget, "_mc_overlay_debug", False):
            logger.info(
                "[mc-overlay-debug] %s.record: active=%s pipeline=%s",
                type(self).__name__,
                self._shell.active,
                self._shell.pipeline is not None,
            )
        fb_w, fb_h = ctx.framebuffer_size
        self._shell.draw(command_buffer, width=float(fb_w), height=float(fb_h))
        # COMMIT = the quad was actually written into this frame's command
        # buffer (raster + texture upload in prepare, then draw here).
        # RASTER without COMMIT means the pass produced an image that never
        # reached the framebuffer (culled pass / missing pipeline).
        if not mc_dnd_debug_enabled():
            self._dbg_recorded = bool(self._shell.active and self._shell.pipeline is not None)
            return
        recorded = bool(self._shell.active and self._shell.pipeline is not None)
        if recorded == self._dbg_recorded:
            return
        self._dbg_recorded = recorded
        state = widget.state if widget is not None else None
        if recorded:
            mc_dnd_debug(
                "overlay COMMIT path=%s side=%s presents=%s (quad recorded, awaiting present)",
                getattr(state, "drag_target_path", None),
                getattr(state, "drag_target_side", None),
                getattr(widget, "_rhi_presents_completed", "?"),
            )
        else:
            mc_dnd_debug(
                "overlay quad NOT recorded (active=%s pipeline=%s) — "
                "rasterized but not drawn",
                self._shell.active,
                self._shell.pipeline is not None,
            )

    def release(self) -> None:
        self._shell.teardown()


RENDER_PASSES: list[CanvasRenderPass] = [DragDropOverlayPass()]
RENDER_PASSES = RENDER_PASSES
