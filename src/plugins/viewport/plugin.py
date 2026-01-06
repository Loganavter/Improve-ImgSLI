from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin
from core.plugin_system.ui_integration import get_plugin_name
from core.events import (
    ViewportSetSplitPositionEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportUpdateMovementSpeedEvent,
    ViewportSetMagnifierPositionEvent,
    ViewportSetMagnifierInternalSplitEvent,
    ViewportToggleMagnifierPartEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
    ViewportToggleOrientationEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportToggleMagnifierEvent,
)
from plugins.viewport.controller import ViewportController
from plugins.viewport.state import ViewportState as ViewportPluginState

@plugin(name="viewport", version="1.0")
class ViewportPlugin(Plugin, IControllablePlugin):
    capabilities = ("viewport", "magnifier")

    def __init__(self):
        super().__init__()
        self.controller: ViewportController | None = None
        self.store: Any | None = None
        self._magnifier_plugin: Any | None = None
        self.event_bus: Any | None = None
        self._domain_state: ViewportPluginState | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        coordinator = getattr(context, "plugin_coordinator", None)
        self._magnifier_plugin = coordinator.get_plugin("magnifier") if coordinator else None

        if self.store:
            self._domain_state = ViewportPluginState()
            self.store.viewport.set_viewport_plugin_state(self._domain_state)
            self.controller = ViewportController(self.store, self._magnifier_plugin, self.event_bus)
        ui_registry = getattr(context, "plugin_ui_registry", None)
        if ui_registry and self.controller:
            ui_registry.register_action(
                get_plugin_name(self),
                "toggle_magnifier",
                self.controller.toggle_magnifier,
            )

        if self.event_bus and self.controller:

            self.event_bus.subscribe(ViewportSetSplitPositionEvent, self.controller.on_set_split_position)
            self.event_bus.subscribe(ViewportUpdateMagnifierSizeRelativeEvent, self.controller.on_update_magnifier_size_relative)
            self.event_bus.subscribe(ViewportUpdateCaptureSizeRelativeEvent, self.controller.on_update_capture_size_relative)
            self.event_bus.subscribe(ViewportUpdateMovementSpeedEvent, self.controller.on_update_movement_speed)
            self.event_bus.subscribe(ViewportSetMagnifierPositionEvent, self.controller.on_set_magnifier_position)
            self.event_bus.subscribe(ViewportSetMagnifierInternalSplitEvent, self.controller.on_set_magnifier_internal_split)
            self.event_bus.subscribe(ViewportToggleMagnifierPartEvent, self.controller.on_toggle_magnifier_part)
            self.event_bus.subscribe(ViewportUpdateMagnifierCombinedStateEvent, self.controller.on_update_magnifier_combined_state)
            self.event_bus.subscribe(ViewportToggleOrientationEvent, self.controller.on_toggle_orientation)
            self.event_bus.subscribe(ViewportToggleMagnifierOrientationEvent, self.controller.on_toggle_magnifier_orientation)
            self.event_bus.subscribe(ViewportToggleFreezeMagnifierEvent, self.controller.on_toggle_freeze_magnifier)
            self.event_bus.subscribe(ViewportOnSliderPressedEvent, self.controller._handle_slider_pressed_event)
            self.event_bus.subscribe(ViewportOnSliderReleasedEvent, self.controller._handle_slider_released_event)
            self.event_bus.subscribe(ViewportSetMagnifierVisibilityEvent, self.controller.on_set_magnifier_visibility)
            self.event_bus.subscribe(ViewportToggleMagnifierEvent, self.controller.on_toggle_magnifier)

    def get_controller(self) -> ViewportController | None:
        return self.controller

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if not self.controller:
            raise RuntimeError("Viewport controller is not initialized")
        target = getattr(self.controller, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Viewport controller has no command '{command}'")

