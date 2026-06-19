"""Toolbar for multi-compare tab."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon


class MultiCompareToolbar(QWidget):
    """Top toolbar: add image (mirrors main workspace btn_image)."""

    add_clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        text: str = "Add images",
    ):
        super().__init__(parent)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.btn_add = Button(
            AppIcon.PHOTO, text=text, variant="surface", parent=self
        )
        self.btn_add.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_add.clicked.connect(self.add_clicked)

        layout.addWidget(self.btn_add, 1)

    def update_language(self, translate) -> None:
        self.btn_add.setText(translate("add_images", "Add images"))
