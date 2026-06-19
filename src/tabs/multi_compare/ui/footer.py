"""Footer bar for multi-compare tab."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon


class MultiCompareFooter(QWidget):
    """Bottom bar: save composed grid (mirrors main workspace btn_save)."""

    save_clicked = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        text: str = "Save result",
    ):
        super().__init__(parent)
        self.setFixedHeight(44)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        self.btn_save = Button(
            AppIcon.SAVE, text=text, variant="surface", parent=self
        )
        self.btn_save.setMinimumHeight(32)
        self.btn_save.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_save.clicked.connect(self.save_clicked)

        layout.addWidget(self.btn_save, 1)

    def update_language(self, translate) -> None:
        self.btn_save.setText(translate("save_result", "Save result"))
