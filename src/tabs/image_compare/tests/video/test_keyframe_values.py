"""Keyframe track values: color channels are hold-typed, color drags compact to
a single step, and continuous scalars avoid step-pairs for sparse drags.

Dogma source: docs/dev/CONTRACTS.md §CanvasFeatureProperty (keyframe channels).
"""

from __future__ import annotations
from domain.types import Color
from tabs.image_compare.plugins.video_editor.services.keyframing.adapters.viewport_base import (
    build_viewport_base_adapter,
)
from tabs.image_compare.plugins.video_editor.services.keyframing.engine.values import (
    add_value_to_track,
    append_channel_keyframe,
)
from tabs.image_compare.plugins.video_editor.services.timeline import TimelineChannel, TimelineTrack

def test_add_value_to_track_creates_color_channels_as_hold() -> None:
    track = TimelineTrack(id="color.track", label="Color", kind="color")

    added = add_value_to_track(track, 0.0, Color(10, 20, 30, 255))

    assert added is True
    assert set(track.channels.keys()) == {"r", "g", "b", "a"}
    assert all(channel.interpolate_values is False for channel in track.channels.values())

def test_color_drag_is_compacted_to_single_step() -> None:
    channel = TimelineChannel(
        id="r",
        label="R",
        kind="color",
        interpolate_values=False,
    )

    assert append_channel_keyframe(channel, 0.0, 0, fps=60) is True
    assert append_channel_keyframe(channel, 0.10, 32, fps=60) is True
    assert append_channel_keyframe(channel, 0.11, 96, fps=60) is True
    assert append_channel_keyframe(channel, 0.12, 160, fps=60) is True

    assert [(kf.timestamp, kf.value, kf.interpolation) for kf in channel.keyframes] == [
        (0.0, 0, "hold"),
        (0.12, 0, "hold"),
        (0.12, 160, "hold"),
    ]

def test_hold_channel_starts_new_step_after_value_settles() -> None:
    channel = TimelineChannel(
        id="r",
        label="R",
        kind="color",
        interpolate_values=False,
    )

    append_channel_keyframe(channel, 0.0, 0, fps=60)
    append_channel_keyframe(channel, 0.10, 32, fps=60)
    assert append_channel_keyframe(channel, 0.12, 32, fps=60) is False
    append_channel_keyframe(channel, 0.30, 96, fps=60)

    assert [(kf.timestamp, kf.value, kf.interpolation) for kf in channel.keyframes] == [
        (0.0, 0, "hold"),
        (0.10, 0, "hold"),
        (0.10, 32, "hold"),
        (0.30, 32, "hold"),
        (0.30, 96, "hold"),
    ]

def test_continuous_scalar_track_avoids_step_pairs_for_sparse_drag() -> None:
    track = TimelineTrack(id="text.alpha", label="Alpha", kind="scalar")

    assert add_value_to_track(track, 0.0, {"value": 100.0}, fps=60) is True
    assert add_value_to_track(track, 0.10, {"value": 60.0}, fps=60) is True
    assert add_value_to_track(track, 0.20, {"value": 20.0}, fps=60) is True

    channel = track.channels["value"]
    assert channel.prefer_continuous_curve is True
    assert [(kf.timestamp, kf.value, kf.interpolation) for kf in channel.keyframes] == [
        (0.0, 100.0, "linear"),
        (0.10, 60.0, "linear"),
        (0.20, 20.0, "linear"),
    ]


