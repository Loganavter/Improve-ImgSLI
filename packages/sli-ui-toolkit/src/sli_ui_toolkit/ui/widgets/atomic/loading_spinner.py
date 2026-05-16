from PyQt6.QtCore import QPointF, Qt, QTimer
from PyQt6.QtGui import QColor, QConicalGradient, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager

class LoadingSpinner(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(40, 40)

    def start(self):
        if not self._timer.isActive():
            self._timer.start(15)

    def stop(self):
        if self._timer.isActive():
            self._timer.stop()

    def is_spinning(self) -> bool:
        return self._timer.isActive()

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = QPointF(self.rect().center())
        radius = min(self.width(), self.height()) / 2.0

        gradient = QConicalGradient(center, float(-self._angle))

        accent_color = self.theme_manager.get_color("accent")
        transparent_color = QColor(accent_color)
        transparent_color.setAlpha(0)

        gradient.setColorAt(0.0, accent_color)
        gradient.setColorAt(0.1, accent_color)
        gradient.setColorAt(0.8, transparent_color)
        gradient.setColorAt(1.0, transparent_color)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)

        path = QPainterPath()
        outer_radius = radius - 2
        inner_radius = radius - 8
        path.addEllipse(center, outer_radius, outer_radius)
        path.addEllipse(center, inner_radius, inner_radius)
        path.setFillRule(Qt.FillRule.OddEvenFill)

        painter.drawPath(path)
