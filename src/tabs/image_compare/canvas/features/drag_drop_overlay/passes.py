"""QRhi render pass for the drag_drop_overlay feature (image_compare, canvas-only)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from tabs.image_compare.canvas.rhi_overlay_pass_base import FullscreenOverlayTexturePass
from tabs.image_compare.canvas.features.drag_drop_overlay.render.overlay import (
    paint_drag_drop_overlay,
    should_paint_drag_overlay,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole


class DragDropOverlayPass(FullscreenOverlayTexturePass):
    """Rasterizes live drag/drop affordances into their own overlay texture.

    Live-only, interaction-driven — uses ``TRANSIENT_PREVIEW`` stacking.
    Does not require ``SceneVisibility.INTERACTIVE``; ``should_paint`` gates
    on ``runtime_state._drag_overlay_visible`` which is set by
    ``canvas/interaction.set_drag_overlay_state``. Must remain visible even
    when ``blank_white`` (no images) so drop hints show on empty canvas.
    """

    stack_role = CanvasStackRole.TRANSIENT_PREVIEW
    # Must paint even when no images are loaded (empty canvas drop hint)
    requires_content = False

    def should_paint(self, ctx) -> bool:
        widget = getattr(ctx, "widget", None)
        if widget is None:
            widget = getattr(ctx, "viewport", None)
            # fallback: try widget attribute directly
            if widget is None:
                return False
        # ctx may be RenderRuntimeContext; widget is inside it as well
        w = getattr(ctx, "widget", None)
        if w is None:
            # image_compare's ctx is RenderRuntimeContext with widget inside feature_overlay
            w = getattr(getattr(ctx, "feature_overlay", None), "widget", None)
        if w is None:
            # last fallback: use the widget passed via should_paint's ctx.widget
            w = widget
        # Direct check on runtime_state
        state = getattr(w, "runtime_state", None) if w is not None else None
        if state is not None:
            return bool(getattr(state, "_drag_overlay_visible", False))
        # Fallback to helper
        return should_paint_drag_overlay(w) if w is not None else False

    def _raster(self, widget, ctx) -> QImage | None:
        # Resolve actual widget: prepare passes widget as first arg
        w = widget
        if w is None:
            w = getattr(ctx, "widget", None)
        if w is None:
            w = getattr(getattr(ctx, "feature_overlay", None), "widget", None)
        if w is None:
            return None
        state = getattr(w, "runtime_state", None)
        if state is None or not bool(getattr(state, "_drag_overlay_visible", False)):
            return None

        # Framebuffer size: prefer ctx.framebuffer_size else ctx.width/height * DPR
        fb = getattr(ctx, "framebuffer_size", None)
        if fb is None:
            width = int(getattr(ctx, "width", 0) or getattr(w, "width", lambda: 0)() or 800)
            height = int(getattr(ctx, "height", 0) or getattr(w, "height", lambda: 0)() or 600)
            # Account for DPR later via painter.scale
            fb_w, fb_h = width, height
            # Use devicePixelRatio to get framebuffer pixels
            try:
                dpr = float(w.devicePixelRatioF())
            except Exception:
                dpr = 1.0
            fb_w = int(max(1, round(fb_w * dpr)))
            fb_h = int(max(1, round(fb_h * dpr)))
        else:
            fb_w, fb_h = fb

        horizontal = bool(getattr(state, "_drag_overlay_horizontal", False))
        texts = getattr(state, "_drag_overlay_texts", ("", ""))
        text1 = texts[0] if len(texts) > 0 else ""
        text2 = texts[1] if len(texts) > 1 else ""

        img = QImage(max(1, int(fb_w)), max(1, int(fb_h)), QImage.Format.Format_RGBA8888_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        try:
            dpr = float(w.devicePixelRatioF())
        except Exception:
            dpr = 1.0
        dpr = max(1.0, dpr)
        painter.save()
        painter.scale(dpr, dpr)
        paint_drag_drop_overlay(painter, w, horizontal, text1, text2)
        painter.restore()
        painter.end()
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


RENDER_PASSES: list[FullscreenOverlayTexturePass] = [DragDropOverlayPass()]
RENDER_PASSES = RENDER_PASSES
