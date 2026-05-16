from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.action_base import Action
from core.store_viewport import RenderConfig, ViewState
from domain.qt_adapters import color_to_qcolor
from domain.types import Color
from plugins.viewport.events import (
    ViewportUpdateCaptureSizeRelativeEvent,
)
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor

from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureCommandAlias,
    CanvasFeatureProperty,
    CanvasFeatureSettingsEventBinding,
    CanvasFeatureToolbarBinding,
    CanvasWidgetFeature,
)
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

from .actions import (
    SetCaptureColorAction,
    SetCaptureSizeRelativeAction,
    SetCaptureVisibleAction,
)
from .events import SettingsSetCaptureColorEvent, SettingsToggleCaptureVisibilityEvent
from .state import CaptureWidgetState, get_capture_widget_state, replace_capture_widget_state

def _make_overlay_view_state_proxy(view_state: ViewState):
    viewport_proxy = type(
        "ViewportProxy",
        (),
        {"view_state": view_state, "render_config": RenderConfig()},
    )()
    return type("StoreProxy", (), {"viewport": viewport_proxy})()

def _capture_size_from_overlay(view_state: ViewState) -> float:
    store_proxy = _make_overlay_view_state_proxy(view_state)
    query = get_canvas_feature_command_by_alias("overlay.active_capture_size")
    if query is not None:
        return float(query(store_proxy))
    return 0.1

def _set_capture_size_on_view_state(view_state: ViewState, size: float) -> ViewState:
    clamped = max(0.01, min(1.0, float(size)))
    store_proxy = _make_overlay_view_state_proxy(view_state)
    command = get_canvas_feature_command_by_alias("overlay.set_active_capture_size")
    if command is not None:
        command(store_proxy, clamped)
    return store_proxy.viewport.view_state

def reduce_capture_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetCaptureSizeRelativeAction):
        return _set_capture_size_on_view_state(view_state, action.size)
    if isinstance(action, SetCaptureVisibleAction):
        state = get_capture_widget_state(view_state).clone()
        state.visible = bool(action.enabled)
        return replace_capture_widget_state(view_state, state)
    if isinstance(action, SetCaptureColorAction):
        state = get_capture_widget_state(view_state).clone()
        state.color = action.color
        return replace_capture_widget_state(view_state, state)
    return view_state

def reduce_capture_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    return config

def _set_snapshot_capture_state(snap, state: CaptureWidgetState) -> None:
    view_state = snap.viewport_state.view_state
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["capture"] = state
    view_state.canvas_widget_state = canvas_widget_state

def build_capture_properties() -> tuple[CanvasFeatureProperty, ...]:
    scalar_channels = (ChannelDescriptor("value", "Value", "scalar"),)
    bool_channels = (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),)
    color_channels = (
        ChannelDescriptor("r", "R", "color"),
        ChannelDescriptor("g", "G", "color"),
        ChannelDescriptor("b", "B", "color"),
        ChannelDescriptor("a", "A", "color"),
    )
    return (
        CanvasFeatureProperty(
            id="capture.size",
            label="Size",
            kind="scalar",
            channels=scalar_channels,
            group_id="capture",
            group_label="Capture",
            setting_key="capture.size",
            read_snapshot=lambda snap: {
                "value": float(_capture_size_from_overlay(snap.viewport_state.view_state)),
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state,
                "view_state",
                _set_capture_size_on_view_state(
                    snap.viewport_state.view_state,
                    float(ch["value"]),
                ),
            ),
            order=29,
        ),
        CanvasFeatureProperty(
            id="capture.visible",
            label="Visible",
            kind="bool",
            channels=bool_channels,
            group_id="capture",
            group_label="Capture",
            setting_key="capture.visible",
            read_snapshot=lambda snap: {"value": bool(get_capture_widget_state(snap.viewport_state.view_state).visible)},
            write_snapshot=lambda snap, ch: _set_snapshot_capture_state(
                snap,
                replace(
                    get_capture_widget_state(snap.viewport_state.view_state).clone(),
                    visible=bool(ch["value"]),
                ),
            ),
            order=30,
        ),
        CanvasFeatureProperty(
            id="capture.color",
            label="Color",
            kind="color",
            channels=color_channels,
            group_id="capture",
            group_label="Capture",
            setting_key="capture.color",
            read_snapshot=lambda snap: {
                "r": int(get_capture_widget_state(snap.viewport_state.view_state).color.r),
                "g": int(get_capture_widget_state(snap.viewport_state.view_state).color.g),
                "b": int(get_capture_widget_state(snap.viewport_state.view_state).color.b),
                "a": int(get_capture_widget_state(snap.viewport_state.view_state).color.a),
            },
            write_snapshot=lambda snap, ch: _set_snapshot_capture_state(
                snap,
                replace(
                    get_capture_widget_state(snap.viewport_state.view_state).clone(),
                    color=Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
                ),
            ),
            order=31,
        ),
    )

