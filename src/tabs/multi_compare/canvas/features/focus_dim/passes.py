"""QRhi render pass: dim the canvas area outside a focused slot's image.

When a slot is focused (single-click, see drag_drop_overlay's
end_slot_press), ``composition_builder`` collapses the tree to just that
slot's ``LayerNode`` -- its own image aspect ratio becomes the composition's
native canvas size, so the image fills the composition canvas exactly (no
internal letterboxing). The only bars left are the canvas-vs-framebuffer
ones (``ctx.offset``/``ctx.scale`` in ``build_render_context``), i.e. the
"sides of the image" on the canvas itself -- this pass paints translucent
black over exactly those bars.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter

from tabs.multi_compare.canvas.rhi_overlay_pass_base import FullscreenOverlayTexturePass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

DIM_COLOR = QColor(0, 0, 0, 235)


class FocusDimPass(FullscreenOverlayTexturePass):
    stack_role = CanvasStackRole.HUD_LABEL

    def should_paint(self, ctx) -> bool:
        widget = ctx.widget
        state = getattr(widget, "state", None)
        return bool(
            state is not None
            and getattr(state, "is_focused", False)
            and ctx.composition is not None
        )

    def _raster(self, widget, ctx) -> QImage | None:
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


RENDER_PASSES: list[FullscreenOverlayTexturePass] = [FocusDimPass()]
