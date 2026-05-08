from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from core.state_management.action_base import Action
from core.state_management.viewport_actions import (
    SetActiveMagnifierIdAction,
    SetCaptureSizeRelativeAction,
    SetHighlightedMagnifierElementAction,
    SetMagnifierInternalSplitAction,
    SetMagnifierOffsetRelativeAction,
    SetMagnifierOffsetRelativeVisualAction,
    SetMagnifierPositionAction,
    SetMagnifierSizeRelativeAction,
    SetMagnifierSpacingRelativeAction,
    SetMagnifierSpacingRelativeVisualAction,
    SetMagnifierVisibilityAction,
    SetOptimizeMagnifierMovementAction,
    ToggleFreezeMagnifierAction,
    ToggleMagnifierAction,
    ToggleMagnifierOrientationAction,
    UpdateMagnifierCombinedStateAction,
)
from core.store_viewport import MagnifierModel, ViewState, ViewportState
from domain.types import Color, Point
from plugins.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    TrackDescriptor,
)
from plugins.video_editor.services.keyframing.types import FrameSnapshot

from ui.canvas_features.capture.state import get_capture_widget_state
from ui.canvas_features.guides.state import get_guides_widget_state
from .state import clone_magnifier_widget_state, get_magnifier_widget_state
from ui.canvas_infra.scene.widget_contract import (
    CanvasFeatureProperty,
    CanvasWidgetFeature,
)

class _ViewportProxy:
    def __init__(self, viewport: ViewportState):
        self.viewport = viewport

def _active_magnifier_id(view_state: ViewState) -> str:
    return get_magnifier_widget_state(view_state).active_id or "default"

def _ensure_active_magnifier_model(view_state: ViewState):
    state = clone_magnifier_widget_state(view_state)
    magnifiers = state.models
    active_id = _active_magnifier_id(view_state)
    model = magnifiers.get(active_id)
    if model is None:
        model = MagnifierModel(
            id=active_id,
            divider_color=state.default_divider_color,
            border_color=state.default_border_color,
            capture_ring_color=get_capture_widget_state(view_state).color,
            laser_color=get_guides_widget_state(view_state).color,
            divider_visible=state.default_divider_visible,
            divider_thickness=state.default_divider_thickness,
        )
    magnifiers[active_id] = model
    state.active_id = active_id
    return state, active_id, magnifiers, model

def _replace_widget_state(view_state: ViewState, state) -> ViewState:
    canvas_widget_state = dict(view_state.canvas_widget_state)
    canvas_widget_state["magnifier"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)

def reduce_magnifier_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetMagnifierSizeRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.size_relative = action.size
        magnifiers[active_id] = model
        state.default_size_relative = action.size
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetCaptureSizeRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.capture_size_relative = action.size
        magnifiers[active_id] = model
        state.default_capture_size_relative = action.size
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleMagnifierAction):
        state = clone_magnifier_widget_state(view_state)
        state.enabled = bool(action.enabled)
        if action.enabled and not state.active_id:
            state.active_id = "default"
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierVisibilityAction):
        payload = action.get_payload()
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        if payload.get("left") is not None:
            model.visible_left = payload["left"]
        if payload.get("center") is not None:
            model.visible_center = payload["center"]
        if payload.get("right") is not None:
            model.visible_right = payload["right"]
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleMagnifierOrientationAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.is_horizontal = action.is_horizontal
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleFreezeMagnifierAction):
        payload = action.get_payload()
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.freeze = payload["freeze"]
        model.frozen_position = payload.get("frozen_position")
        if payload.get("new_offset") is not None:
            model.offset_relative = payload["new_offset"]
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierPositionAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.position = action.position
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierInternalSplitAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.internal_split = max(0.0, min(1.0, action.split))
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, UpdateMagnifierCombinedStateAction):
        return view_state
    if isinstance(action, SetActiveMagnifierIdAction):
        state = clone_magnifier_widget_state(view_state)
        state.active_id = action.magnifier_id
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierOffsetRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.offset_relative = action.offset
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierSpacingRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.spacing_relative = action.spacing
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierOffsetRelativeVisualAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.offset_relative = action.offset
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierSpacingRelativeVisualAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.spacing_relative = action.spacing
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetOptimizeMagnifierMovementAction):
        state = clone_magnifier_widget_state(view_state)
        canvas_widget_state = dict(view_state.canvas_widget_state)
        canvas_widget_state["magnifier"] = state
        return replace(view_state, optimize_magnifier_movement=action.enabled, canvas_widget_state=canvas_widget_state)
    if isinstance(action, SetHighlightedMagnifierElementAction):
        return replace(view_state, highlighted_magnifier_element=action.element)
    return view_state

