"""Toolbar for multi-compare tab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button
from ui.icon_manager import AppIcon
from ui.theming import resolve_theme_color


class MultiCompareToolbar(QWidget):
    """Top toolbar: add image + cross-tab help/settings/quick-save."""

    add_clicked = Signal()
    text_settings_clicked = Signal()
    quick_save_clicked = Signal()
    settings_clicked = Signal()
    help_clicked = Signal()

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

        accent = QColor(resolve_theme_color(ThemeManager.get_instance(), "accent"))
        self.btn_text_settings = Button(
            AppIcon.TEXT_MANIPULATOR, variant="surface", background_color=accent, parent=self
        )
        self.btn_text_settings.setToolTip("Text settings")
        self.btn_text_settings.clicked.connect(self.text_settings_clicked)

        self.btn_quick_save = Button(
            AppIcon.QUICK_SAVE, variant="surface", background_color=accent, parent=self
        )
        self.btn_quick_save.setIconSizePx(24)
        self.btn_quick_save.clicked.connect(self.quick_save_clicked)

        self.btn_settings = Button(
            AppIcon.SETTINGS, variant="surface", background_color=accent, parent=self
        )
        self.btn_settings.clicked.connect(self.settings_clicked)

        self.help_button = Button(
            AppIcon.HELP, variant="surface", background_color=accent, parent=self
        )
        self.help_button.setIconSizePx(24)
        self.help_button.clicked.connect(self.help_clicked)

        layout.addWidget(self.btn_text_settings)
        layout.addWidget(self.btn_add, 1)
        layout.addWidget(self.btn_quick_save)
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.help_button)

    def update_language(self, translate) -> None:
        self.btn_add.setText(translate("add_images", "Add images"))
        self.btn_text_settings.setToolTip(
            translate("text_settings", "Text settings")
        )
