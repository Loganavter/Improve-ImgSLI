from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IUIPlugin, IServicePlugin
from core.events import (
    SettingsChangeLanguageEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
    SettingsApplyFontSettingsEvent,
    SettingsToggleDividerLineVisibilityEvent,
    SettingsSetDividerLineColorEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
    SettingsSetMagnifierDividerColorEvent,
    SettingsToggleAutoCropBlackBordersEvent,
    SettingsSetDividerLineThicknessEvent,
    SettingsSetMagnifierDividerThicknessEvent,
)
from plugins.settings.controller import SettingsController
from plugins.settings.manager import SettingsManager

@plugin(name="settings", version="1.0")
class SettingsPlugin(Plugin, IUIPlugin, IServicePlugin):
    capabilities = ("settings_management",)

    def __init__(self):
        super().__init__()
        self.controller: SettingsController | None = None
        self.settings_manager: SettingsManager | None = None
        self.event_bus: Any | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.settings_manager = getattr(context, "settings_manager", None)
        self.event_bus = getattr(context, "event_bus", None)
        if self.store and self.settings_manager:
            self.controller = SettingsController(self.store, self.settings_manager, event_bus=self.event_bus)

        if self.event_bus and self.controller:

            self.event_bus.subscribe(SettingsChangeLanguageEvent, self.controller.on_change_language)
            self.event_bus.subscribe(SettingsToggleIncludeFilenamesInSavedEvent, self.controller.on_toggle_include_filenames_in_saved)
            self.event_bus.subscribe(SettingsApplyFontSettingsEvent, self.controller.on_apply_font_settings)
            self.event_bus.subscribe(SettingsToggleDividerLineVisibilityEvent, self.controller.on_toggle_divider_line_visibility)
            self.event_bus.subscribe(SettingsSetDividerLineColorEvent, self.controller.on_set_divider_line_color)
            self.event_bus.subscribe(SettingsToggleMagnifierDividerVisibilityEvent, self.controller.on_toggle_magnifier_divider_visibility)
            self.event_bus.subscribe(SettingsSetMagnifierDividerColorEvent, self.controller.on_set_magnifier_divider_color)
            self.event_bus.subscribe(SettingsToggleAutoCropBlackBordersEvent, self.controller.on_toggle_auto_crop_black_borders)
            self.event_bus.subscribe(SettingsSetDividerLineThicknessEvent, self.controller.on_set_divider_line_thickness)
            self.event_bus.subscribe(SettingsSetMagnifierDividerThicknessEvent, self.controller.on_set_magnifier_divider_thickness)

    def get_controller(self) -> SettingsController | None:
        return self.controller

    def get_service(self) -> SettingsManager | None:
        return self.settings_manager

    def provides_capability(self, capability: str) -> bool:
        return capability == "settings_management"

    def set_presenter(self, presenter: Any) -> None:
        if self.controller:
            self.controller.presenter = presenter

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if not self.controller:
            raise RuntimeError("Settings controller is not initialized")
        target = getattr(self.controller, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Settings controller has no command '{command}'")