def reduce_magnifier_render_config(config, action: Action):
    return config

def _magnifier_model(viewport: ViewportState):
    from ui.canvas_features.magnifier.store import MagnifierStoreService

    return MagnifierStoreService(_ViewportProxy(viewport)).get_active_or_first_magnifier()

def _track_descriptor(
    track_id: str,
    label: str,
    kind: str,
    *,
    channels: tuple[ChannelDescriptor, ...] | None = None,
) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (ChannelDescriptor("value", "Value", "bool", interpolate_values=False),),
        "vec2": (
            ChannelDescriptor("x", "X", "scalar"),
            ChannelDescriptor("y", "Y", "scalar"),
        ),
        "color": (
            ChannelDescriptor("r", "R", "color"),
            ChannelDescriptor("g", "G", "color"),
            ChannelDescriptor("b", "B", "color"),
            ChannelDescriptor("a", "A", "color"),
        ),
        "mask3": (
            ChannelDescriptor("left", "Left", "bool", interpolate_values=False),
            ChannelDescriptor("center", "Center", "bool", interpolate_values=False),
            ChannelDescriptor("right", "Right", "bool", interpolate_values=False),
        ),
    }
    return TrackDescriptor(id=track_id, label=label, kind=kind, channels=channels or defaults[kind])

