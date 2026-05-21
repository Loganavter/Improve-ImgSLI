from __future__ import annotations

from domain.types import Color
from ui.canvas_infra.scene.widget_contract import CanvasFeatureProperty
from plugins.video_editor.services.keyframing.adapters.base import (
    ChannelDescriptor,
    TrackDescriptor,
)

from .state import get_magnifier_widget_state

def _track_descriptor(
    track_id: str,
    label: str,
    kind: str,
    *,
    channels: tuple[ChannelDescriptor, ...] | None = None,
) -> TrackDescriptor:
    defaults = {
        "scalar": (ChannelDescriptor("value", "Value", "scalar"),),
        "bool": (
            ChannelDescriptor("value", "Value", "bool", interpolate_values=False),
        ),
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
    return TrackDescriptor(
        id=track_id,
        label=label,
        kind=kind,
        channels=channels or defaults[kind],
    )

def build_magnifier_properties() -> tuple[CanvasFeatureProperty, ...]:
    enabled = _track_descriptor("magnifier.default.enabled", "Enabled", "bool")
    border_color = _track_descriptor("magnifier.border.color", "Border Color", "color")
    divider_color = _track_descriptor("magnifier.divider.color", "Divider Color", "color")
    intersection_highlight = _track_descriptor(
        "magnifier.intersection_highlight.enabled",
        "Intersection Highlight",
        "bool",
    )
    auto_color_new = _track_descriptor(
        "magnifier.auto_color_new_instances.enabled",
        "Auto Color New Instances",
        "bool",
    )
    return (
        CanvasFeatureProperty(
            id=enabled.id,
            label=enabled.label,
            kind=enabled.kind,
            channels=enabled.channels,
            group_id="magnifier",
            group_label="Magnifier",
            read_snapshot=lambda snap: {
                "value": bool(get_magnifier_widget_state(snap.viewport_state.view_state).enabled)
            },
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "enabled",
                bool(ch["value"]),
            ),
            order=50,
        ),
        CanvasFeatureProperty(
            id=border_color.id,
            label=border_color.label,
            kind=border_color.kind,
            channels=border_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.border.color",
            read_snapshot=lambda snap: {
                "r": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_border_color.r),
                "g": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_border_color.g),
                "b": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_border_color.b),
                "a": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_border_color.a),
            },
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "default_border_color",
                Color(
                    int(ch["r"]),
                    int(ch["g"]),
                    int(ch["b"]),
                    int(ch["a"]),
                ),
            ),
            order=51,
        ),
        CanvasFeatureProperty(
            id=divider_color.id,
            label=divider_color.label,
            kind=divider_color.kind,
            channels=divider_color.channels,
            group_id="magnifier",
            group_label="Magnifier",
            setting_key="magnifier.divider.color",
            read_snapshot=lambda snap: {
                "r": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_divider_color.r),
                "g": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_divider_color.g),
                "b": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_divider_color.b),
                "a": int(get_magnifier_widget_state(snap.viewport_state.view_state).default_divider_color.a),
            },
            write_snapshot=lambda snap, ch: setattr(
                get_magnifier_widget_state(snap.viewport_state.view_state),
                "default_divider_color",
                Color(
                    int(ch["r"]),
                    int(ch["g"]),
                    int(ch["b"]),
                    int(ch["a"]),
                ),
            ),
            order=52,
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
            order=53,
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
            order=54,
        ),
    )
