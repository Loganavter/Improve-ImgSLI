from __future__ import annotations

from typing import Any

from core.events import (
    SettingsApplyFontSettingsEvent,
    SettingsChangeLanguageEvent,
    SettingsToggleAutoCropBlackBordersEvent,
    SettingsToggleIncludeFilenamesInSavedEvent,
)
from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IServicePlugin, IUIPlugin
from plugins.settings.controller import SettingsController
from plugins.settings.manager import SettingsManager
from ui.canvas_features.magnifier.events import (
    SettingsSetMagnifierDividerColorEvent,
    SettingsSetMagnifierDividerThicknessEvent,
    SettingsToggleMagnifierDividerVisibilityEvent,
)
from ui.canvas_infra.scene.widget_registry import (
    get_canvas_feature_settings_event_bindings,
)

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
            self.controller = SettingsController(
                self.store, self.settings_manager, event_bus=self.event_bus
            )

        if self.event_bus and self.controller:
            def _run_canvas_feature_command(feature_name: str, command_id: str, *args):
                self.controller.execute_canvas_feature_command(
                    feature_name,
                    command_id,
                    *args,
                )

            self.event_bus.subscribe(
                SettingsChangeLanguageEvent, self.controller.on_change_language
            )
            self.event_bus.subscribe(
                SettingsToggleIncludeFilenamesInSavedEvent,
                self.controller.on_toggle_include_filenames_in_saved,
            )
            self.event_bus.subscribe(
                SettingsApplyFontSettingsEvent, self.controller.on_apply_font_settings
            )
            self.event_bus.subscribe(
                SettingsToggleMagnifierDividerVisibilityEvent,
                self.controller.on_toggle_magnifier_divider_visibility,
            )
            self.event_bus.subscribe(
                SettingsSetMagnifierDividerColorEvent,
                self.controller.on_set_magnifier_divider_color,
            )
            self.event_bus.subscribe(
                SettingsToggleAutoCropBlackBordersEvent,
                self.controller.on_toggle_auto_crop_black_borders,
            )
            self.event_bus.subscribe(
                SettingsSetMagnifierDividerThicknessEvent,
                self.controller.on_set_magnifier_divider_thickness,
            )
            for feature_name, bindings in get_canvas_feature_settings_event_bindings().items():
                for binding in bindings:
                    self.event_bus.subscribe(
                        binding.event_type,
                        lambda event, feature_name=feature_name, binding=binding: _run_canvas_feature_command(
                            feature_name,
                            binding.command_id,
                            *binding.extract_args(event),
                        ),
                    )

    def get_qss_paths(self) -> tuple[str, ...]:
        return (self.plugin_resource_path("resources", "settings.qss"),)

    def get_controller(self) -> SettingsController | None:
        return self.controller

    def get_service(self) -> SettingsManager | None:
        return self.settings_manager

    def provides_capability(self, capability: str) -> bool:
        return capability == "settings_management"

    def bind_window_shell(self, window_shell: Any) -> None:
        if self.controller:
            if hasattr(window_shell, "get_feature"):
                self.controller.presenter = window_shell.get_feature("settings")
            else:
                self.controller.presenter = window_shell

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if not self.controller:
            raise RuntimeError("Settings controller is not initialized")
        target = getattr(self.controller, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Settings controller has no command '{command}'")
