from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush
from toolkit.widgets.atomic.clickable_label import ClickableLabel

class CanvasWidget(ClickableLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._background_pixmap: QPixmap | None = None
        self._magnifier_pixmap: QPixmap | None = None
        self._magnifier_pos: QPoint | None = None

        self._show_divider = False
        self._split_pos_x = 0

        self._capture_area_center: QPoint | None = None
        self._capture_area_size: int = 0
        self._capture_area_color: QColor = QColor(255, 50, 100, 230)

    def set_layers(self, background: QPixmap | None, magnifier: QPixmap | None, mag_pos: QPoint | None):
        should_update = False

        if background is not None:
            self._background_pixmap = background
            should_update = True

        if magnifier is not self._magnifier_pixmap:
            self._magnifier_pixmap = magnifier
            should_update = True

        if mag_pos != self._magnifier_pos:
            self._magnifier_pos = mag_pos
            should_update = True

        if should_update:
            self.update()

    def set_split_line_params(self, visible: bool, pos_x: int):
        if self._show_divider != visible or self._split_pos_x != pos_x:
            self._show_divider = visible
            self._split_pos_x = pos_x
            self.update()

    def set_capture_area(self, center: QPoint | None, size: int, color: QColor | None = None):
        should_update = False

        if center != self._capture_area_center:
            self._capture_area_center = center
            should_update = True

        if size != self._capture_area_size:
            self._capture_area_size = size
            should_update = True

        if color and color != self._capture_area_color:
            self._capture_area_color = color
            should_update = True

        if should_update:
            self.update()

    def setPixmap(self, pixmap: QPixmap | None):
        if pixmap:
            self.set_layers(pixmap, None, None)
        else:
            self.set_layers(None, None, None)

    def paintEvent(self, event):

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        if self._background_pixmap and not self._background_pixmap.isNull():

            painter.drawPixmap(0, 0, self._background_pixmap)

        if self._capture_area_center and self._capture_area_size > 0:

            import math
            CAPTURE_THICKNESS_FACTOR = 0.1
            MIN_CAPTURE_THICKNESS = 2.0
            MAX_CAPTURE_THICKNESS = 8.0

            thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(self._capture_area_size)))
            thickness_clamped = max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float))
            thickness = max(2, int(round(thickness_clamped)))

            radius = self._capture_area_size // 2

            painter.setPen(QPen(self._capture_area_color, thickness))
            painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            painter.drawEllipse(
                self._capture_area_center.x() - radius,
                self._capture_area_center.y() - radius,
                self._capture_area_size,
                self._capture_area_size
            )

        if self._magnifier_pixmap and not self._magnifier_pixmap.isNull() and self._magnifier_pos:

            painter.drawPixmap(self._magnifier_pos, self._magnifier_pixmap)

