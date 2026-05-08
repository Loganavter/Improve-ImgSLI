from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.action_base import Action
from core.store_viewport import RenderConfig, ViewState
from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor

from ui.canvas_infra.scene.widget_contract import CanvasFeatureProperty, CanvasWidgetFeature

from .actions import SetCaptureColorAction, SetCaptureVisibleAction
from .state import CaptureWidgetState, get_capture_widget_state, replace_capture_widget_state

def reduce_capture_view_state(view_state: ViewState, action: Action) -> ViewState:
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
    bool_channels = (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),)
    color_channels = (
        ChannelDescriptor("r", "R", "color"),
        ChannelDescriptor("g", "G", "color"),
        ChannelDescriptor("b", "B", "color"),
        ChannelDescriptor("a", "A", "color"),
    )
    return (
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

def build_capture_commands() -> dict[str, Any]:
    return {
        "render.canvas_payload": _command_build_render_canvas_payload,
    }

WIDGET_FEATURE = CanvasWidgetFeature(
    name="capture",
    reduce_view_state=reduce_capture_view_state,
    reduce_render_config=reduce_capture_render_config,
    build_properties=build_capture_properties,
    build_commands=build_capture_commands,
    reducer_order=30,
    property_order=30,
)
