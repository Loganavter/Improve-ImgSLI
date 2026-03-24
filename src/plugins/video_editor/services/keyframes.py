from __future__ import annotations

import copy
import logging
import math
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
from typing import Any

from core.store_viewport import ViewportState
from domain.types import Color, Point
from plugins.video_editor.services.track_defs import (
    ViewportTrackSpec,
    multi_attr_track,
    track,
)
from plugins.video_editor.services.timeline import (
    ChannelKeyframe,
    TimelineChannel,
    TimelineModel,
    TimelineTrack,
)

logger = logging.getLogger("ImproveImgSLI")

@dataclass(frozen=True)
class FrameSnapshot:
    timestamp: float
    viewport_state: Any
    settings_state: Any
    image1_path: str | None
    image2_path: str | None
    name1: str | None
    name2: str | None

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "viewport_state": self.viewport_state,
            "settings_state": self.settings_state,
            "image1_path": self.image1_path,
            "image2_path": self.image2_path,
            "name1": self.name1,
            "name2": self.name2,
        }

@dataclass(frozen=True)
class Keyframe:
    timestamp: float
    value: Any
    interpolation: str = "linear"

def _read_interaction_session(viewport: ViewportState) -> dict[str, Any]:
    return {"value": str(int(getattr(viewport, "interaction_session_id", 0)))}

def _write_interaction_session(viewport: ViewportState, channels: dict[str, Any]) -> None:
    try:
        viewport.interaction_session_id = int(channels["value"])
    except (TypeError, ValueError):
        viewport.interaction_session_id = 0

VIEWPORT_TRACK_SPECS: tuple[ViewportTrackSpec, ...] = (

    track("comparison.diff_mode",         "comparison", "Comparison", "Diff Mode",    "enum",  attr="diff_mode"),
    track("comparison.channel_view_mode", "comparison", "Comparison", "Channel View", "enum",  attr="channel_view_mode"),

    track("view.interpolation_method", "view", "View", "Interpolation", "enum",
          attr="interpolation_method",
          write_attrs=["interpolation_method", "render_config.interpolation_method"]),

    track("splitter.main.position", "splitter", "Splitter", "Position", "scalar",
          attr="split_position",
          write_attrs=["split_position", "split_position_visual"]),
    track("splitter.main.orientation", "splitter", "Splitter", "Orientation", "bool", attr="is_horizontal"),
    track("splitter.main.color", "splitter", "Splitter", "Color", "color",
          attr="render_config.divider_line_color"),

    track("magnifier.default.enabled",        "magnifier.default", "Magnifier 1", "Enabled",        "bool",   attr="use_magnifier"),
    track("magnifier.default.position",       "magnifier.default", "Magnifier 1", "Position",       "vec2",   attr="capture_position_relative"),
    track("magnifier.default.size",           "magnifier.default", "Magnifier 1", "Size",           "scalar", attr="magnifier_size_relative"),
    track("magnifier.default.capture_size",   "magnifier.default", "Magnifier 1", "Capture Size",   "scalar", attr="capture_size_relative"),
    track("magnifier.default.internal_split", "magnifier.default", "Magnifier 1", "Internal Split", "scalar", attr="magnifier_internal_split"),
    track("magnifier.default.orientation",    "magnifier.default", "Magnifier 1", "Orientation",    "bool",   attr="magnifier_is_horizontal"),
    multi_attr_track("magnifier.default.visibility", "magnifier.default", "Magnifier 1", "Visibility", "mask3",
        attr_map={"left": "magnifier_visible_left", "center": "magnifier_visible_center", "right": "magnifier_visible_right"}),

    track("lasers.enabled",   "lasers", "Lasers", "Enabled",   "bool",   attr="render_config.show_magnifier_guides"),
    track("lasers.thickness", "lasers", "Lasers", "Thickness", "scalar", attr="render_config.magnifier_guides_thickness"),
    track("lasers.color",     "lasers", "Lasers", "Color",     "color",  attr="render_config.magnifier_laser_color"),
    track("lasers.smoothing.enabled", "lasers", "Lasers", "Smoothing", "bool",
          attr="render_config.optimize_laser_smoothing",
          write_attrs=["optimize_laser_smoothing", "render_config.optimize_laser_smoothing"]),
    track("lasers.smoothing.interpolation_method", "lasers", "Lasers", "Smoothing Interpolation", "enum",
          attr="render_config.laser_smoothing_interpolation_method"),

    track("text.visible",    "text", "Text", "Visible",          "bool",   attr="include_file_names_in_saved"),
    track("text.font_size",  "text", "Text", "Font Size %",      "scalar", attr="font_size_percent"),
    track("text.font_weight","text", "Text", "Font Weight",      "scalar", attr="font_weight"),
    track("text.alpha",      "text", "Text", "Alpha %",          "scalar", attr="text_alpha_percent"),
    track("text.color",      "text", "Text", "Color",            "color",  attr="file_name_color"),
    track("text.bg_color",   "text", "Text", "Background Color", "color",  attr="file_name_bg_color"),
    track("text.bg_visible", "text", "Text", "Background",       "bool",   attr="draw_text_background"),
    track("text.placement",  "text", "Text", "Placement",        "enum",   attr="text_placement_mode"),

    track("__input.interaction_session", "__input", "Input", "Interaction Session", "enum",
          reader=_read_interaction_session, writer=_write_interaction_session),
)