def _read_magnifier_position(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    point = model.position if model is not None else Point(0.5, 0.5)
    return {"x": float(point.x), "y": float(point.y)}

def _write_magnifier_position(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    if model is None:
        return
    model.position = Point(float(channels["x"]), float(channels["y"]))

def _read_magnifier_internal_split(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    return {"value": float(model.internal_split) if model is not None else 0.5}

def _write_magnifier_internal_split(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    if model is None:
        return
    model.internal_split = float(channels["value"])

def _read_magnifier_size(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        return {"value": float(model.size_relative)}
    return {"value": float(get_magnifier_widget_state(snapshot.viewport_state.view_state).default_size_relative)}

def _write_magnifier_size(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    value = float(channels["value"])
    get_magnifier_widget_state(snapshot.viewport_state.view_state).default_size_relative = value
    if model is None:
        return
    model.size_relative = value

def _read_capture_size(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        return {"value": float(model.capture_size_relative)}
    return {"value": float(get_magnifier_widget_state(snapshot.viewport_state.view_state).default_capture_size_relative)}

def _write_capture_size(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    value = float(channels["value"])
    get_magnifier_widget_state(snapshot.viewport_state.view_state).default_capture_size_relative = value
    if model is None:
        return
    model.capture_size_relative = value

def _read_magnifier_orientation(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    return {"value": bool(model.is_horizontal) if model is not None else False}

def _write_magnifier_orientation(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    if model is None:
        return
    model.is_horizontal = bool(channels["value"])

def _read_magnifier_visibility(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is None:
        return {"left": True, "center": True, "right": True}
    return {
        "left": bool(model.visible_left),
        "center": bool(model.visible_center),
        "right": bool(model.visible_right),
    }

def _write_magnifier_visibility(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    model = _magnifier_model(snapshot.viewport_state)
    if model is None:
        return
    if "left" in channels:
        model.visible_left = bool(channels["left"])
    if "center" in channels:
        model.visible_center = bool(channels["center"])
    if "right" in channels:
        model.visible_right = bool(channels["right"])

def _read_magnifier_divider_visible(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        return {"value": bool(model.divider_visible)}
    return {"value": bool(get_magnifier_widget_state(snapshot.viewport_state.view_state).default_divider_visible)}

def _write_magnifier_divider_visible(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    value = bool(channels["value"])
    state = get_magnifier_widget_state(snapshot.viewport_state.view_state)
    state.default_divider_visible = value
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        model.divider_visible = value

def _read_magnifier_divider_color(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        color = model.divider_color
    else:
        color = get_magnifier_widget_state(snapshot.viewport_state.view_state).default_divider_color
    return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}

def _write_magnifier_divider_color(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    from domain.types import Color

    color = Color(
        int(channels["r"]),
        int(channels["g"]),
        int(channels["b"]),
        int(channels["a"]),
    )
    state = get_magnifier_widget_state(snapshot.viewport_state.view_state)
    state.default_divider_color = color
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        model.divider_color = color

def _read_magnifier_divider_thickness(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        return {"value": float(model.divider_thickness)}
    return {"value": float(get_magnifier_widget_state(snapshot.viewport_state.view_state).default_divider_thickness)}

def _write_magnifier_divider_thickness(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    value = int(float(channels["value"]))
    state = get_magnifier_widget_state(snapshot.viewport_state.view_state)
    state.default_divider_thickness = value
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        model.divider_thickness = value

def _read_magnifier_border_color(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        color = model.border_color
    else:
        color = get_magnifier_widget_state(snapshot.viewport_state.view_state).default_border_color
    return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}

def _write_magnifier_border_color(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    color = Color(
        int(channels["r"]),
        int(channels["g"]),
        int(channels["b"]),
        int(channels["a"]),
    )
    state = get_magnifier_widget_state(snapshot.viewport_state.view_state)
    state.default_border_color = color
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        model.border_color = color

def _read_magnifier_capture_color(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        color = model.capture_ring_color
    else:
        color = get_capture_widget_state(snapshot.viewport_state.view_state).color
    return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}

def _write_magnifier_capture_color(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    color = Color(
        int(channels["r"]),
        int(channels["g"]),
        int(channels["b"]),
        int(channels["a"]),
    )
    capture_state = get_capture_widget_state(snapshot.viewport_state.view_state).clone()
    capture_state.color = color
    canvas_widget_state = dict(getattr(snapshot.viewport_state.view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["capture"] = capture_state
    snapshot.viewport_state.view_state.canvas_widget_state = canvas_widget_state

    state, active_id, magnifiers, model = _ensure_active_magnifier_model(snapshot.viewport_state.view_state)
    model.capture_ring_color = color
    magnifiers[active_id] = model
    canvas_widget_state = dict(getattr(snapshot.viewport_state.view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["magnifier"] = state
    snapshot.viewport_state.view_state.canvas_widget_state = canvas_widget_state

def _read_magnifier_laser_color(snapshot: FrameSnapshot) -> dict[str, Any]:
    model = _magnifier_model(snapshot.viewport_state)
    if model is not None:
        color = model.laser_color
    else:
        color = get_guides_widget_state(snapshot.viewport_state.view_state).color
    return {"r": int(color.r), "g": int(color.g), "b": int(color.b), "a": int(color.a)}

def _write_magnifier_laser_color(snapshot: FrameSnapshot, channels: dict[str, Any]) -> None:
    color = Color(
        int(channels["r"]),
        int(channels["g"]),
        int(channels["b"]),
        int(channels["a"]),
    )
    guides_state = get_guides_widget_state(snapshot.viewport_state.view_state).clone()
    guides_state.color = color
    canvas_widget_state = dict(getattr(snapshot.viewport_state.view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["guides"] = guides_state
    snapshot.viewport_state.view_state.canvas_widget_state = canvas_widget_state

    state, active_id, magnifiers, model = _ensure_active_magnifier_model(snapshot.viewport_state.view_state)
    model.laser_color = color
    magnifiers[active_id] = model
    canvas_widget_state = dict(getattr(snapshot.viewport_state.view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["magnifier"] = state
    snapshot.viewport_state.view_state.canvas_widget_state = canvas_widget_state

def build_magnifier_properties() -> tuple[CanvasFeatureProperty, ...]:
    enabled = _track_descriptor("magnifier.default.enabled", "Enabled", "bool")
    position = _track_descriptor("magnifier.default.position", "Position", "vec2")
    size = _track_descriptor("magnifier.default.size", "Size", "scalar")
    capture_size = _track_descriptor("magnifier.default.capture_size", "Capture Size", "scalar")
    internal_split = _track_descriptor("magnifier.default.internal_split", "Internal Split", "scalar")
    orientation = _track_descriptor("magnifier.default.orientation", "Orientation", "bool")
    visibility = _track_descriptor("magnifier.default.visibility", "Visibility", "mask3")
    divider_visible = _track_descriptor("magnifier.divider.visible", "Divider Visible", "bool")
    divider_color = _track_descriptor("magnifier.divider.color", "Divider Color", "color")
    divider_thickness = _track_descriptor("magnifier.divider.thickness", "Divider Thickness", "scalar")
    border_color = _track_descriptor("magnifier.border.color", "Border Color", "color")
    capture_color = _track_descriptor("magnifier.capture.color", "Capture Color", "color")
    laser_color = _track_descriptor("magnifier.laser.color", "Laser Color", "color")
    intersection_highlight = _track_descriptor("magnifier.intersection_highlight.enabled", "Intersection Highlight", "bool")
    auto_color_new = _track_descriptor("magnifier.auto_color_new_instances.enabled", "Auto Color New Instances", "bool")
    return (
        CanvasFeatureProperty(
            id=enabled.id,
            label=enabled.label,
            kind=enabled.kind,
            channels=enabled.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=lambda snap: {"value": bool(get_magnifier_widget_state(snap.viewport_state.view_state).enabled)},
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "enabled",
                bool(ch["value"]),
            ),
            order=50,
        ),
        CanvasFeatureProperty(
            id=position.id,
            label=position.label,
            kind=position.kind,
            channels=position.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=_read_magnifier_position,
            write_snapshot=_write_magnifier_position,
            order=51,
        ),
        CanvasFeatureProperty(
            id=size.id,
            label=size.label,
            kind=size.kind,
            channels=size.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.size",
            serialize_setting=lambda ch: float(ch["value"]),
            deserialize_setting=lambda raw: {"value": float(raw)},
            read_snapshot=_read_magnifier_size,
            write_snapshot=_write_magnifier_size,
            order=52,
        ),
        CanvasFeatureProperty(
            id=capture_size.id,
            label=capture_size.label,
            kind=capture_size.kind,
            channels=capture_size.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.capture_size",
            serialize_setting=lambda ch: float(ch["value"]),
            deserialize_setting=lambda raw: {"value": float(raw)},
            read_snapshot=_read_capture_size,
            write_snapshot=_write_capture_size,
            order=53,
        ),
        CanvasFeatureProperty(
            id=internal_split.id,
            label=internal_split.label,
            kind=internal_split.kind,
            channels=internal_split.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=_read_magnifier_internal_split,
            write_snapshot=_write_magnifier_internal_split,
            order=54,
        ),
        CanvasFeatureProperty(
            id=orientation.id,
            label=orientation.label,
            kind=orientation.kind,
            channels=orientation.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=_read_magnifier_orientation,
            write_snapshot=_write_magnifier_orientation,
            order=55,
        ),
        CanvasFeatureProperty(
            id=visibility.id,
            label=visibility.label,
            kind=visibility.kind,
            channels=visibility.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=_read_magnifier_visibility,
            write_snapshot=_write_magnifier_visibility,
            order=56,
        ),
        CanvasFeatureProperty(
            id=divider_visible.id,
            label=divider_visible.label,
            kind=divider_visible.kind,
            channels=divider_visible.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.divider.visible",
            read_snapshot=_read_magnifier_divider_visible,
            write_snapshot=_write_magnifier_divider_visible,
            order=57,
        ),
        CanvasFeatureProperty(
            id=divider_color.id,
            label=divider_color.label,
            kind=divider_color.kind,
            channels=divider_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.divider.color",
            read_snapshot=_read_magnifier_divider_color,
            write_snapshot=_write_magnifier_divider_color,
            order=58,
        ),
        CanvasFeatureProperty(
            id=divider_thickness.id,
            label=divider_thickness.label,
            kind=divider_thickness.kind,
            channels=divider_thickness.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.divider.thickness",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=_read_magnifier_divider_thickness,
            write_snapshot=_write_magnifier_divider_thickness,
            order=59,
        ),
        CanvasFeatureProperty(
            id=border_color.id,
            label=border_color.label,
            kind=border_color.kind,
            channels=border_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.border.color",
            read_snapshot=_read_magnifier_border_color,
            write_snapshot=_write_magnifier_border_color,
            order=60,
        ),
        CanvasFeatureProperty(
            id=capture_color.id,
            label=capture_color.label,
            kind=capture_color.kind,
            channels=capture_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.capture.color",
            read_snapshot=_read_magnifier_capture_color,
            write_snapshot=_write_magnifier_capture_color,
            order=61,
        ),
        CanvasFeatureProperty(
            id=laser_color.id,
            label=laser_color.label,
            kind=laser_color.kind,
            channels=laser_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.laser.color",
            read_snapshot=_read_magnifier_laser_color,
            write_snapshot=_write_magnifier_laser_color,
            order=62,
        ),
        CanvasFeatureProperty(
            id=intersection_highlight.id,
            label=intersection_highlight.label,
            kind=intersection_highlight.kind,
            channels=intersection_highlight.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.intersection_highlight.enabled",
            read_snapshot=lambda snap: {
                "value": bool(
                    get_magnifier_widget_state(
                        snap.viewport_state.view_state
                    ).intersection_highlight_enabled
                )
            },
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "intersection_highlight_enabled",
                bool(ch["value"]),
            ),
            order=63,
        ),
        CanvasFeatureProperty(
            id=auto_color_new.id,
            label=auto_color_new.label,
            kind=auto_color_new.kind,
            channels=auto_color_new.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.auto_color_new_instances.enabled",
            read_snapshot=lambda snap: {
                "value": bool(
                    get_magnifier_widget_state(
                        snap.viewport_state.view_state
                    ).auto_color_new_instances
                )
            },
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "auto_color_new_instances",
                bool(ch["value"]),
            ),
            order=64,
        ),
    )

WIDGET_FEATURE = CanvasWidgetFeature(
    name="magnifier",
    reduce_view_state=reduce_magnifier_view_state,
    reduce_render_config=reduce_magnifier_render_config,
    build_properties=build_magnifier_properties,
    reducer_order=50,
    property_order=50,
)
