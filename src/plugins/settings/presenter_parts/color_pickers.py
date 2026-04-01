from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QColorDialog

from core.events import (
    SettingsSetDividerLineColorEvent,
    SettingsSetMagnifierDividerColorEvent,
)
from domain.qt_adapters import color_to_qcolor, qcolor_to_color

class SettingsColorPickerCoordinator:
    def __init__(self, store, main_controller, main_window_app, tr_func):
        self.store = store
        self.main_controller = main_controller
        self.main_window_app = main_window_app
        self.tr = tr_func
        self._dialogs: dict[str, QColorDialog | None] = {
            "divider": None,
            "magnifier_divider": None,
            "magnifier_border": None,
            "laser": None,
            "capture_ring": None,
        }

    def show_divider_color_picker(self):
        self._show_dialog(
            key="divider",
            current_color=self.store.viewport.render_config.divider_line_color,
            title_key="ui.choose_divider_line_color",
            on_selected=self._apply_divider_color,
            post_apply=self._sync_divider_button_color,
        )

    def show_magnifier_divider_color_picker(self):
        self._show_dialog(
            key="magnifier_divider",
            current_color=self.store.viewport.render_config.magnifier_divider_color,
            title_key="ui.choose_magnifier_divider_line_color",
            on_selected=self._apply_magnifier_divider_color,
        )

    def show_magnifier_border_color_picker(self):
        self._show_dialog(
            key="magnifier_border",
            current_color=self.store.viewport.render_config.magnifier_border_color,
            title_key="ui.choose_magnifier_border_color",
            on_selected=self._apply_via_settings("set_magnifier_border_color"),
        )

    def show_laser_color_picker(self):
        self._show_dialog(
            key="laser",
            current_color=self.store.viewport.render_config.magnifier_laser_color,
            title_key="ui.choose_magnifier_guides_color",
            on_selected=self._apply_via_settings("set_magnifier_laser_color"),
        )

    def show_capture_ring_color_picker(self):
        self._show_dialog(
            key="capture_ring",
            current_color=self.store.viewport.render_config.capture_ring_color,
            title_key="ui.choose_capture_ring_color",
            on_selected=self._apply_via_settings("set_capture_ring_color"),
        )

    def apply_smart_magnifier_colors(self):
        dialog = QColorDialog(
            color_to_qcolor(self.store.viewport.render_config.magnifier_divider_color),
            self.main_window_app,
        )
        dialog.setWindowTitle(self.tr("ui.choose_magnifier_base_color"))
        self.main_window_app.theme_manager.apply_theme_to_dialog(dialog)

        def on_color_selected(color):
            if not color.isValid():
                return

            laser_color = QColor(color)
            laser_color.setAlpha(120)

            border_color = QColor(color)
            border_color.setAlpha(230)

            capture_ring_color = QColor(color)
            capture_ring_color.setAlpha(230)

            settings_controller = self._settings_controller()
            if settings_controller is None:
                return

            settings_controller.set_magnifier_border_color(qcolor_to_color(border_color))
            settings_controller.set_magnifier_laser_color(qcolor_to_color(laser_color))
            settings_controller.set_capture_ring_color(qcolor_to_color(capture_ring_color))

        dialog.colorSelected.connect(on_color_selected)
        dialog.show()

    def _show_dialog(
        self,
        *,
        key: str,
        current_color,
        title_key: str,
        on_selected: Callable,
        post_apply: Callable | None = None,
    ):
        dialog = self._dialogs.get(key)
        if dialog and dialog.isVisible():
            dialog.raise_()
            dialog.activateWindow()
            return

        dialog = QColorDialog(color_to_qcolor(current_color), self.main_window_app)
        dialog.setWindowFlags(dialog.windowFlags() | 0x00000000)
        dialog.setModal(False)
        dialog.setWindowTitle(self.tr(title_key))
        self.main_window_app.theme_manager.apply_theme_to_dialog(dialog)

        def handle_selected(color):
            if not color.isValid():
                return
            on_selected(color)
            if post_apply is not None:
                post_apply(color)

        dialog.colorSelected.connect(handle_selected)
        dialog.show()
        self._dialogs[key] = dialog

    def _apply_divider_color(self, color):
        event_bus = getattr(self.main_controller, "event_bus", None)
        if event_bus:
            event_bus.emit(SettingsSetDividerLineColorEvent(qcolor_to_color(color)))

    def _sync_divider_button_color(self, color):
        if hasattr(self.main_window_app, "set_divider_button_color"):
            self.main_window_app.set_divider_button_color(color)

    def _apply_magnifier_divider_color(self, color):
        event_bus = getattr(self.main_controller, "event_bus", None)
        if event_bus:
            event_bus.emit(
                SettingsSetMagnifierDividerColorEvent(qcolor_to_color(color))
            )

    def _apply_via_settings(self, method_name: str) -> Callable:
        def apply(color):
            settings_controller = self._settings_controller()
            if settings_controller is not None:
                getattr(settings_controller, method_name)(qcolor_to_color(color))

        return apply

    def _settings_controller(self):
        return getattr(self.main_controller, "settings", None)
