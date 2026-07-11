"""Toolbar for multi-compare tab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from sli_ui_toolkit.i18n import translatable_text, translatable_tooltip
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button
from ui.widgets.scroll_value_button import ScrollValueButton

from sli_ui_toolkit.i18n import tr
from tabs.multi_compare.ui.layout_manager import MultiCompareLayoutManager
from ui.icon_manager import AppIcon
from ui.theming import resolve_theme_color


def _tr_with_default(key: str, default: str):
    def _resolve(_key: str, lang: str) -> str:
        result = tr(_key, lang)
        return result if result != _key else default

    return _resolve


class MultiCompareToolbar(QWidget):
    """Top toolbar: add image + cross-tab help/settings/quick-save + divider controls."""

    add_clicked = Signal()
    text_settings_clicked = Signal()
    quick_save_clicked = Signal()
    settings_clicked = Signal()
    help_clicked = Signal()

    divider_visible_toggled = Signal(bool)
    divider_width_changed = Signal(int)
    divider_color_clicked = Signal()

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
        self._layout = layout
        self._ui_mode = "beginner"

        accent = QColor(resolve_theme_color(ThemeManager.get_instance(), "accent"))

        self.btn_divider_visible = Button(
            icon=(AppIcon.DIVIDER_VISIBLE, AppIcon.DIVIDER_HIDDEN),
            toggle=True,
            parent=self,
        )
        translatable_tooltip(
            self.btn_divider_visible,
            "tooltip.toggle_divider_visibility",
            tr_func=_tr_with_default(
                "tooltip.toggle_divider_visibility", "Toggle divider visibility"
            ),
        )
        self.btn_divider_visible.toggled.connect(
            lambda checked: self.divider_visible_toggled.emit(not checked)
        )

        self.btn_divider_color = Button(
            AppIcon.DIVIDER_COLOR,
            show_underline=True,
            parent=self,
        )
        self.btn_divider_color.setObjectName("mc_btn_divider_color")
        translatable_tooltip(
            self.btn_divider_color,
            "tooltip.divider_color",
            tr_func=_tr_with_default("tooltip.divider_color", "Divider color"),
        )
        self.btn_divider_color.clicked.connect(self.divider_color_clicked)

        self.btn_divider_width = ScrollValueButton(
            icon=AppIcon.VERTICAL_SPLIT,
            min_value=0,
            max_value=10,
            zero_icon=AppIcon.DIVIDER_HIDDEN,
            parent=self,
        )
        self.btn_divider_width.setObjectName("mc_btn_divider_width")
        translatable_tooltip(
            self.btn_divider_width,
            "tooltip.adjust_divider_width",
            tr_func=_tr_with_default(
                "tooltip.adjust_divider_width", "Adjust divider width"
            ),
        )
        if hasattr(self.btn_divider_width, "valueChanged"):
            self.btn_divider_width.valueChanged.connect(self.divider_width_changed)
        if hasattr(self.btn_divider_width, "rightClicked"):
            self.btn_divider_width.rightClicked.connect(
                self._on_divider_width_right_clicked
            )

        self.btn_add = Button(AppIcon.PHOTO, text=text, variant="surface", parent=self)
        translatable_text(
            self.btn_add,
            "add_images",
            tr_func=_tr_with_default("add_images", "Add images"),
        )
        translatable_tooltip(
            self.btn_add,
            "tooltip.multi_compare_add_images",
            tr_func=_tr_with_default(
                "tooltip.multi_compare_add_images", "Add images to the comparison grid"
            ),
        )
        self.btn_add.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.btn_add.clicked.connect(self.add_clicked)

        self.btn_text_settings = Button(
            AppIcon.TEXT_FILENAME,
            variant="surface",
            parent=self,
        )
        translatable_tooltip(
            self.btn_text_settings,
            "tooltip.multi_compare_text_settings",
            tr_func=_tr_with_default(
                "tooltip.multi_compare_text_settings",
                "Change labels drawn over grid images",
            ),
        )
        self.btn_text_settings.clicked.connect(self.text_settings_clicked)

        self.btn_quick_save = Button(
            AppIcon.QUICK_SAVE, variant="surface", background_color=accent, parent=self
        )
        self.btn_quick_save.setIconSizePx(24)
        translatable_tooltip(
            self.btn_quick_save,
            "tooltip.quick_save_image",
            tr_func=_tr_with_default(
                "tooltip.quick_save_image",
                "Save immediately using the last export location",
            ),
        )
        self.btn_quick_save.clicked.connect(self.quick_save_clicked)

        self.btn_settings = Button(
            AppIcon.SETTINGS, variant="surface", background_color=accent, parent=self
        )
        translatable_tooltip(
            self.btn_settings,
            "tooltip.open_application_settings",
            tr_func=_tr_with_default(
                "tooltip.open_application_settings",
                "Open app and workspace settings",
            ),
        )
        self.btn_settings.clicked.connect(self.settings_clicked)

        self.help_button = Button(
            AppIcon.HELP, variant="surface", background_color=accent, parent=self
        )
        self.help_button.setIconSizePx(24)
        translatable_tooltip(
            self.help_button,
            "tooltip.show_help",
            tr_func=_tr_with_default("tooltip.show_help", "Open help for this workflow"),
        )
        self.help_button.clicked.connect(self.help_clicked)

        self.line_group_container = self._button_group(
            [self.btn_divider_visible, self.btn_divider_color, self.btn_divider_width],
        )
        self.label_group_container = self._button_group(
            [self.btn_text_settings],
        )
        self.action_group_container = self._button_group(
            [self.btn_quick_save, self.btn_settings, self.help_button],
        )

        layout.addWidget(self.line_group_container)
        layout.addWidget(self.label_group_container)
        layout.addWidget(self.btn_add, 1)
        layout.addWidget(self.action_group_container)
        self.layout_manager = MultiCompareLayoutManager(self)

    def _button_group(self, buttons) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for button in buttons:
            layout.addWidget(button)
        return container

    def apply_ui_mode(self, mode: str) -> None:
        self._ui_mode = (
            mode if mode in {"beginner", "advanced", "expert"} else "beginner"
        )
        self.btn_divider_width.setShowUnderline(self._ui_mode == "expert")
        self.layout_manager.apply_mode(mode)

    def _on_divider_width_right_clicked(self) -> None:
        if self._ui_mode == "expert":
            self.divider_color_clicked.emit()