INTERNAL_VIEWPORT_BASE_TRACK = "__viewport_base"

class KeyframeTrack:
    def __init__(self, track: TimelineTrack):
        self._track = track

    @property
    def keyframes(self) -> list[Keyframe]:
        channel = self._primary_channel()
        if channel is None:
            return []
        return [
            Keyframe(
                timestamp=item.timestamp,
                value=item.value,
                interpolation=item.interpolation,
            )
            for item in channel.keyframes
        ]

    @property
    def channels(self) -> dict[str, TimelineChannel]:
        return self._track.channels

    @property
    def label(self) -> str:
        return self._track.label

    def clear(self) -> None:
        self._track.clear()

    def add_keyframe(self, timestamp: float, value: Any, *, fps: int = 60) -> bool:
        return _add_value_to_track(self._track, timestamp, value, fps=fps)

    def evaluate_at(self, timestamp: float) -> Any:
        return _assemble_value_from_track(self._track, timestamp)

    def _primary_channel(self) -> TimelineChannel | None:
        return self._track.channels.get("value") or next(
            iter(self._track.channels.values()), None
        )

class KeyframedRecording:
    SIMPLE_TRACK_LAYOUT = {
        "settings_state": ("view", "View", "Settings State", "state"),
        "image1_path": ("sources", "Sources", "Image 1", "source"),
        "image2_path": ("sources", "Sources", "Image 2", "source"),
        "name1": ("overlay", "Overlay", "Name 1", "label"),
        "name2": ("overlay", "Overlay", "Name 2", "label"),
    }

    def __init__(
        self,
        fps: int = 60,
        extra_specs: tuple[ViewportTrackSpec, ...] = (),
    ):
        self.fps = max(1, int(fps))
        self.timeline = TimelineModel()
        self.tracks: dict[str, KeyframeTrack] = {}
        self._last_viewport_fingerprint: Any = None
        self._last_settings_fingerprint: Any = None
        self._all_specs = VIEWPORT_TRACK_SPECS + tuple(extra_specs)

        base_track = self.timeline.ensure_track(
            group_id="view",
            track_id=INTERNAL_VIEWPORT_BASE_TRACK,
            group_label="View",
            track_label="Viewport Base",
            track_kind="state",
        )
        base_track.ensure_channel(
            "value", label="Value", kind="state", interpolate_values=False
        )
        self.tracks["viewport_state"] = KeyframeTrack(base_track)

        for spec in self._all_specs:
            track = self.timeline.ensure_track(
                group_id=spec.group_id,
                track_id=spec.public_id,
                group_label=spec.group_label,
                track_label=spec.track_label,
                track_kind=spec.track_kind,
            )
            for channel_id, channel_label, channel_kind in spec.channels:
                track.ensure_channel(
                    channel_id,
                    label=channel_label,
                    kind=channel_kind,
                    interpolate_values=(
                        channel_kind not in {"bool", "enum"}
                        and spec.track_kind != "color"
                    ),
                )
            self.tracks[spec.public_id] = KeyframeTrack(track)

        for track_id, (group_id, group_label, track_label, track_kind) in (
            self.SIMPLE_TRACK_LAYOUT.items()
        ):
            track = self.timeline.ensure_track(
                group_id=group_id,
                track_id=track_id,
                group_label=group_label,
                track_label=track_label,
                track_kind=track_kind,
            )
            channel_kind = "state" if track_id == "settings_state" else "value"
            track.ensure_channel(
                "value",
                label="Value",
                kind=channel_kind,
                interpolate_values=False,
            )
            self.tracks[track_id] = KeyframeTrack(track)

    @property
    def sample_timestamps(self) -> list[float]:
        return self.timeline.sample_timestamps

    @property
    def keyframes(self) -> dict[str, list[ChannelKeyframe]]:
        payload: dict[str, list[ChannelKeyframe]] = {}
        for name, wrapper in self.tracks.items():
            channel = wrapper.channels.get("value") or next(
                iter(wrapper.channels.values()), None
            )
            payload[name] = list(channel.keyframes) if channel is not None else []
        return payload

    @classmethod
    def from_snapshots(
        cls, snapshots: list[FrameSnapshot], fps: int = 60
    ) -> "KeyframedRecording":
        recording = cls(fps=fps)
        for snapshot in snapshots:
            recording.append(snapshot)
        recording.finalize_tail_keyframes()
        return recording

    def clear(self) -> None:
        self.timeline.clear()
        self._last_viewport_fingerprint = None
        self._last_settings_fingerprint = None

    def append(self, snapshot: FrameSnapshot) -> None:
        timestamp = self._quantize_timestamp(snapshot.timestamp)
        if self.timeline.sample_timestamps and math.isclose(
            self.timeline.sample_timestamps[-1], timestamp, abs_tol=1e-9
        ):
            self.timeline.sample_timestamps[-1] = timestamp
        else:
            self.timeline.sample_timestamps.append(timestamp)

        viewport_fingerprint = _viewport_fingerprint(snapshot.viewport_state)
        self._append_viewport_base_keyframe(
            timestamp,
            snapshot.viewport_state,
            viewport_fingerprint,
        )
        for spec in self._all_specs:
            self.tracks[spec.public_id].add_keyframe(
                timestamp, spec.reader(snapshot.viewport_state), fps=self.fps
            )
        settings_fingerprint = _frozen_value(snapshot.settings_state)
        self._append_cached_hold_keyframe(
            track_name="settings_state",
            timestamp=timestamp,
            value=snapshot.settings_state,
            fingerprint=settings_fingerprint,
            fingerprint_attr="_last_settings_fingerprint",
        )
        self.tracks["image1_path"].add_keyframe(timestamp, snapshot.image1_path, fps=self.fps)
        self.tracks["image2_path"].add_keyframe(timestamp, snapshot.image2_path, fps=self.fps)
        self.tracks["name1"].add_keyframe(timestamp, snapshot.name1, fps=self.fps)
        self.tracks["name2"].add_keyframe(timestamp, snapshot.name2, fps=self.fps)

    def _append_viewport_base_keyframe(
        self,
        timestamp: float,
        viewport_state: ViewportState,
        fingerprint: Any,
    ) -> None:
        channel = self.tracks["viewport_state"].channels["value"]
        keyframes = channel.keyframes
        interpolation = "hold"
        new_keyframe = ChannelKeyframe(
            timestamp=float(timestamp),
            value=_clone_value(viewport_state),
            interpolation=interpolation,
        )

        if not keyframes:
            keyframes.append(new_keyframe)
            self._last_viewport_fingerprint = fingerprint
            return

        if math.isclose(keyframes[-1].timestamp, new_keyframe.timestamp, abs_tol=1e-9):
            keyframes[-1] = new_keyframe
            self._last_viewport_fingerprint = fingerprint
            return

        if self._last_viewport_fingerprint == fingerprint:
            return

        keyframes.append(new_keyframe)
        self._last_viewport_fingerprint = fingerprint

    def _append_cached_hold_keyframe(
        self,
        *,
        track_name: str,
        timestamp: float,
        value: Any,
        fingerprint: Any,
        fingerprint_attr: str,
    ) -> None:
        channel = self.tracks[track_name].channels["value"]
        keyframes = channel.keyframes
        timestamp = float(timestamp)
        new_keyframe = ChannelKeyframe(
            timestamp=timestamp,
            value=_clone_value(value),
            interpolation="hold",
        )

        if not keyframes:
            keyframes.append(new_keyframe)
            setattr(self, fingerprint_attr, fingerprint)
            return

        if math.isclose(keyframes[-1].timestamp, timestamp, abs_tol=1e-9):
            keyframes[-1] = new_keyframe
            setattr(self, fingerprint_attr, fingerprint)
            return

        if getattr(self, fingerprint_attr) == fingerprint:
            return

        keyframes.append(new_keyframe)
        setattr(self, fingerprint_attr, fingerprint)

    def _quantize_timestamp(self, timestamp: float) -> float:
        frame = int(round(max(0.0, float(timestamp)) * self.fps))
        return float(frame) / float(self.fps)

    def evaluate_at(self, timestamp: float) -> FrameSnapshot:
        if not self.timeline.sample_timestamps:
            raise ValueError("Recording is empty")
        clamped_time = max(0.0, min(float(timestamp), self.get_duration()))
        viewport = self.tracks["viewport_state"].evaluate_at(clamped_time)
        for spec in self._all_specs:
            spec.writer(
                viewport,
                _evaluate_track_channels(self.get_track(spec.public_id), clamped_time),
            )
        return FrameSnapshot(
            timestamp=clamped_time,
            viewport_state=viewport,
            settings_state=self.tracks["settings_state"].evaluate_at(clamped_time),
            image1_path=self.tracks["image1_path"].evaluate_at(clamped_time),
            image2_path=self.tracks["image2_path"].evaluate_at(clamped_time),
            name1=self.tracks["name1"].evaluate_at(clamped_time),
            name2=self.tracks["name2"].evaluate_at(clamped_time),
        )

    def materialize_snapshots(self) -> list[FrameSnapshot]:
        return [self.evaluate_at(timestamp) for timestamp in self.timeline.sample_timestamps]

    def get_duration(self) -> float:
        return self.timeline.get_duration()

    def get_keyframe_count(self) -> int:
        return sum(
            len(channel.keyframes)
            for track in self.timeline.iter_tracks()
            for channel in track.channels.values()
        )

    def get_track(self, name: str) -> TimelineTrack | None:
        wrapper = self.tracks.get(name)
        return wrapper._track if wrapper is not None else None

    def finalize_tail_keyframes(self) -> None:
        if not self.timeline.sample_timestamps:
            return

        end_timestamp = float(self.timeline.sample_timestamps[-1])
        for track in self.timeline.iter_tracks():
            for channel in track.channels.values():
                if not channel.keyframes:
                    continue
                last = channel.keyframes[-1]
                if math.isclose(last.timestamp, end_timestamp, abs_tol=1e-9):
                    continue
                channel.keyframes.append(
                    ChannelKeyframe(
                        timestamp=end_timestamp,
                        value=_clone_value(last.value),
                        interpolation=last.interpolation,
                    )
                )

    def apply_cut_markers(self, timestamps: list[float]) -> None:
        if not timestamps:
            return
        for cut_timestamp in timestamps:
            cut_timestamp = float(cut_timestamp)
            for track in self.timeline.iter_tracks():
                for channel in track.channels.values():
                    if not channel.interpolate_values or len(channel.keyframes) < 2:
                        continue
                    for index in range(1, len(channel.keyframes)):
                        current = channel.keyframes[index]
                        previous = channel.keyframes[index - 1]
                        if not math.isclose(
                            float(current.timestamp), cut_timestamp, abs_tol=1e-9
                        ):
                            continue
                        if _values_close(
                            previous.value,
                            current.value,
                            kind=channel.kind,
                        ):
                            break
                        channel.keyframes[index] = ChannelKeyframe(
                            timestamp=current.timestamp,
                            value=_clone_value(current.value),
                            interpolation="cut",
                        )
                        break

    def __bool__(self) -> bool:
        return bool(self.timeline)

