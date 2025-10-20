from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

class DragGhostWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.ToolTip |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        self.pixmap_label = QLabel()
        self._layout.addWidget(self.pixmap_label)

        self.setOpacity(0.75)

    def set_pixmap(self, pixmap: QPixmap):
        self.pixmap_label.setPixmap(pixmap)
        self.setFixedSize(pixmap.size())

    def setOpacity(self, opacity):
        self.setWindowOpacity(opacity)
