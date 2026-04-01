from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, pyqtSignal

from domain.types import Color

from core.events import (
    SettingsApplyFontSettingsEvent,
    SettingsChangeLanguageEvent,
    SettingsSetDividerLineColorEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerColorEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleAutoCropBlackBordersEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
)
from plugins.settings.color_actions import SettingsColorActions
from plugins.settings.mutations import SettingsMutationService
from plugins.settings.notifier import SettingsUpdateNotifier

logger = logging.getLogger("ImproveImgSLI")

class SettingsController(QObject):

    update_requested = pyqtSignal()

    def __init__(self, store, settings_manager, presenter=None, event_bus=None):
        super().__init__()
        self.store = store
        self.settings_manager = settings_manager
        self.presenter = presenter
        self.event_bus = event_bus
        self.notifier = SettingsUpdateNotifier(
            store=store,
            event_bus=event_bus,
            update_requested_signal=self.update_requested,
        )
        self.mutations = SettingsMutationService(
            store=store,
            settings_manager=settings_manager,
            notifier=self.notifier,
        )
        self.color_actions = SettingsColorActions(
            store=store,
            presenter=presenter,
            main_window_getter=lambda: presenter.main_window_app if presenter else None,
        )

    def change_language(self, lang_code: str):
        changed = self.mutations.set_settings_value(
            "current_language",
            lang_code,
            setting_key="language",
            emit_scope="settings",
        )
        if not changed:
            return

        main_controller = getattr(self.presenter, "main_controller", None)
        window_shell = getattr(main_controller, "window_shell", None)
        if window_shell is not None and hasattr(window_shell, "on_language_changed"):
            window_shell.on_language_changed()
            return

        if self.presenter:
            self.presenter.on_language_changed()

    def toggle_include_filenames_in_saved(self, checked: bool):
        self.mutations.set_viewport_value(
            "include_file_names_in_saved",
            checked,
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def apply_font_settings(
        self,
        size: int,
        font_weight: int,
        color: Color,
        bg_color: Color,
        draw_background: bool,
        placement_mode: str,
        text_alpha_percent: int,
    ):
        self.mutations.apply_font_settings(
            size=size,
            font_weight=font_weight,
            color=color,
            bg_color=bg_color,
            draw_background=draw_background,
            placement_mode=placement_mode,
            text_alpha_percent=text_alpha_percent,
        )

    def toggle_divider_line_visibility(self, visible: bool):
        self.mutations.set_viewport_value(
            "divider_line_visible",
            visible,
            setting_key="divider_line_visible",
            request_core_update=True,
        )

    def set_divider_line_color(self, color: Color):
        self.mutations.set_viewport_color(
            "divider_line_color",
            color,
            setting_key="divider_line_color",
            request_core_update=True,
        )

    def set_divider_line_thickness(self, thickness: int):
        thickness = max(0, min(20, int(thickness)))
        self.mutations.set_viewport_value(
            "divider_line_thickness",
            thickness,
            setting_key="divider_line_thickness",
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def toggle_magnifier_divider_visibility(self, visible: bool):
        self.mutations.set_viewport_value(
            "magnifier_divider_visible",
            visible,
            setting_key="magnifier_divider_visible",
            request_core_update=True,
        )

    def set_magnifier_divider_color(self, color: Color):
        self.mutations.set_viewport_color(
            "magnifier_divider_color",
            color,
            setting_key="magnifier_divider_color",
            request_core_update=True,
        )

    def show_magnifier_divider_color_picker(self):
        self.color_actions.show_magnifier_divider_color_picker(
            self.set_magnifier_divider_color
        )

    def set_magnifier_divider_thickness(self, thickness: int):
        thickness = max(0, min(10, int(thickness)))
        self.mutations.set_viewport_value(
            "magnifier_divider_thickness",
            thickness,
            setting_key="magnifier_divider_thickness",
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def toggle_auto_crop_black_borders(self, enabled: bool):
        self.mutations.set_settings_value(
            "auto_crop_black_borders",
            enabled,
            setting_key="auto_crop_black_borders",
            emit_scope="settings",
        )

    def apply_smart_magnifier_colors(self):
        self.color_actions.apply_smart_magnifier_colors(
            set_divider_color=self.set_magnifier_divider_color,
            set_laser_color=self.set_magnifier_laser_color,
            set_capture_ring_color=self.set_capture_ring_color,
        )

    def set_magnifier_border_color(self, color: Color):
        self.mutations.set_viewport_color(
            "magnifier_border_color",
            color,
            setting_key="magnifier_border_color",
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def set_magnifier_laser_color(self, color: Color):
        self.mutations.set_viewport_color(
            "magnifier_laser_color",
            color,
            setting_key="magnifier_laser_color",
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def set_capture_ring_color(self, color: Color):
        self.mutations.set_viewport_color(
            "capture_ring_color",
            color,
            setting_key="capture_ring_color",
            invalidate_render_cache=True,
            request_core_update=True,
        )

    def set_ui_mode(self, mode: str):

        if mode == "advanced":

            saved_mode = self.settings_manager._load_setting("ui_mode", "beginner")
            if saved_mode == "expert":
                mode = "expert"

        if mode not in ("beginner", "advanced", "expert", "minimal"):
            logger.warning(f"Invalid UI mode: {mode}, using 'beginner'")
            mode = "beginner"

        if getattr(self.store.settings, "ui_mode", "beginner") != mode:
            self.mutations.set_settings_value(
                "ui_mode",
                mode,
                setting_key="ui_mode",
                emit_scope="settings",
            )
            self.notifier.emit_ui_mode_changed(mode)

    def on_change_language(self, event: SettingsChangeLanguageEvent):
        self.change_language(event.lang_code)

    def on_toggle_include_filenames_in_saved(
        self, event: SettingsToggleIncludeFilenamesInSavedEvent
    ):
        self.toggle_include_filenames_in_saved(event.include)

    def on_apply_font_settings(self, event: SettingsApplyFontSettingsEvent):
        self.apply_font_settings(
            event.size,
            event.weight,
            event.color,
            event.bg_color,
            event.draw_bg,
            event.placement,
            event.alpha,
        )

    def on_toggle_divider_line_visibility(
        self, event: SettingsToggleDividerLineVisibilityEvent
    ):
        self.toggle_divider_line_visibility(event.visible)

    def on_set_divider_line_color(self, event: SettingsSetDividerLineColorEvent):
        self.set_divider_line_color(event.color)

    def on_toggle_magnifier_divider_visibility(
        self, event: SettingsToggleMagnifierDividerVisibilityEvent
    ):
        self.toggle_magnifier_divider_visibility(event.visible)

    def on_set_magnifier_divider_color(
        self, event: SettingsSetMagnifierDividerColorEvent
    ):
        self.set_magnifier_divider_color(event.color)

    def on_toggle_auto_crop_black_borders(
        self, event: SettingsToggleAutoCropBlackBordersEvent
    ):
        self.toggle_auto_crop_black_borders(event.enabled)

    def on_set_divider_line_thickness(
        self, event: SettingsSetDividerLineThicknessEvent
    ):
        self.set_divider_line_thickness(event.thickness)

    def on_set_magnifier_divider_thickness(
        self, event: SettingsSetMagnifierDividerThicknessEvent
    ):
        self.set_magnifier_divider_thickness(event.thickness)
