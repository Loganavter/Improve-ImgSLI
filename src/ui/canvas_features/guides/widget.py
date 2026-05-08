from __future__ import annotations

from dataclasses import replace
from typing import Any

from core.state_management.action_base import Action
from core.store_viewport import RenderConfig, ViewState
from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor, TrackDescriptor

from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureProperty,
    CanvasWidgetFeature,
)

from .actions import (
    SetGuidesColorAction,
    SetGuidesEnabledAction,
    SetGuidesSmoothingEnabledAction,
    SetGuidesSmoothingInterpolationMethodAction,
    SetGuidesThicknessAction,
)
from .state import GuidesWidgetState, get_guides_widget_state, replace_guides_widget_state

def reduce_guides_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetGuidesEnabledAction):
        state = get_guides_widget_state(view_state).clone()
        state.enabled = bool(action.enabled)
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesThicknessAction):
        state = get_guides_widget_state(view_state).clone()
        state.thickness = max(0, int(action.thickness))
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesColorAction):
        state = get_guides_widget_state(view_state).clone()
        state.color = action.color
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesSmoothingEnabledAction):
        state = get_guides_widget_state(view_state).clone()
        state.smoothing_enabled = bool(action.enabled)
        return replace_guides_widget_state(view_state, state)
    if isinstance(action, SetGuidesSmoothingInterpolationMethodAction):
        state = get_guides_widget_state(view_state).clone()
        state.smoothing_interpolation_method = str(action.method)
        return replace_guides_widget_state(view_state, state)
    return view_state

def reduce_guides_render_config(config: RenderConfig, action: Action) -> RenderConfig:
    return config

def _set_snapshot_guides_state(snap, state: GuidesWidgetState) -> None:
    view_state = snap.viewport_state.view_state
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["guides"] = state
    view_state.canvas_widget_state = canvas_widget_state

def _track_descriptor(track_id: str, label: str, kind: str) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
        "enum": (ChannelDescriptor("value", "Value", "enum", interpolate_values=False),),
        "color": (
            ChannelDescriptor("r", "R", "color"),
            ChannelDescriptor("g", "G", "color"),
            ChannelDescriptor("b", "B", "color"),
            ChannelDescriptor("a", "A", "color"),
        ),
    }
    return TrackDescriptor(id=track_id, label=label, kind=kind, channels=defaults[kind])

def build_guides_properties() -> tuple[CanvasFeatureProperty, ...]:
    enabled = _track_descriptor("lasers.enabled", "Enabled", "bool")
    thickness = _track_descriptor("lasers.thickness", "Thickness", "scalar")
    color = _track_descriptor("lasers.color", "Color", "color")
    smoothing = _track_descriptor("lasers.smoothing.enabled", "Smoothing", "bool")
    interpolation = _track_descriptor("lasers.smoothing.interpolation_method", "Smoothing Interpolation", "enum")
    return (
        CanvasFeatureProperty(
            id=enabled.id,
            label=enabled.label,
            kind=enabled.kind,
            channels=enabled.channels,
            group_id="guides",
            group_label="Guides",
            setting_key="guides.enabled",
            read_snapshot=lambda snap: {"value": bool(get_guides_widget_state(snap.viewport_state.view_state).enabled)},
            write_snapshot=lambda snap, ch: _set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    enabled=bool(ch["value"]),
                ),
            ),
            order=20,
        ),
        CanvasFeatureProperty(
            id=thickness.id,
            label=thickness.label,
            kind=thickness.kind,
            channels=thickness.channels,
            group_id="guides",
            group_label="Guides",
            setting_key="guides.thickness",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {"value": float(get_guides_widget_state(snap.viewport_state.view_state).thickness)},
            write_snapshot=lambda snap, ch: _set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    thickness=max(0, int(float(ch["value"]))),
                ),
            ),
            order=21,
        ),
        CanvasFeatureProperty(
            id=color.id,
            label=color.label,
            kind=color.kind,
            channels=color.channels,
            group_id="guides",
            group_label="Guides",
            setting_key="guides.color",
            read_snapshot=lambda snap: {
                "r": int(get_guides_widget_state(snap.viewport_state.view_state).color.r),
                "g": int(get_guides_widget_state(snap.viewport_state.view_state).color.g),
                "b": int(get_guides_widget_state(snap.viewport_state.view_state).color.b),
                "a": int(get_guides_widget_state(snap.viewport_state.view_state).color.a),
            },
            write_snapshot=lambda snap, ch: _set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    color=Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
                ),
            ),
            order=22,
        ),
        CanvasFeatureProperty(
            id=smoothing.id,
            label=smoothing.label,
            kind=smoothing.kind,
            channels=smoothing.channels,
            group_id="guides",
            group_label="Guides",
            setting_key="guides.smoothing.enabled",
            read_snapshot=lambda snap: {"value": bool(get_guides_widget_state(snap.viewport_state.view_state).smoothing_enabled)},
            write_snapshot=lambda snap, ch: _set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    smoothing_enabled=bool(ch["value"]),
                ),
            ),
            order=23,
        ),
        CanvasFeatureProperty(
            id=interpolation.id,
            label=interpolation.label,
            kind=interpolation.kind,
            channels=interpolation.channels,
            group_id="guides",
            group_label="Guides",
            setting_key="guides.smoothing.interpolation_method",
            read_snapshot=lambda snap: {"value": get_guides_widget_state(snap.viewport_state.view_state).smoothing_interpolation_method},
            write_snapshot=lambda snap, ch: _set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    smoothing_interpolation_method=str(ch["value"]),
                ),
            ),
            order=24,
        ),
    )

def _command_build_render_canvas_payload(store) -> dict[str, Any]:
    viewport = getattr(store, "viewport", None)
    if viewport is None:
        return {
            "enabled": False,
            "thickness": 1,
            "color": (255, 255, 255, 255),
            "smoothing_enabled": False,
            "smoothing_interpolation_method": "BILINEAR",
        }
    state = get_guides_widget_state(viewport.view_state)
    color = state.color
    return {
        "enabled": bool(state.enabled),
        "thickness": int(state.thickness),
        "color": (int(color.r), int(color.g), int(color.b), int(color.a)),
        "smoothing_enabled": bool(state.smoothing_enabled),
        "smoothing_interpolation_method": str(state.smoothing_interpolation_method),
    }

def build_guides_commands() -> dict[str, Any]:
    return {
        "render.canvas_payload": _command_build_render_canvas_payload,
    }

WIDGET_FEATURE = CanvasWidgetFeature(
    name="guides",
    reduce_view_state=reduce_guides_view_state,
    reduce_render_config=reduce_guides_render_config,
    build_properties=build_guides_properties,
    build_commands=build_guides_commands,
    reducer_order=20,
    property_order=20,
)
