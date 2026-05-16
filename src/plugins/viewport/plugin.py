from __future__ import annotations

from typing import Any

from core.plugin_system import Plugin, plugin
from core.plugin_system.interfaces import IControllablePlugin, IVideoTrackProvider
from core.plugin_system.ui_integration import get_plugin_name
from plugins.viewport.controller import ViewportController
from plugins.viewport.definition import build_plugin_definition
from plugins.viewport.events import (
    ViewportOnSliderPressedEvent,
    ViewportOnSliderReleasedEvent,
    ViewportSetMagnifierInternalSplitEvent,
    ViewportSetMagnifierPositionEvent,
    ViewportSetMagnifierVisibilityEvent,
    ViewportSetSplitPositionEvent,
    ViewportToggleFreezeMagnifierEvent,
    ViewportToggleMagnifierEvent,
    ViewportToggleMagnifierLaserEvent,
    ViewportToggleMagnifierOrientationEvent,
    ViewportToggleMagnifierPartEvent,
    ViewportToggleOrientationEvent,
    ViewportUpdateCaptureSizeRelativeEvent,
    ViewportUpdateMagnifierCombinedStateEvent,
    ViewportUpdateMagnifierSizeRelativeEvent,
    ViewportUpdateMovementSpeedEvent,
)
from plugins.viewport.state import ViewportState as ViewportPluginState
from plugins.video_editor.services.keyframing import (
    ChannelDescriptor,
    KeyframeToolAdapter,
    StaticToolAdapter,
    StaticToolBinding,
    StaticTrackBinding,
    ToolDescriptor,
    TrackDescriptor,
)
from plugins.video_editor.services.keyframing.types import FrameSnapshot
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

def _store_proxy(viewport):
    return type("StoreProxy", (), {"viewport": viewport})()

