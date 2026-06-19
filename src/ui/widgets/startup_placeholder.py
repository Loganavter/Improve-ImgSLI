from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StartupPlaceholder(QWidget):
    """Transparent overlay shown over the image area before any image is loaded.

    Tracks the geometry of a target widget (the image canvas) and exposes
    a single text label centered in the middle.
    """

    def __init__(self, parent: QWidget, target_widget: QWidget | None = None):
        super().__init__(parent)
        self._target_widget = target_widget

        self.setObjectName("ImageStartupPlaceholder")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addStretch(1)

        self.label = QLabel("", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.hide()
        layout.addWidget(self.label, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

        self.sync_geometry()
        self.show()
        self.raise_()

    def set_target(self, target: QWidget):
        self._target_widget = target

    def sync_geometry(self):
        if self._target_widget is None:
            return
        self.setGeometry(self._target_widget.geometry())
        self.raise_()

    def set_background_color(self, color):
        bg = QColor(color)
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, bg)
        pal.setColor(QPalette.ColorRole.Base, bg)
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.update()
