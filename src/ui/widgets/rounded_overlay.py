from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


class RoundedOverlayWidget(QWidget):
    """Child widget that paints its own AA rounded background.

    Works correctly when hosted over a QOpenGLWidget where QSS border-radius
    on a child widget leaves a leaking rectangle outside the rounded shape.
    """

    def __init__(self, parent=None, *, bg_color=QColor(0, 0, 0, 140), radius=6):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._bg_color = bg_color
        self._radius = float(radius)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)
        painter.end()
