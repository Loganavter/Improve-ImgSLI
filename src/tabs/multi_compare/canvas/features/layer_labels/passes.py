"""QRhi render pass for the layer_labels feature.

Rasterizes per-layer filename labels into their own overlay texture and
draws them through the shared textured engine shell
(``engine.overlay.TexturedOverlayShell``). No GPU allocation, no bespoke
pipeline builders, no draw-recorder calls here -- those live in the
shell; this pass only declares its binding, resolves per-frame raster
bytes through a ctx-first resolver, and stages them.

DPR behavior is unchanged from the retired mirror (R0): the labels
source is source-owned -- ``LabelsOverlaySource.paint`` sizes everything
from ``framebuffer_size`` -- so no ``painter.scale(dpr)`` here (unlike
the drag overlay, which scales). Do NOT unify DPR handling across passes.
"""

from __future__ import annotations

import logging
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
from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

logger = logging.getLogger("ImproveImgSLI")


def _shader_dir() -> Path:
    # Mirrors the retired ``scene.resources.load_shader`` location: the
    # shared multi_compare QRhi shader dir holding overlay.vert/frag.qsb.
    return Path(__file__).resolve().parents[3] / "shaders" / "qrhi"


BINDING = TexturedOverlayBinding(
    shader_dir=_shader_dir(),
    shader_stem="overlay",
)

# Single source instance shared by the class seam (should_paint) and the
# ctx-first raster resolver below. LabelsOverlaySource is stateless (pure
# geometry + style from the composition), so one instance serves both.
_SOURCE = LabelsOverlaySource()


def _raster_image(ctx) -> QImage | None:
    """Rasterize the layer labels for ``ctx`` into a premultiplied image."""
    composition = ctx.composition
    if not _SOURCE.should_paint(composition):
        return None
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
    _SOURCE.paint(
        painter,
        composition=composition,
        scale=ctx.scale,
        offset=ctx.offset,
        framebuffer_size=ctx.framebuffer_size,
    )
    painter.end()
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
    img = _raster_image(ctx)
    if img is None or img.isNull():
        return None
    return _image_to_frame(img)


def _frame_resolver() -> TexturedOverlayResolver:
    """Resolver factory: the raster arrives via ``ctx``, nothing is captured."""
    return resolve


class LayerLabelsPass(CanvasRenderPass):
    """Rasterizes per-layer filename labels into their own overlay texture."""

    stack_role = CanvasStackRole.HUD_LABEL

    def __init__(self) -> None:
        self._shell = TexturedOverlayShell()
        self._source = _SOURCE

    def should_paint(self, ctx) -> bool:
        return self._source.should_paint(ctx.composition)

    def _raster(self, widget, ctx) -> QImage | None:
        return _raster_image(ctx)

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
        # callers stay silent).
        if frame_context is not None:
            _gate = self.should_paint(ctx)
            _count = 1 if self._shell.active else 0
            frame_context.record(
                "overlay.labels",
                "ran" if _gate else "skipped",
                f"overlay.labels items={_count}",
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

    def release(self) -> None:
        self._shell.teardown()


RENDER_PASSES: list[CanvasRenderPass] = [LayerLabelsPass()]
RENDER_PASSES = RENDER_PASSES
