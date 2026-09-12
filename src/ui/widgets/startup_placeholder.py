from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ui.widgets.themed_surface import ThemedSurface


class StartupPlaceholder(ThemedSurface):
    """Transparent overlay shown over the image area before any image is loaded.

    Tracks the geometry of a target widget (the image canvas) and exposes
    a single text label centered in the middle.
    """

    def __init__(self, parent: QWidget, target_widget: QWidget | None = None):
        super().__init__(parent)
        self._target_widget = target_widget

        self.setObjectName("ImageStartupPlaceholder")
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

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def set_target(self, target: QWidget):
        self._target_widget = target

    def sync_geometry(self):
        if self._target_widget is None:
            return
        self.setGeometry(self._target_widget.geometry())
        self.raise_()

    def set_background_color(self, color):
        """Backward-compatible no-op: background tracks theme via ThemedSurface."""
        self.update()