def _execute_magnifier_command(store, command_id: str, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(command_id)
    if command is None:
        return None
    return command(store, *args, **kwargs)

def _query_magnifier(store, query_id: str, default=None, *args, **kwargs):
    command = get_canvas_feature_command_by_alias(query_id)
    if command is None:
        return default
    result = command(store, *args, **kwargs)
    return default if result is None else result

def _active_magnifier_state(viewport):
    return _query_magnifier(_store_proxy(viewport), "overlay.active_state")

def _read_active_magnifier_freeze(snapshot: FrameSnapshot):
    magnifier = _active_magnifier_state(snapshot.viewport_state)
    return {"value": bool(magnifier["freeze"]) if magnifier is not None else False}

def _write_active_magnifier_freeze(snapshot: FrameSnapshot, channels):
    _execute_magnifier_command(
        _store_proxy(snapshot.viewport_state),
        "overlay.set_active_freeze",
        bool(channels["value"]),
    )

def _read_active_magnifier_combined(snapshot: FrameSnapshot):
    return {
        "value": bool(
            _query_magnifier(_store_proxy(snapshot.viewport_state), "overlay.active_combined", False)
        )
    }

def _write_active_magnifier_combined(snapshot: FrameSnapshot, channels):
    _execute_magnifier_command(
        _store_proxy(snapshot.viewport_state),
        "overlay.set_active_combined",
        bool(channels["value"]),
    )

def _read_magnifier_movement_speed(snapshot: FrameSnapshot):
    return {"value": float(snapshot.viewport_state.view_state.movement_speed_per_sec)}

def _write_magnifier_movement_speed(snapshot: FrameSnapshot, channels):
    snapshot.viewport_state.view_state.movement_speed_per_sec = float(channels["value"])

def _read_magnifier_movement_optimized(snapshot: FrameSnapshot):
    return {"value": bool(snapshot.viewport_state.view_state.optimize_interactive_movement)}

def _write_magnifier_movement_optimized(snapshot: FrameSnapshot, channels):
    snapshot.viewport_state.view_state.optimize_interactive_movement = bool(
        channels["value"]
    )

def _build_keyframe_adapter() -> StaticToolAdapter:
    tool = ToolDescriptor(
        id="viewport.magnifier_runtime",
        tool_type="magnifier_runtime",
        label="Magnifier Runtime",
        group_id="magnifier.runtime",
        group_label="Magnifier Runtime",
        subclass_id="runtime",
        subclass_label="Runtime",
        tracks=(
            TrackDescriptor(
                id="magnifier.default.freeze",
                label="Freeze",
                kind="bool",
                channels=(ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
            ),
            TrackDescriptor(
                id="magnifier.default.combined",
                label="Combined",
                kind="bool",
                channels=(ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
            ),
            TrackDescriptor(
                id="magnifier.movement.speed",
                label="Speed",
                kind="scalar",
                channels=(ChannelDescriptor("value", "Value", "scalar"),),
            ),
            TrackDescriptor(
                id="magnifier.movement.optimized",
                label="Optimized",
                kind="bool",
                channels=(ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
            ),
        ),
    )
    return StaticToolAdapter(
        adapter_id="viewport.magnifier_runtime",
        tools=(
            StaticToolBinding(
                descriptor=tool,
                tracks=(
                    StaticTrackBinding(tool.tracks[0], _read_active_magnifier_freeze, _write_active_magnifier_freeze),
                    StaticTrackBinding(tool.tracks[1], _read_active_magnifier_combined, _write_active_magnifier_combined),
                    StaticTrackBinding(tool.tracks[2], _read_magnifier_movement_speed, _write_magnifier_movement_speed),
                    StaticTrackBinding(tool.tracks[3], _read_magnifier_movement_optimized, _write_magnifier_movement_optimized),
                ),
            ),
        ),
    )

@plugin(name="viewport", version="1.0")
class ViewportPlugin(Plugin, IControllablePlugin, IVideoTrackProvider):
    capabilities = ("viewport", "magnifier")

    def __init__(self):
        super().__init__()
        self.controller: ViewportController | None = None
        self.store: Any | None = None
        self.event_bus: Any | None = None
        self._domain_state: ViewportPluginState | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        if self.store:
            self._domain_state = ViewportPluginState()
            self.store.viewport.set_viewport_plugin_state(self._domain_state)
            self.controller = ViewportController(
                self.store,
                self.event_bus,
                settings_manager=getattr(context, "settings_manager", None),
            )
        ui_registry = getattr(context, "plugin_ui_registry", None)
        if ui_registry and self.controller:
            ui_registry.register_action(
                get_plugin_name(self),
                "toggle_magnifier",
                self.controller.toggle_magnifier,
            )

        if self.event_bus and self.controller:

            self.event_bus.subscribe(
                ViewportSetSplitPositionEvent, self.controller.on_set_split_position
            )
            self.event_bus.subscribe(
                ViewportUpdateMagnifierSizeRelativeEvent,
                self.controller.on_update_magnifier_size_relative,
            )
            self.event_bus.subscribe(
                ViewportUpdateCaptureSizeRelativeEvent,
                self.controller.on_update_capture_size_relative,
            )
            self.event_bus.subscribe(
                ViewportUpdateMovementSpeedEvent,
                self.controller.on_update_movement_speed,
            )
            self.event_bus.subscribe(
                ViewportSetMagnifierPositionEvent,
                self.controller.on_set_magnifier_position,
            )
            self.event_bus.subscribe(
                ViewportSetMagnifierInternalSplitEvent,
                self.controller.on_set_magnifier_internal_split,
            )
            self.event_bus.subscribe(
                ViewportToggleMagnifierPartEvent,
                self.controller.on_toggle_magnifier_part,
            )
            self.event_bus.subscribe(
                ViewportToggleMagnifierLaserEvent,
                self.controller.on_toggle_magnifier_laser,
            )
            self.event_bus.subscribe(
                ViewportUpdateMagnifierCombinedStateEvent,
                self.controller.on_update_magnifier_combined_state,
            )
            self.event_bus.subscribe(
                ViewportToggleOrientationEvent, self.controller.on_toggle_orientation
            )
            self.event_bus.subscribe(
                ViewportToggleMagnifierOrientationEvent,
                self.controller.on_toggle_magnifier_orientation,
            )
            self.event_bus.subscribe(
                ViewportToggleFreezeMagnifierEvent,
                self.controller.on_toggle_freeze_magnifier,
            )
            self.event_bus.subscribe(
                ViewportOnSliderPressedEvent,
                self.controller._handle_slider_pressed_event,
            )
            self.event_bus.subscribe(
                ViewportOnSliderReleasedEvent,
                self.controller._handle_slider_released_event,
            )
            self.event_bus.subscribe(
                ViewportSetMagnifierVisibilityEvent,
                self.controller.on_set_magnifier_visibility,
            )
            self.event_bus.subscribe(
                ViewportToggleMagnifierEvent, self.controller.on_toggle_magnifier
            )

    def get_controller(self) -> ViewportController | None:
        return self.controller

    def get_definition(self):
        return build_plugin_definition()

    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        if not self.controller:
            raise RuntimeError("Viewport controller is not initialized")
        target = getattr(self.controller, command, None)
        if callable(target):
            return target(*args, **kwargs)
        raise AttributeError(f"Viewport controller has no command '{command}'")

    def get_video_keyframe_adapters(self) -> tuple[KeyframeToolAdapter, ...]:
        return (_build_keyframe_adapter(),)
