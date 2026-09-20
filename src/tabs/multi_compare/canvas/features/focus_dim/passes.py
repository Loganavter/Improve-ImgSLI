"""QRhi render pass: dim the canvas area outside a focused slot's image.

When a slot is focused (single-click, see drag_drop_overlay's
end_slot_press), ``composition_builder`` collapses the tree to just that
slot's ``LayerNode`` -- its own image aspect ratio becomes the composition's
native canvas size, so the image fills the composition canvas exactly (no
internal letterboxing). The only bars left are the canvas-vs-framebuffer
ones (``ctx.offset``/``ctx.scale`` in ``build_render_context``), i.e. the
"sides of the image" on the canvas itself -- this pass paints translucent
black over exactly those bars.

Draws through the shared textured engine shell
(``engine.overlay.TexturedOverlayShell``). No GPU allocation, no bespoke
pipeline builders, no draw-recorder calls here -- those live in the
shell; this pass only declares its binding, resolves per-frame raster
bytes through a ctx-first resolver, and stages them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from engine.overlay import (
    TexturedOverlayBinding,
    TexturedOverlayResolver,
    TexturedOverlayShell,
)
from engine.frame.context import make_ids
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

logger = logging.getLogger("ImproveImgSLI")

DIM_COLOR = QColor(0, 0, 0, 235)


def _shader_dir() -> Path:
    # Mirrors the retired ``scene.resources.load_shader`` location: the
    # shared multi_compare QRhi shader dir holding overlay.vert/frag.qsb.
    return Path(__file__).resolve().parents[3] / "shaders" / "qrhi"


BINDING = TexturedOverlayBinding(
    shader_dir=_shader_dir(),
    shader_stem="overlay",
)


def _raster_image(ctx) -> QImage | None:
    """Rasterize the focus-dim bars for ``ctx`` into a premultiplied image."""
    fb_w, fb_h = ctx.framebuffer_size
    fb_w, fb_h = max(1, int(fb_w)), max(1, int(fb_h))
    img = QImage(fb_w, fb_h, QImage.Format.Format_RGBA8888_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)

    ox, oy = ctx.offset
    comp = ctx.composition
    image_w = max(1, int(comp.canvas_w)) * ctx.scale
    image_h = max(1, int(comp.canvas_h)) * ctx.scale
    top = max(0, int(round(oy)))
    bottom = min(fb_h, int(round(oy + image_h)))
    left = max(0, int(round(ox)))
    right = min(fb_w, int(round(ox + image_w)))

    painter = QPainter(img)
    try:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(DIM_COLOR)
        if top > 0:
            painter.drawRect(0, 0, fb_w, top)
        if bottom < fb_h:
            painter.drawRect(0, bottom, fb_w, fb_h - bottom)
        if left > 0:
            painter.drawRect(0, top, left, bottom - top)
        if right < fb_w:
            painter.drawRect(right, top, fb_w - right, bottom - top)
    finally:
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


class FocusDimPass(CanvasRenderPass):
    stack_role = CanvasStackRole.HUD_LABEL

    def __init__(self) -> None:
        self._shell = TexturedOverlayShell()

    def should_paint(self, ctx) -> bool:
        widget = ctx.widget
        state = getattr(widget, "state", None)
        return bool(
            state is not None
            and getattr(state, "is_focused", False)
            and ctx.composition is not None
        )

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
                "overlay.focus_dim",
                "ran" if _gate else "skipped",
                f"overlay.focus_dim items={_count}",
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


RENDER_PASSES: list[CanvasRenderPass] = [FocusDimPass()]
