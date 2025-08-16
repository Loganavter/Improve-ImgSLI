from __future__ import annotations

from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

class BodyLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setText("")
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        font = QFont(self.font())
        font.setPointSize(max(10, font.pointSize()))
        self.setFont(font)

class CaptionLabel(QLabel):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        font = QFont(self.font())

        size = font.pointSize()
        if size > 0:
            font.setPointSize(max(9, size - 1))
        self.setFont(font)