def test_magnifier_position_vec2_avoids_step_pairs_like_divider() -> None:
    """magnifier.<id>.position must use continuous curves (same as splitter.main.position)."""
    track = TimelineTrack(id="magnifier.default.position", label="Capture Position", kind="vec2")

    assert add_value_to_track(track, 0.0, {"x": 0.10, "y": 0.20}, fps=60) is True
    assert add_value_to_track(track, 0.10, {"x": 0.30, "y": 0.40}, fps=60) is True
    assert add_value_to_track(track, 0.20, {"x": 0.50, "y": 0.60}, fps=60) is True

    assert track.channels["x"].prefer_continuous_curve is True
    assert track.channels["y"].prefer_continuous_curve is True
    assert [(kf.timestamp, kf.value) for kf in track.channels["x"].keyframes] == [
        (0.0, 0.10),
        (0.10, 0.30),
        (0.20, 0.50),
    ]
    assert [(kf.timestamp, kf.value) for kf in track.channels["y"].keyframes] == [
        (0.0, 0.20),
        (0.10, 0.40),
        (0.20, 0.60),
    ]


def test_magnifier_offset_vec2_uses_continuous_curve() -> None:
    """Lens offset is a separate continuous track from capture position."""
    track = TimelineTrack(id="magnifier.default.offset", label="Offset", kind="vec2")

    assert add_value_to_track(track, 0.0, {"x": 0.0, "y": 0.0}, fps=60) is True
    assert add_value_to_track(track, 0.10, {"x": 0.05, "y": -0.02}, fps=60) is True
    assert add_value_to_track(track, 0.20, {"x": 0.10, "y": -0.04}, fps=60) is True

    assert track.channels["x"].prefer_continuous_curve is True
    assert track.channels["y"].prefer_continuous_curve is True
    assert [(kf.timestamp, kf.value) for kf in track.channels["x"].keyframes] == [
        (0.0, 0.0),
        (0.10, 0.05),
        (0.20, 0.10),
    ]


def test_continuous_idle_then_move_does_not_ramp_from_t0() -> None:
    """Divider/magnifier sit still after record start, then move — curve starts at move."""
    track = TimelineTrack(id="splitter.main.position", label="Position", kind="scalar")

    assert add_value_to_track(track, 0.0, {"value": 0.5}, fps=60) is True
    assert add_value_to_track(track, 0.10, {"value": 0.5}, fps=60) is True
    assert add_value_to_track(track, 0.50, {"value": 0.5}, fps=60) is True
    assert add_value_to_track(track, 0.52, {"value": 0.7}, fps=60) is True
    assert add_value_to_track(track, 0.60, {"value": 0.9}, fps=60) is True

    channel = track.channels["value"]
    assert [(round(kf.timestamp, 4), kf.value) for kf in channel.keyframes] == [
        (0.5, 0.5),
        (0.52, 0.7),
        (0.6, 0.9),
    ]


def test_magnifier_idle_then_move_does_not_ramp_from_t0() -> None:
    track = TimelineTrack(id="magnifier.default.position", label="Position", kind="vec2")

    assert add_value_to_track(track, 0.0, {"x": 0.2, "y": 0.3}, fps=60) is True
    assert add_value_to_track(track, 0.40, {"x": 0.2, "y": 0.3}, fps=60) is True
    assert add_value_to_track(track, 0.42, {"x": 0.4, "y": 0.5}, fps=60) is True
    assert add_value_to_track(track, 0.50, {"x": 0.6, "y": 0.7}, fps=60) is True

    assert [(round(kf.timestamp, 4), kf.value) for kf in track.channels["x"].keyframes] == [
        (0.4, 0.2),
        (0.42, 0.4),
        (0.5, 0.6),
    ]
    assert [(round(kf.timestamp, 4), kf.value) for kf in track.channels["y"].keyframes] == [
        (0.4, 0.3),
        (0.42, 0.5),
        (0.5, 0.7),
    ]

def test_text_color_tracks_are_declared_as_hold() -> None:
    adapter = build_viewport_base_adapter()
    descriptor = next(tool for tool in adapter.describe_tools() if tool.id == "viewport.base")
    text_color_track = next(track for track in descriptor.tracks if track.id == "text.color")
    text_bg_color_track = next(track for track in descriptor.tracks if track.id == "text.bg_color")

    assert all(channel.interpolate_values is False for channel in text_color_track.channels)
    assert all(channel.interpolate_values is False for channel in text_bg_color_track.channels)