def _add_value_to_track(track: TimelineTrack, timestamp: float, value: Any, *, fps: int = 60) -> bool:
    payload = (
        value
        if isinstance(value, dict)
        else _split_value_to_channels(value)
    )
    added = False
    for channel_id, channel_value in payload.items():
        channel = track.channels.get(channel_id)
        if channel is None:
            channel = track.ensure_channel(
                channel_id,
                label=channel_id.upper() if len(channel_id) <= 2 else channel_id.title(),
                kind=_channel_kind(channel_value),
                interpolate_values=_channel_interpolates(channel_value),
                source_track_id=track.id,
            )
        added = _append_channel_keyframe(channel, timestamp, channel_value, fps=fps) or added
    return added

def _append_channel_keyframe(
    channel: TimelineChannel, timestamp: float, value: Any, *, fps: int = 60
) -> bool:
    interpolation = "linear" if channel.interpolate_values else "hold"
    keyframes = channel.keyframes
    timestamp = float(timestamp)

    if not keyframes:
        keyframes.append(
            ChannelKeyframe(
                timestamp=timestamp,
                value=_clone_value(value),
                interpolation=interpolation,
            )
        )
        return True

    if math.isclose(keyframes[-1].timestamp, timestamp, abs_tol=1e-9):
        keyframes[-1] = ChannelKeyframe(
            timestamp=timestamp,
            value=_clone_value(value),
            interpolation=interpolation,
        )
        return True

    if channel.interpolate_values and _values_close(
        keyframes[-1].value, value, kind=channel.kind
    ):

        if len(keyframes) >= 2 and not _values_close(
            keyframes[-2].value, keyframes[-1].value, kind=channel.kind
        ):
            keyframes.append(
                ChannelKeyframe(
                    timestamp=timestamp,
                    value=_clone_value(value),
                    interpolation=interpolation,
                )
            )
            return True
        return False

    if not channel.interpolate_values:
        if _values_equal(keyframes[-1].value, value):
            return False

        previous_value = _clone_value(keyframes[-1].value)
        keyframes.append(
            ChannelKeyframe(
                timestamp=timestamp,
                value=previous_value,
                interpolation=interpolation,
            )
        )
        keyframes.append(
            ChannelKeyframe(
                timestamp=timestamp,
                value=_clone_value(value),
                interpolation=interpolation,
            )
        )
        return True

    time_gap = timestamp - float(keyframes[-1].timestamp)
    step_threshold = 3.0 / max(1, fps)
    if time_gap > step_threshold and _should_insert_linear_step(
        channel.kind,
        keyframes[-1].value,
        value,
    ):
        previous_value = _clone_value(keyframes[-1].value)
        keyframes.append(
            ChannelKeyframe(
                timestamp=timestamp,
                value=previous_value,
                interpolation=interpolation,
            )
        )
        keyframes.append(
            ChannelKeyframe(
                timestamp=timestamp,
                value=_clone_value(value),
                interpolation=interpolation,
            )
        )
        return True

    new_keyframe = ChannelKeyframe(
        timestamp=timestamp,
        value=_clone_value(value),
        interpolation=interpolation,
    )

    if len(keyframes) >= 2 and _is_redundant_linear_keyframe(
        keyframes[-2],
        keyframes[-1],
        new_keyframe,
        kind=channel.kind,
    ):
        keyframes[-1] = new_keyframe
        return True

    keyframes.append(new_keyframe)
    return True

