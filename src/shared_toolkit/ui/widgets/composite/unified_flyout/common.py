import logging
from enum import Enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter, QPainterPath
from PyQt6.QtWidgets import QGraphicsEffect

logger = logging.getLogger("ImproveImgSLI")

class _RoundedClipEffect(QGraphicsEffect):
    def __init__(self, radius=8, parent=None):
        super().__init__(parent)
        self._radius = radius

    def draw(self, painter: QPainter):
        src = self.sourceBoundingRect()
        if src.isEmpty():
            return
        clip = QPainterPath()
        clip.addRoundedRect(src, self._radius, self._radius)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
        self.drawSource(painter)
        painter.restore()

class FlyoutMode(Enum):
    HIDDEN = 0
    SINGLE_LEFT = 1
    SINGLE_RIGHT = 2
    DOUBLE = 3
    SINGLE_SIMPLE = 4
