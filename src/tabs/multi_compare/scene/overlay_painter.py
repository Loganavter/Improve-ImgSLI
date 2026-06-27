"""QPainter raster overlay builder for Multi Compare render passes."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource
from tabs.multi_compare.scene.passes.drag_overlay import DragDropOverlaySource
from tabs.multi_compare.scene.passes.labels import LabelsOverlaySource


class MultiCompareOverlayPainter:
    """Rasterizes labels and live drag/drop affordances."""

    def __init__(self, host) -> None:
        self.host = host
        self.dividers = DividersOverlaySource()
        self.labels = LabelsOverlaySource()
        self.drag_drop = DragDropOverlaySource()

    def build(
        self,
        composition,
        sr: float,
        ox: float,
        oy: float,
        fb_w: int,
        fb_h: int,
    ) -> QImage | None:
        """Build the overlay texture at framebuffer resolution."""

        state = self.host.state
        if not any(
            source.should_paint(composition, state)
            for source in (self.dividers, self.labels, self.drag_drop)
        ):
            return None
        phys_w = max(1, int(fb_w))
        phys_h = max(1, int(fb_h))
        img = QImage(phys_w, phys_h, QImage.Format.Format_RGBA8888_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        if self.dividers.should_paint(composition, state):
            self.dividers.paint(
                painter,
                host=self.host,
                composition=composition,
                state=state,
                scale=sr,
                offset=(ox, oy),
            )

        if self.labels.should_paint(composition, state):
            self.labels.paint(
                painter,
                composition=composition,
                state=state,
                scale=sr,
                offset=(ox, oy),
            )

        if self.drag_drop.should_paint(composition, state):
            dpr = max(1.0, float(self.host.devicePixelRatioF()))
            painter.save()
            painter.scale(dpr, dpr)
            self.drag_drop.paint(painter, host=self.host)
            painter.restore()

        painter.end()
        return img.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