def _should_insert_linear_step(kind: str, previous_value: Any, new_value: Any) -> bool:
    if kind == "scalar":
        try:
            return abs(float(new_value) - float(previous_value)) >= 0.08
        except (TypeError, ValueError):
            return False
    if kind == "vec2" and all(
        hasattr(v, "x") and hasattr(v, "y") for v in (previous_value, new_value)
    ):
        dx = float(new_value.x) - float(previous_value.x)
        dy = float(new_value.y) - float(previous_value.y)
        return math.hypot(dx, dy) >= 0.12
    return False

def _channel_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, str):
        return "enum"
    if isinstance(value, (int, float)):
        return "scalar"
    if isinstance(value, Color):
        return "color"
    if isinstance(value, Point):
        return "vec2"
    return "state"

def _channel_interpolates(value: Any) -> bool:
    return not isinstance(value, (bool, str)) and value is not None

def _values_close(left: Any, right: Any, *, kind: str) -> bool:
    if kind == "scalar" and isinstance(left, (int, float)) and isinstance(
        right, (int, float)
    ):
        return abs(float(left) - float(right)) <= 0.002
    if kind == "color" and isinstance(left, (int, float)) and isinstance(
        right, (int, float)
    ):
        return abs(float(left) - float(right)) <= 1.0
    return _values_equal(left, right)

