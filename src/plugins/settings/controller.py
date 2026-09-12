from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal

from plugins.settings.canvas_feature_gateway import (
    execute_canvas_feature_alias,
    execute_canvas_feature_command,
)
from plugins.settings.events import (
    SettingsApplyFontSettingsEvent,
    SettingsChangeLanguageEvent,
    SettingsToggleAutoCropBlackBordersEvent,
)
from plugins.settings.mutations import SettingsMutationService
from plugins.settings.notifier import SettingsUpdateNotifier

logger = logging.getLogger("ImproveImgSLI")

class SettingsController(QObject):

    update_requested = Signal()

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

    def change_language(self, lang_code: str):
        changed = self.mutations.set_settings_value(
            "current_language",
            lang_code,
            setting_key="language",
            emit_scope="settings",
        )
        if not changed:
            return

        from resources.translations import emit_language_changed

        emit_language_changed(lang_code)

        main_controller = getattr(self.presenter, "main_controller", None)
        window_shell = getattr(main_controller, "window_shell", None)
        if window_shell is not None and hasattr(window_shell, "on_language_changed"):
            window_shell.on_language_changed()
            return

        if self.presenter:
            self.presenter.on_language_changed()

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
        changed = self.mutations.apply_font_settings(
            size=max(1, int(size)),
            font_weight=max(0, int(font_weight)),
            color=color,
            bg_color=bg_color,
            draw_background=bool(draw_background),
            placement_mode=str(placement_mode),
            text_alpha_percent=max(0, min(100, int(text_alpha_percent))),
        )
        if not changed:
            return
        self.notifier.request_core_update()
        recorder = getattr(self.store, "recorder", None)
        if recorder is not None and getattr(recorder, "is_recording", False) and not getattr(recorder, "is_paused", False):
            recorder.capture_frame()

    def execute_canvas_feature_command(
        self,
        feature_name: str,
        command_id: str,
        *args,
    ):
        return execute_canvas_feature_command(feature_name, command_id, self, *args)

    def execute_canvas_feature_alias(self, alias: str, *args):
        return execute_canvas_feature_alias(alias, self, *args)

    def toggle_auto_crop_black_borders(self, enabled: bool):
        self.mutations.set_settings_value(
            "auto_crop_black_borders",
            enabled,
            setting_key="auto_crop_black_borders",
            emit_scope="settings",
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

    def on_toggle_auto_crop_black_borders(
        self, event: SettingsToggleAutoCropBlackBordersEvent
    ):
        self.toggle_auto_crop_black_borders(event.enabled)
