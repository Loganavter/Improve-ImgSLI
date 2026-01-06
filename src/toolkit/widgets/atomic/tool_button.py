from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QToolButton

class ToolButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setAutoRaise(True)

        self.setObjectName("ToolButton")

    def setIcon(self, icon: QIcon):  # noqa: N802 - совместимость с используемым API
        super().setIcon(icon)

    def setIconSize(self, size: QSize):  # noqa: N802 - совместимость с используемым API
        super().setIconSize(size)