def _is_redundant_linear_keyframe(
    previous: ChannelKeyframe,
    current: ChannelKeyframe,
    new: ChannelKeyframe,
    *,
    kind: str,
) -> bool:
    if previous.interpolation == "hold" or current.interpolation == "hold":
        return False
    span = new.timestamp - previous.timestamp
    if span <= 1e-9:
        return False
    factor = (current.timestamp - previous.timestamp) / span
    if factor <= 0.0 or factor >= 1.0:
        return False
    expected = _interpolate_value(previous.value, new.value, factor)
    return _values_close(expected, current.value, kind=kind)

def _split_value_to_channels(value: Any) -> dict[str, Any]:
    if isinstance(value, Point):
        return {"x": value.x, "y": value.y}
    if isinstance(value, Color):
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
    return {"value": value}

def _assemble_value_from_track(track: TimelineTrack, timestamp: float) -> Any:
    channel_values = _evaluate_track_channels(track, timestamp)
    if set(channel_values.keys()) == {"x", "y"}:
        return Point(x=channel_values["x"], y=channel_values["y"])
    if {"r", "g", "b", "a"}.issubset(channel_values.keys()):
        return Color(
            r=channel_values["r"],
            g=channel_values["g"],
            b=channel_values["b"],
            a=channel_values["a"],
        )
    return channel_values.get("value")

