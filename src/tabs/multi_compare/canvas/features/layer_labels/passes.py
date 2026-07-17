"""QRhi render pass for the layer_labels feature."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from tabs.multi_compare.canvas.rhi_overlay_pass_base import FullscreenOverlayTexturePass
from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole


class LayerLabelsPass(FullscreenOverlayTexturePass):
    """Rasterizes per-layer filename labels into their own overlay texture."""

    stack_role = CanvasStackRole.HUD_LABEL

    def __init__(self) -> None:
        super().__init__()
        self._source = LabelsOverlaySource()

    def should_paint(self, ctx) -> bool:
        return self._source.should_paint(ctx.composition)

    def _raster(self, widget, ctx) -> QImage | None:
        composition = ctx.composition
        if not self._source.should_paint(composition):
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
        self._source.paint(
            painter,
            composition=composition,
            scale=ctx.scale,
            offset=ctx.offset,
            framebuffer_size=ctx.framebuffer_size,
        )
        painter.end()
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


RENDER_PASSES: list[FullscreenOverlayTexturePass] = [LayerLabelsPass()]
RENDER_PASSES = RENDER_PASSES
