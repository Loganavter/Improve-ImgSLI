"""Toolbar for multi-compare tab."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget
from sli_ui_toolkit.i18n import translatable_text, translatable_tooltip
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import Button, ThemedWidget
from ui.widgets.scroll_value_button import ScrollValueButton

from sli_ui_toolkit.i18n import tr
from tabs.multi_compare.ui.layout_manager import MultiCompareLayoutManager
from tabs.multi_compare.icons import Icon
from ui.theming import resolve_theme_color


def _tr_with_default(key: str, default: str):
    def _resolve(_key: str, lang: str) -> str:
        result = tr(_key, lang)
        return result if result != _key else default

    return _resolve


class MultiCompareToolbar(ThemedWidget, QWidget):
    """Top toolbar: add image, quick-save, divider controls, label settings."""

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
            icon=(Icon.DIVIDER_VISIBLE, Icon.DIVIDER_HIDDEN),
            toggle=True,
            parent=self,
        )
        translatable_tooltip(
            self.btn_divider_visible,
            "tooltip.toggle_divider_visibility",
            tr_func=_tr_with_default(
                "tooltip.toggle_divider_visibility", "Toggle divider visibility"
            ),
            defer_when_hidden=True,
        )
        self.btn_divider_visible.toggled.connect(
            lambda checked: self.divider_visible_toggled.emit(not checked)
        )

        self.btn_divider_color = Button(
            Icon.DIVIDER_COLOR,
            show_underline=True,
            parent=self,
        )
        self.btn_divider_color.setObjectName("mc_btn_divider_color")
        translatable_tooltip(
            self.btn_divider_color,
            "tooltip.divider_color",
            tr_func=_tr_with_default("tooltip.divider_color", "Divider color"),
            defer_when_hidden=True,
        )
        self.btn_divider_color.clicked.connect(self.divider_color_clicked)

        self.btn_divider_width = ScrollValueButton(
            icon=Icon.GRID,
            min_value=0,
            max_value=10,
            zero_icon=Icon.DIVIDER_HIDDEN,
            parent=self,
        )
        self.btn_divider_width.setObjectName("mc_btn_divider_width")
        translatable_tooltip(
            self.btn_divider_width,
            "multi_compare.action.divider_width_desc",
            tr_func=_tr_with_default(
                "multi_compare.action.divider_width_desc",
                "Grid line width, color (right-click), and visibility (set to zero)",
            ),
            defer_when_hidden=True,
        )
        if hasattr(self.btn_divider_width, "valueChanged"):
            self.btn_divider_width.valueChanged.connect(self.divider_width_changed)
        if hasattr(self.btn_divider_width, "rightClicked"):
            self.btn_divider_width.rightClicked.connect(
                self._on_divider_width_right_clicked
            )

        self.btn_add = Button(Icon.PHOTO, text=text, variant="surface", parent=self)
        translatable_text(
            self.btn_add,
            "add_images",
            tr_func=_tr_with_default("add_images", "Add images"),
            defer_when_hidden=True,
        )
        translatable_tooltip(
            self.btn_add,
            "tooltip.multi_compare_add_images",
            tr_func=_tr_with_default(
                "tooltip.multi_compare_add_images", "Add images to the comparison grid"
            ),
            defer_when_hidden=True,
        )
        self.btn_add.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.btn_add.clicked.connect(self.add_clicked)

        self.btn_text_settings = Button(
            Icon.TEXT_FILENAME,
            variant="default",
            parent=self,
        )
        translatable_tooltip(
            self.btn_text_settings,
            "tooltip.multi_compare_text_settings",
            tr_func=_tr_with_default(
                "tooltip.multi_compare_text_settings",
                "Change labels drawn over grid images",
            ),
            defer_when_hidden=True,
        )
        self.btn_text_settings.clicked.connect(self.text_settings_clicked)

        self.btn_quick_save = Button(
            Icon.QUICK_SAVE, variant="surface", background_color=accent, parent=self
        )
        self.btn_quick_save.setIconSizePx(24)
        translatable_tooltip(
            self.btn_quick_save,
            "tooltip.quick_save_image",
            tr_func=_tr_with_default(
                "tooltip.quick_save_image",
                "Save immediately using the last export location",
            ),
            defer_when_hidden=True,
        )
        self.btn_quick_save.clicked.connect(self.quick_save_clicked)

        # Host title bar owns app Settings/Help — keep widgets for wiring compat but hide.
        self.btn_settings = Button(
            Icon.SETTINGS, variant="surface", background_color=accent, parent=self
        )
        self.btn_settings.hide()
        self.help_button = Button(
            Icon.HELP, variant="surface", background_color=accent, parent=self
        )
        self.help_button.setIconSizePx(24)
        self.help_button.hide()

        self.line_group_container = self._button_group(
            [self.btn_divider_visible, self.btn_divider_color, self.btn_divider_width],
        )
        self.label_group_container = self._button_group(
            [self.btn_text_settings],
        )
        self.action_group_container = self._button_group(
            [self.btn_quick_save],
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

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._bg_color)
        painter.end()

    def on_theme_changed(self) -> None:
        self._bg_color = QColor(resolve_theme_color(self._theme_manager, "Window"))
        super().on_theme_changed()
