from __future__ import annotations

from dataclasses import replace

from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import ChannelDescriptor, TrackDescriptor
from ui.canvas_infra.scene.widget_contract import CanvasFeatureProperty

from .state import GuidesWidgetState, get_guides_widget_state

def set_snapshot_guides_state(snap, state: GuidesWidgetState) -> None:
    view_state = snap.viewport_state.view_state
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["guides"] = state
    view_state.canvas_widget_state = canvas_widget_state

def track_descriptor(track_id: str, label: str, kind: str) -> TrackDescriptor:
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
    enabled = track_descriptor("lasers.enabled", "Enabled", "bool")
    thickness = track_descriptor("lasers.thickness", "Thickness", "scalar")
    color = track_descriptor("lasers.color", "Color", "color")
    smoothing = track_descriptor("lasers.smoothing.enabled", "Smoothing", "bool")
    interpolation = track_descriptor(
        "lasers.smoothing.interpolation_method",
        "Smoothing Interpolation",
        "enum",
    )
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
            write_snapshot=lambda snap, ch: set_snapshot_guides_state(
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
            write_snapshot=lambda snap, ch: set_snapshot_guides_state(
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
            write_snapshot=lambda snap, ch: set_snapshot_guides_state(
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
            write_snapshot=lambda snap, ch: set_snapshot_guides_state(
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
            write_snapshot=lambda snap, ch: set_snapshot_guides_state(
                snap,
                replace(
                    get_guides_widget_state(snap.viewport_state.view_state).clone(),
                    smoothing_interpolation_method=str(ch["value"]),
                ),
            ),
            order=24,
        ),
    )