def _evaluate_track_channels(track: TimelineTrack | None, timestamp: float) -> dict[str, Any]:
    if track is None or not track.channels:
        raise ValueError("Track is not available")
    return {
        channel_id: _evaluate_channel(channel, timestamp)
        for channel_id, channel in track.channels.items()
    }

def _evaluate_channel(channel: TimelineChannel, timestamp: float) -> Any:
    if not channel.keyframes:
        raise ValueError(f"Channel '{channel.id}' has no keyframes")

    keyframes = channel.keyframes

    if timestamp <= keyframes[0].timestamp:
        return _clone_value(keyframes[0].value)

    previous = keyframes[0]
    for i in range(1, len(keyframes)):
        current = keyframes[i]
        if timestamp <= current.timestamp:

            if math.isclose(float(timestamp), float(current.timestamp), abs_tol=1e-9):
                while i + 1 < len(keyframes) and math.isclose(
                    float(keyframes[i + 1].timestamp),
                    float(current.timestamp),
                    abs_tol=1e-9,
                ):
                    previous = current
                    i += 1
                    current = keyframes[i]

                if math.isclose(
                    float(previous.timestamp),
                    float(current.timestamp),
                    abs_tol=1e-9,
                ):
                    return _clone_value(current.value)

            if current.interpolation == "cut":
                if math.isclose(
                    float(timestamp), float(current.timestamp), abs_tol=1e-9
                ):
                    return _clone_value(current.value)
                return _clone_value(previous.value)
            if (
                not channel.interpolate_values
                or current.interpolation == "hold"
                or current.timestamp <= previous.timestamp
            ):
                return _clone_value(previous.value)
            factor = (timestamp - previous.timestamp) / (
                current.timestamp - previous.timestamp
            )
            return _interpolate_value(previous.value, current.value, factor)
        previous = current

    return _clone_value(keyframes[-1].value)

