from __future__ import annotations

from dataclasses import replace

from domain.types import Color
from plugins.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    TrackDescriptor,
)
from ui.canvas_infra.scene.widget_contract import CanvasFeatureProperty

from .state import DividerWidgetState, get_divider_widget_state


def set_snapshot_divider_state(snap, state: DividerWidgetState) -> None:
    view_state = snap.viewport_state.view_state
    canvas_widget_state = dict(getattr(view_state, "canvas_widget_state", None) or {})
    canvas_widget_state["divider"] = state
    view_state.canvas_widget_state = canvas_widget_state


def track_descriptor(track_id: str, label: str, kind: str) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (
            ChannelDescriptor("value", "Value", "bool", interpolate_values=False),
        ),
        "color": (
            ChannelDescriptor("r", "R", "color"),
            ChannelDescriptor("g", "G", "color"),
            ChannelDescriptor("b", "B", "color"),
            ChannelDescriptor("a", "A", "color"),
        ),
    }
    return TrackDescriptor(id=track_id, label=label, kind=kind, channels=defaults[kind])


def build_divider_properties() -> tuple[CanvasFeatureProperty, ...]:
    position = track_descriptor("splitter.main.position", "Position", "scalar")
    orientation = track_descriptor("splitter.main.orientation", "Orientation", "bool")
    color = track_descriptor("splitter.main.color", "Color", "color")
    visible = track_descriptor("splitter.main.visible", "Visible", "bool")
    thickness = track_descriptor("splitter.main.thickness", "Thickness", "scalar")
    return (
        CanvasFeatureProperty(
            id=position.id,
            label=position.label,
            kind=position.kind,
            channels=position.channels,
            group_id="divider",
            group_label="Divider",
            read_snapshot=lambda snap: {
                "value": float(snap.viewport_state.view_state.split_position)
            },
            write_snapshot=lambda snap, ch: (
                setattr(
                    snap.viewport_state.view_state, "split_position", float(ch["value"])
                ),
                setattr(
                    snap.viewport_state.view_state,
                    "split_position_visual",
                    float(ch["value"]),
                ),
            ),
            order=10,
        ),
        CanvasFeatureProperty(
            id=orientation.id,
            label=orientation.label,
            kind=orientation.kind,
            channels=orientation.channels,
            group_id="divider",
            group_label="Divider",
            read_snapshot=lambda snap: {
                "value": bool(snap.viewport_state.view_state.is_horizontal)
            },
            write_snapshot=lambda snap, ch: setattr(
                snap.viewport_state.view_state,
                "is_horizontal",
                bool(ch["value"]),
            ),
            order=11,
        ),
        CanvasFeatureProperty(
            id=color.id,
            label=color.label,
            kind=color.kind,
            channels=color.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.color",
            read_snapshot=lambda snap: {
                "r": int(
                    get_divider_widget_state(snap.viewport_state.view_state).color.r
                ),
                "g": int(
                    get_divider_widget_state(snap.viewport_state.view_state).color.g
                ),
                "b": int(
                    get_divider_widget_state(snap.viewport_state.view_state).color.b
                ),
                "a": int(
                    get_divider_widget_state(snap.viewport_state.view_state).color.a
                ),
            },
            write_snapshot=lambda snap, ch: set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    color=Color(int(ch["r"]), int(ch["g"]), int(ch["b"]), int(ch["a"])),
                ),
            ),
            order=12,
        ),
        CanvasFeatureProperty(
            id=visible.id,
            label=visible.label,
            kind=visible.kind,
            channels=visible.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.visible",
            read_snapshot=lambda snap: {
                "value": bool(
                    get_divider_widget_state(snap.viewport_state.view_state).visible
                )
            },
            write_snapshot=lambda snap, ch: set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    visible=bool(ch["value"]),
                ),
            ),
            order=13,
        ),
        CanvasFeatureProperty(
            id=thickness.id,
            label=thickness.label,
            kind=thickness.kind,
            channels=thickness.channels,
            group_id="divider",
            group_label="Divider",
            setting_key="divider.thickness",
            serialize_setting=lambda ch: int(ch["value"]),
            deserialize_setting=lambda raw: {"value": int(float(raw))},
            read_snapshot=lambda snap: {
                "value": float(
                    get_divider_widget_state(snap.viewport_state.view_state).thickness
                )
            },
            write_snapshot=lambda snap, ch: set_snapshot_divider_state(
                snap,
                replace(
                    get_divider_widget_state(snap.viewport_state.view_state).clone(),
                    thickness=max(0, int(float(ch["value"]))),
                ),
            ),
            order=14,
        ),
    )