def _command_build_render_canvas_payload(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {"visible": False, "color": (255, 50, 100, 230)}
    state = get_capture_widget_state(viewport.view_state)
    color = state.color
    return {
        "visible": bool(state.visible),
        "color": (int(color.r), int(color.g), int(color.b), int(color.a)),
    }

def _command_set_capture_size(actions, raw_value: int | float) -> None:
    relative_size = max(0.01, min(1.0, float(raw_value)))
    event_bus = getattr(actions, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportUpdateCaptureSizeRelativeEvent(relative_size))
        return
    main_controller = getattr(actions, "main_controller", None)
    if main_controller is not None and hasattr(main_controller, "execute_plugin_command"):
        main_controller.execute_plugin_command(
            "viewport",
            "update_capture_size_relative",
            relative_size,
        )

def _set_slider_value_quietly(slider, value: int) -> None:
    if slider is None or slider.value() == value:
        return
    old = slider.blockSignals(True)
    try:
        slider.setValue(value)
    finally:
        slider.blockSignals(old)

def _sync_capture_toolbar_state(presenter) -> None:
    slider = getattr(getattr(presenter, "ui", None), "slider_capture", None)
    if slider is None:
        return
    size = _capture_size_from_overlay(presenter.store.viewport.view_state)
    _set_slider_value_quietly(slider, int(size * 100))

def _capture_size_pressed_handler(presenter) -> None:
    from plugins.viewport.events import ViewportOnSliderPressedEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is not None:
        event_bus.emit(ViewportOnSliderPressedEvent("capture_size"))

def _capture_size_released_handler(presenter) -> None:
    from plugins.viewport.events import ViewportOnSliderReleasedEvent

    event_bus = getattr(presenter, "event_bus", None)
    if event_bus is None:
        return
    event_bus.emit(
        ViewportOnSliderReleasedEvent(
            "capture_size_relative",
            lambda: _capture_size_from_overlay(presenter.store.viewport.view_state),
        )
    )

def build_capture_toolbar_bindings() -> tuple[CanvasFeatureToolbarBinding, ...]:
    return (
        CanvasFeatureToolbarBinding(
            control_id="capture.size",
            on_value_changed=lambda presenter, value: _command_set_capture_size(
                presenter,
                float(value) / 100.0,
            ),
            on_pressed=_capture_size_pressed_handler,
            on_released=_capture_size_released_handler,
            sync_state=_sync_capture_toolbar_state,
        ),
    )

def build_capture_commands() -> dict[str, Any]:
    return {
        "query.widget_state": lambda view_state: get_capture_widget_state(view_state),
        "settings.toggle_visibility": lambda settings, visible: settings.mutations.set_canvas_feature_setting(
            "capture.visible",
            bool(visible),
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "settings.set_color": lambda settings, color: settings.mutations.set_canvas_feature_setting(
            "capture.color",
            color,
            invalidate_render_cache=True,
            request_core_update=True,
        ),
        "toolbar.set_size": _command_set_capture_size,
        "render.canvas_payload": _command_build_render_canvas_payload,
    }

def build_capture_settings_event_bindings() -> tuple[CanvasFeatureSettingsEventBinding, ...]:
    return (
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsToggleCaptureVisibilityEvent,
            command_id="settings.toggle_visibility",
            extract_args=lambda event: (event.visible,),
        ),
        CanvasFeatureSettingsEventBinding(
            event_type=SettingsSetCaptureColorEvent,
            command_id="settings.set_color",
            extract_args=lambda event: (event.color,),
        ),
    )

def build_capture_render_scene_overrides(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {}
    state = get_capture_widget_state(viewport.view_state)
    return {
        "capture_color": color_to_qcolor(state.color),
        "show_capture": bool(state.visible),
    }

CAPTURE_COMMAND_ALIASES = (
    CanvasFeatureCommandAlias("capture.settings.toggle_visibility", "settings.toggle_visibility"),
    CanvasFeatureCommandAlias("capture.settings.set_color", "settings.set_color"),
    CanvasFeatureCommandAlias("capture.widget_state", "query.widget_state"),
)

def build_widget_feature() -> CanvasWidgetFeature:
    return CanvasWidgetFeature(
        name="capture",
        reduce_view_state=reduce_capture_view_state,
        reduce_render_config=reduce_capture_render_config,
        build_properties=build_capture_properties,
        build_toolbar_bindings=build_capture_toolbar_bindings,
        build_commands=build_capture_commands,
        command_aliases=CAPTURE_COMMAND_ALIASES,
        build_settings_event_bindings=build_capture_settings_event_bindings,
        build_render_scene_overrides=build_capture_render_scene_overrides,
        i18n_namespace="ui.tooltips",
        reducer_order=30,
        property_order=30,
    )

WIDGET_FEATURE = build_widget_feature()
