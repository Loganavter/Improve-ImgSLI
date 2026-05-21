"""Toolbar for multi-compare tab."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon

class MultiCompareToolbar(QWidget):
    """Top toolbar: reset zoom, grid/focus toggle, clear."""

    reset_zoom_clicked = pyqtSignal()
    toggle_grid_clicked = pyqtSignal()
    clear_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self.btn_reset_zoom = Button(AppIcon.CROP_OUT, parent=self)
        self.btn_reset_zoom.setToolTip("Reset zoom")
        self.btn_reset_zoom.clicked.connect(self.reset_zoom_clicked)

        self.btn_grid_mode = Button(
            icon=(AppIcon.HORIZONTAL_SPLIT, AppIcon.MAGNIFIER), toggle=True, parent=self,
        )
        self.btn_grid_mode.setToolTip("Grid / Focus")
        self.btn_grid_mode.toggled.connect(lambda _: self.toggle_grid_clicked.emit())

        self.btn_clear = Button(AppIcon.DELETE, variant="delete", parent=self)
        self.btn_clear.setToolTip("Clear all")
        self.btn_clear.clicked.connect(self.clear_clicked)

        self.slot_count_label = QLabel("0 images")
        self.slot_count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.btn_reset_zoom)
        layout.addWidget(self.btn_grid_mode)
        layout.addSpacing(12)
        layout.addWidget(self.slot_count_label)
        layout.addStretch()
        layout.addWidget(self.btn_clear)

    def update_slot_count(self, count: int) -> None:
        self.slot_count_label.setText(f"{count} images")
