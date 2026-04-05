from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QImage, QPixmap

from .quick_bridge import QuickCanvasBridge
from .quick_image_provider import QuickCanvasImageProvider

@dataclass
class QuickOverlayState:
    bridge: QuickCanvasBridge
    image_provider: QuickCanvasImageProvider
    provider_id: str
    base_revision_ref: list[int]
    magnifier_qimage: QImage | None = None
    magnifier_top_left: QPoint | None = None
    capture_center: QPointF | None = None
    capture_radius: float = 0.0
    magnifier_centers: list[QPointF] = field(default_factory=list)
    magnifier_radius: float = 0.0
    guides_visible: bool = False
    guides_color: QColor = field(default_factory=lambda: QColor(255, 255, 255, 120))
    guides_thickness: float = 1.0
    capture_color: QColor = field(default_factory=lambda: QColor(255, 50, 100, 230))

    def _next_revision(self) -> int:
        self.base_revision_ref[0] += 1
        return self.base_revision_ref[0]

    def set_magnifier_content(self, pixmap: QPixmap | None, top_left: QPoint | None) -> int | None:
        self.magnifier_qimage = (
            pixmap.toImage() if pixmap is not None and not pixmap.isNull() else None
        )
        self.magnifier_top_left = QPoint(top_left) if top_left is not None else None
        if self.magnifier_top_left is not None:
            self.bridge.set_magnifier_x(float(self.magnifier_top_left.x()))
            self.bridge.set_magnifier_y(float(self.magnifier_top_left.y()))
        else:
            self.bridge.set_magnifier_x(0.0)
            self.bridge.set_magnifier_y(0.0)

        if self.magnifier_qimage is None:
            self.bridge.set_magnifier_source("")
            self.bridge.set_magnifier_visible(False)
            return None

        revision = self._next_revision()
        self.image_provider.set_image("magnifier", self.magnifier_qimage)
        self.bridge.set_magnifier_source(f"image://{self.provider_id}/magnifier?v={revision}")
        self.bridge.set_magnifier_visible(True)
        return revision

    def set_overlay_coords(
        self,
        capture_center: QPointF | None,
        capture_radius: float,
        mag_centers: list[QPointF],
        mag_radius: float,
    ) -> None:
        self.capture_center = (
            QPointF(float(capture_center.x()), float(capture_center.y()))
            if capture_center is not None
            else None
        )
        self.capture_radius = float(capture_radius or 0.0)
        self.magnifier_centers = [
            QPointF(float(center.x()), float(center.y()))
            for center in (mag_centers or [])
        ]
        self.magnifier_radius = float(mag_radius or 0.0)

        self.bridge.set_capture_visible(
            self.capture_center is not None and self.capture_radius > 0.0
        )
        self.bridge.set_capture_x(
            float(self.capture_center.x()) if self.capture_center is not None else 0.0
        )
        self.bridge.set_capture_y(
            float(self.capture_center.y()) if self.capture_center is not None else 0.0
        )
        self.bridge.set_capture_radius(self.capture_radius)
        self.bridge.set_overlay_centers(
            [{"x": float(center.x()), "y": float(center.y())} for center in self.magnifier_centers]
        )
        self.bridge.set_overlay_radius(self.magnifier_radius)

    def set_guides_params(self, visible: bool, color: QColor, thickness: int) -> None:
        self.guides_visible = bool(visible)
        self.guides_color = QColor(color) if color is not None else QColor(255, 255, 255, 120)
        self.guides_thickness = float(max(1, int(thickness or 1)))
        self.bridge.set_guides_visible(self.guides_visible)
        self.bridge.set_guides_color(self.guides_color)
        self.bridge.set_guides_thickness(self.guides_thickness)

    def set_capture_color(self, color: QColor) -> None:
        self.capture_color = QColor(color) if color is not None else QColor(255, 50, 100, 230)
        self.bridge.set_capture_color(self.capture_color)

    def clear(self) -> None:
        self.set_magnifier_content(None, None)
        self.set_overlay_coords(None, 0.0, [], 0.0)
