"""QRhi render pass for the layer_labels feature."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from tabs.multi_compare.canvas.rhi_overlay_pass_base import FullscreenOverlayTexturePass
from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

logger = logging.getLogger("ImproveImgSLI")


class LayerLabelsPass(FullscreenOverlayTexturePass):
    """Rasterizes per-layer filename labels into their own overlay texture."""

    stack_role = CanvasStackRole.HUD_LABEL

    def __init__(self) -> None:
        super().__init__()
        self._source = LabelsOverlaySource()

    def should_paint(self, ctx) -> bool:
        composition = ctx.composition
        result = self._source.should_paint(composition)
        if getattr(ctx.widget, "_mc_overlay_debug", False):
            labels = (
                [
                    (layer.layer_id, None if layer.label is None else layer.label.text)
                    for layer in composition.layers
                ]
                if composition is not None
                else None
            )
            logger.info(
                "[mc-labels-debug] should_paint=%s composition=%s labels=%s",
                result,
                composition is not None,
                labels,
            )
        return result

    def _raster(self, widget, ctx) -> QImage | None:
        composition = ctx.composition
        debug = getattr(widget, "_mc_overlay_debug", False)
        if not self._source.should_paint(composition):
            if debug:
                logger.info("[mc-labels-debug] _raster: should_paint False, returning None")
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
        if debug:
            logger.info(
                "[mc-labels-debug] _raster: rasterized fb=%sx%s isNull=%s",
                fb_w,
                fb_h,
                img.isNull(),
            )
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)


RENDER_PASSES: list[FullscreenOverlayTexturePass] = [LayerLabelsPass()]
RENDER_PASSES = RENDER_PASSES