def _clone_value(value: Any) -> Any:
    if isinstance(value, ViewportState):
        return value.clone()
    if hasattr(value, "freeze_for_export"):
        return value.freeze_for_export()
    if is_dataclass(value):
        return _clone_dataclass_value(value)
    return value

def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, ViewportState) and isinstance(right, ViewportState):
        return _viewport_fingerprint(left) == _viewport_fingerprint(right)
    if is_dataclass(left) and is_dataclass(right):
        return _frozen_value(left) == _frozen_value(right)
    return left == right

def _viewport_fingerprint(state: ViewportState) -> Any:
    return (
        _frozen_value(state.render_config),
        _frozen_value(state.view_state),
        _frozen_value(getattr(state, "divider_clip_rect", None)),
    )

@lru_cache(maxsize=64)
def _dataclass_field_names(cls: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(cls))

def _clone_dataclass_value(value: Any) -> Any:
    payload = {
        name: _clone_value(getattr(value, name))
        for name in _dataclass_field_names(type(value))
    }
    return type(value)(**payload)

def _frozen_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if isinstance(value, tuple):
        return tuple(_frozen_value(item) for item in value)
    if isinstance(value, list):
        return ("__list__", tuple(_frozen_value(item) for item in value))
    if isinstance(value, set):
        return ("__set__", tuple(sorted(_frozen_value(item) for item in value)))
    if isinstance(value, dict):
        return (
            "__dict__",
            tuple(
                sorted(
                    (str(key), _frozen_value(item))
                    for key, item in value.items()
                )
            ),
        )
    if is_dataclass(value):
        return (
            type(value).__name__,
            tuple(
                (name, _frozen_value(getattr(value, name)))
                for name in _dataclass_field_names(type(value))
            ),
        )
    return value

def _interpolate_value(start: Any, end: Any, factor: float) -> Any:
    if factor <= 0.0:
        return _clone_value(start)
    if factor >= 1.0:
        return _clone_value(end)

    if isinstance(start, ViewportState) and isinstance(end, ViewportState):
        return _interpolate_viewport_state(start, end, factor)
    if isinstance(start, Point) and isinstance(end, Point):
        return Point(
            x=_lerp_float(start.x, end.x, factor),
            y=_lerp_float(start.y, end.y, factor),
        )
    if isinstance(start, Color) and isinstance(end, Color):
        return Color(
            r=_lerp_int(start.r, end.r, factor),
            g=_lerp_int(start.g, end.g, factor),
            b=_lerp_int(start.b, end.b, factor),
            a=_lerp_int(start.a, end.a, factor),
        )
    if isinstance(start, bool) or isinstance(end, bool):
        return _clone_value(start)
    if isinstance(start, int) and isinstance(end, int):
        return _lerp_int(start, end, factor)
    if isinstance(start, float) and isinstance(end, float):
        return _lerp_float(start, end, factor)
    if isinstance(start, tuple) and isinstance(end, tuple) and len(start) == len(end):
        return tuple(_interpolate_value(a, b, factor) for a, b in zip(start, end))
    if isinstance(start, list) and isinstance(end, list) and len(start) == len(end):
        return [_interpolate_value(a, b, factor) for a, b in zip(start, end)]
    if is_dataclass(start) and is_dataclass(end) and type(start) is type(end):
        values = {}
        for field in fields(start):
            values[field.name] = _interpolate_value(
                getattr(start, field.name),
                getattr(end, field.name),
                factor,
            )
        return type(start)(**values)
    return _clone_value(start)

def _interpolate_viewport_state(
    start: ViewportState, end: ViewportState, factor: float
) -> ViewportState:
    interpolated = start.clone()
    interpolated.render_config = _interpolate_value(
        start.render_config, end.render_config, factor
    )
    interpolated.view_state = _interpolate_value(start.view_state, end.view_state, factor)
    interpolated.divider_clip_rect = _clone_value(
        start.divider_clip_rect if factor < 1.0 else end.divider_clip_rect
    )
    return interpolated

def _lerp_float(start: float, end: float, factor: float) -> float:
    return float(start + (end - start) * factor)

def _lerp_int(start: int, end: int, factor: float) -> int:
    return int(round(_lerp_float(float(start), float(end), factor)))
