"""Footer bar for multi-compare tab — export controls placeholder."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon

class MultiCompareFooter(QWidget):
    """Bottom bar: export button (placeholder for future export flow)."""

    export_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        layout.addStretch()

        self.btn_export = Button(AppIcon.SAVE, text="Export", variant="primary", size=(80, 30), parent=self)
        self.btn_export.clicked.connect(self.export_clicked)
        layout.addWidget(self.btn_export)
