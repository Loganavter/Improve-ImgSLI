from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from functools import lru_cache
from typing import Any

from core.store_viewport import ViewportState
from domain.types import Color, Point
from plugins.video_editor.services.timeline import (
    ChannelKeyframe,
    TimelineChannel,
    TimelineTrack,
)

_CONTINUOUS_CURVE_TRACK_IDS = {
    "filename_overlay.font_size",
    "filename_overlay.font_weight",
    "filename_overlay.text_alpha",
    "splitter.main.position",
    "text.font_size",
    "text.font_weight",
    "text.alpha",
}

def _prefers_continuous_curve(track_id: str | None) -> bool:
    if not track_id:
        return False
    return track_id in _CONTINUOUS_CURVE_TRACK_IDS

def add_value_to_track(track: TimelineTrack, timestamp: float, value: Any, *, fps: int = 60) -> bool:
    payload = value if isinstance(value, dict) else split_value_to_channels(value)
    if track.kind == "vec2" and {"x", "y"}.issubset(payload.keys()):
        return append_vec2_track_keyframe(track, timestamp, payload, fps=fps)
    added = False
    for channel_id, channel_value in payload.items():
        channel = track.channels.get(channel_id)
        if channel is None:
            channel_kind_name = track.kind if track.kind == "color" else channel_kind(channel_value)
            channel = track.ensure_channel(
                channel_id,
                label=channel_id.upper() if len(channel_id) <= 2 else channel_id.title(),
                kind=channel_kind_name,
                interpolate_values=(False if channel_kind_name == "color" else channel_interpolates(channel_value)),
                source_track_id=track.id,
                prefer_continuous_curve=_prefers_continuous_curve(track.id),
            )
        added = append_channel_keyframe(channel, timestamp, channel_value, fps=fps) or added
    return added

def append_vec2_track_keyframe(
    track: TimelineTrack,
    timestamp: float,
    payload: dict[str, Any],
    *,
    fps: int = 60,
) -> bool:
    x_channel = track.channels.get("x")
    y_channel = track.channels.get("y")
    if x_channel is None or y_channel is None:
        added = False
        for channel_id, channel_value in payload.items():
            channel = track.channels.get(channel_id)
            if channel is None:
                channel = track.ensure_channel(
                    channel_id,
                    label=channel_id.upper(),
                    kind="scalar",
                    interpolate_values=True,
                    source_track_id=track.id,
                )
            added = append_channel_keyframe(channel, timestamp, channel_value, fps=fps) or added
        return added

    timestamp = float(timestamp)
    current_point = Point(float(payload["x"]), float(payload["y"]))
    interpolation = "linear"
    if not x_channel.keyframes or not y_channel.keyframes:
        x_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["x"]), interpolation=interpolation))
        y_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["y"]), interpolation=interpolation))
        return True

    if math.isclose(x_channel.keyframes[-1].timestamp, timestamp, abs_tol=1e-9):
        x_channel.keyframes[-1] = ChannelKeyframe(timestamp=timestamp, value=float(payload["x"]), interpolation=interpolation)
        y_channel.keyframes[-1] = ChannelKeyframe(timestamp=timestamp, value=float(payload["y"]), interpolation=interpolation)
        return True

    previous_point = Point(float(x_channel.keyframes[-1].value), float(y_channel.keyframes[-1].value))
    if values_close(previous_point, current_point, kind="vec2"):
        if (
            len(x_channel.keyframes) >= 2
            and len(y_channel.keyframes) >= 2
            and not values_close(
                Point(float(x_channel.keyframes[-2].value), float(y_channel.keyframes[-2].value)),
                previous_point,
                kind="vec2",
            )
        ):
            x_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["x"]), interpolation=interpolation))
            y_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["y"]), interpolation=interpolation))
            return True
        return False

    time_gap = timestamp - float(x_channel.keyframes[-1].timestamp)
    step_threshold = 3.0 / max(1, fps)
    if time_gap > step_threshold and should_insert_linear_step("vec2", previous_point, current_point):
        x_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(previous_point.x), interpolation=interpolation))
        y_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(previous_point.y), interpolation=interpolation))
        x_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["x"]), interpolation=interpolation))
        y_channel.keyframes.append(ChannelKeyframe(timestamp=timestamp, value=float(payload["y"]), interpolation=interpolation))
        return True

    new_x = ChannelKeyframe(timestamp=timestamp, value=float(payload["x"]), interpolation=interpolation)
    new_y = ChannelKeyframe(timestamp=timestamp, value=float(payload["y"]), interpolation=interpolation)
    if (
        len(x_channel.keyframes) >= 2
        and len(y_channel.keyframes) >= 2
        and is_redundant_linear_keyframe(
            ChannelKeyframe(timestamp=x_channel.keyframes[-2].timestamp, value=Point(float(x_channel.keyframes[-2].value), float(y_channel.keyframes[-2].value)), interpolation=x_channel.keyframes[-2].interpolation),
            ChannelKeyframe(timestamp=x_channel.keyframes[-1].timestamp, value=Point(float(x_channel.keyframes[-1].value), float(y_channel.keyframes[-1].value)), interpolation=x_channel.keyframes[-1].interpolation),
            ChannelKeyframe(timestamp=timestamp, value=current_point, interpolation=interpolation),
            kind="vec2",
        )
    ):
        x_channel.keyframes[-1] = new_x
        y_channel.keyframes[-1] = new_y
        return True
    x_channel.keyframes.append(new_x)
    y_channel.keyframes.append(new_y)
    return True

def append_channel_keyframe(channel: TimelineChannel, timestamp: float, value: Any, *, fps: int = 60) -> bool:
    interpolation = "linear" if channel.interpolate_values else "hold"
    keyframes = channel.keyframes
    timestamp = float(timestamp)
    step_threshold = 3.0 / max(1, fps)

    if not keyframes:
        keyframes.append(ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation))
        channel.hold_compact_pending = False
        return True
    if math.isclose(keyframes[-1].timestamp, timestamp, abs_tol=1e-9):
        keyframes[-1] = ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation)
        channel.hold_compact_pending = False
        return True

    if channel.interpolate_values and values_close(keyframes[-1].value, value, kind=channel.kind):
        if len(keyframes) >= 2 and not values_close(keyframes[-2].value, keyframes[-1].value, kind=channel.kind):
            keyframes.append(ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation))
            return True
        return False

    if not channel.interpolate_values:
        if values_equal(keyframes[-1].value, value):
            channel.hold_compact_pending = False
            return False
        if (
            channel.hold_compact_pending
            and len(keyframes) >= 2
            and (timestamp - float(keyframes[-1].timestamp)) <= step_threshold
        ):
            previous_value = clone_value(keyframes[-2].value)
            keyframes[-2] = ChannelKeyframe(timestamp=timestamp, value=previous_value, interpolation=interpolation)
            keyframes[-1] = ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation)
            channel.hold_compact_pending = True
            return True
        previous_value = clone_value(keyframes[-1].value)
        keyframes.append(ChannelKeyframe(timestamp=timestamp, value=previous_value, interpolation=interpolation))
        keyframes.append(ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation))
        channel.hold_compact_pending = True
        return True

    time_gap = timestamp - float(keyframes[-1].timestamp)
    if (
        not channel.prefer_continuous_curve
        and time_gap > step_threshold
        and should_insert_linear_step(channel.kind, keyframes[-1].value, value)
    ):
        previous_value = clone_value(keyframes[-1].value)
        keyframes.append(ChannelKeyframe(timestamp=timestamp, value=previous_value, interpolation=interpolation))
        keyframes.append(ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation))
        return True

    new_keyframe = ChannelKeyframe(timestamp=timestamp, value=clone_value(value), interpolation=interpolation)
    if (
        not channel.prefer_continuous_curve
        and len(keyframes) >= 2
        and is_redundant_linear_keyframe(keyframes[-2], keyframes[-1], new_keyframe, kind=channel.kind)
    ):
        keyframes[-1] = new_keyframe
        return True
    keyframes.append(new_keyframe)
    return True

def should_insert_linear_step(kind: str, previous_value: Any, new_value: Any) -> bool:
    if kind == "scalar":
        try:
            return abs(float(new_value) - float(previous_value)) >= 0.08
        except (TypeError, ValueError):
            return False
    if kind == "vec2" and all(hasattr(v, "x") and hasattr(v, "y") for v in (previous_value, new_value)):
        dx = float(new_value.x) - float(previous_value.x)
        dy = float(new_value.y) - float(previous_value.y)
        return math.hypot(dx, dy) >= 0.12
    return False

def channel_kind(value: Any) -> str:
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

def channel_interpolates(value: Any) -> bool:
    return not isinstance(value, (bool, str, Color)) and value is not None

def values_close(left: Any, right: Any, *, kind: str) -> bool:
    if kind == "scalar" and isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 0.002
    if kind == "color" and isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= 1.0
    if kind == "vec2" and isinstance(left, Point) and isinstance(right, Point):
        return math.hypot(float(right.x) - float(left.x), float(right.y) - float(left.y)) <= 0.002
    return values_equal(left, right)

def is_redundant_linear_keyframe(
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
    expected = interpolate_value(previous.value, new.value, factor)
    return values_close(expected, current.value, kind=kind)

def split_value_to_channels(value: Any) -> dict[str, Any]:
    if isinstance(value, Point):
        return {"x": value.x, "y": value.y}
    if isinstance(value, Color):
        return {"r": value.r, "g": value.g, "b": value.b, "a": value.a}
    return {"value": value}

def assemble_value_from_track(track: TimelineTrack, timestamp: float) -> Any:
    channel_values = evaluate_track_channels(track, timestamp)
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

def evaluate_track_channels(track: TimelineTrack | None, timestamp: float) -> dict[str, Any]:
    if track is None or not track.channels:
        raise ValueError("Track is not available")
    return {
        channel_id: evaluate_channel(channel, timestamp)
        for channel_id, channel in track.channels.items()
    }

def evaluate_channel(channel: TimelineChannel, timestamp: float) -> Any:
    if not channel.keyframes:
        raise ValueError(f"Channel '{channel.id}' has no keyframes")
    keyframes = channel.keyframes
    if timestamp <= keyframes[0].timestamp:
        return clone_value(keyframes[0].value)

    previous = keyframes[0]
    for index in range(1, len(keyframes)):
        current = keyframes[index]
        if timestamp <= current.timestamp:
            if math.isclose(float(timestamp), float(current.timestamp), abs_tol=1e-9):
                while index + 1 < len(keyframes) and math.isclose(
                    float(keyframes[index + 1].timestamp),
                    float(current.timestamp),
                    abs_tol=1e-9,
                ):
                    previous = current
                    index += 1
                    current = keyframes[index]
                if math.isclose(float(previous.timestamp), float(current.timestamp), abs_tol=1e-9):
                    return clone_value(current.value)

            if current.interpolation == "cut":
                if math.isclose(float(timestamp), float(current.timestamp), abs_tol=1e-9):
                    return clone_value(current.value)
                return clone_value(previous.value)
            if (
                not channel.interpolate_values
                or current.interpolation == "hold"
                or current.timestamp <= previous.timestamp
            ):
                return clone_value(previous.value)
            factor = (timestamp - previous.timestamp) / (current.timestamp - previous.timestamp)
            return interpolate_value(previous.value, current.value, factor)
        previous = current
    return clone_value(keyframes[-1].value)

def clone_value(value: Any) -> Any:
    if isinstance(value, ViewportState):
        return value.clone()
    if hasattr(value, "freeze_for_export"):
        return value.freeze_for_export()
    if is_dataclass(value):
        return clone_dataclass_value(value)
    if isinstance(value, dict):
        import copy
        return copy.deepcopy(value)
    if isinstance(value, (list, set)):
        import copy
        return copy.deepcopy(value)
    return value

def values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, ViewportState) and isinstance(right, ViewportState):
        return viewport_fingerprint(left) == viewport_fingerprint(right)
    if is_dataclass(left) and is_dataclass(right):
        return frozen_value(left) == frozen_value(right)
    return left == right

def viewport_fingerprint(state: ViewportState) -> Any:
    return (
        frozen_value(state.render_config),
        frozen_value(state.view_state),
        frozen_value(getattr(state, "overlay_clip_rect", None)),
    )

@lru_cache(maxsize=64)
def dataclass_field_names(cls: type) -> tuple[str, ...]:
    return tuple(field.name for field in fields(cls))

def clone_dataclass_value(value: Any) -> Any:
    payload = {
        name: clone_value(getattr(value, name))
        for name in dataclass_field_names(type(value))
    }
    return type(value)(**payload)

def frozen_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if isinstance(value, tuple):
        return tuple(frozen_value(item) for item in value)
    if isinstance(value, list):
        return ("__list__", tuple(frozen_value(item) for item in value))
    if isinstance(value, set):
        return ("__set__", tuple(sorted(frozen_value(item) for item in value)))
    if isinstance(value, dict):
        return (
            "__dict__",
            tuple(sorted((str(key), frozen_value(item)) for key, item in value.items())),
        )
    if is_dataclass(value):
        return (
            type(value).__name__,
            tuple(
                (name, frozen_value(getattr(value, name)))
                for name in dataclass_field_names(type(value))
            ),
        )
    return value

def interpolate_value(start: Any, end: Any, factor: float) -> Any:
    if factor <= 0.0:
        return clone_value(start)
    if factor >= 1.0:
        return clone_value(end)

    if isinstance(start, ViewportState) and isinstance(end, ViewportState):
        return interpolate_viewport_state(start, end, factor)
    if isinstance(start, Point) and isinstance(end, Point):
        return Point(x=lerp_float(start.x, end.x, factor), y=lerp_float(start.y, end.y, factor))
    if isinstance(start, Color) and isinstance(end, Color):
        return Color(
            r=lerp_int(start.r, end.r, factor),
            g=lerp_int(start.g, end.g, factor),
            b=lerp_int(start.b, end.b, factor),
            a=lerp_int(start.a, end.a, factor),
        )
    if isinstance(start, bool) or isinstance(end, bool):
        return clone_value(start)
    if isinstance(start, int) and isinstance(end, int):
        return lerp_int(start, end, factor)
    if isinstance(start, float) and isinstance(end, float):
        return lerp_float(start, end, factor)
    if isinstance(start, tuple) and isinstance(end, tuple) and len(start) == len(end):
        return tuple(interpolate_value(a, b, factor) for a, b in zip(start, end))
    if isinstance(start, list) and isinstance(end, list) and len(start) == len(end):
        return [interpolate_value(a, b, factor) for a, b in zip(start, end)]
    if is_dataclass(start) and is_dataclass(end) and type(start) is type(end):
        values = {}
        for field in fields(start):
            values[field.name] = interpolate_value(
                getattr(start, field.name),
                getattr(end, field.name),
                factor,
            )
        return type(start)(**values)
    return clone_value(start)

def interpolate_viewport_state(start: ViewportState, end: ViewportState, factor: float) -> ViewportState:
    interpolated = start.clone()
    interpolated.render_config = interpolate_value(start.render_config, end.render_config, factor)
    interpolated.view_state = interpolate_value(start.view_state, end.view_state, factor)
    interpolated.overlay_clip_rect = clone_value(
        start.overlay_clip_rect if factor < 1.0 else end.overlay_clip_rect
    )
    return interpolated

def lerp_float(start: float, end: float, factor: float) -> float:
    return float(start + (end - start) * factor)

def lerp_int(start: int, end: int, factor: float) -> int:
    return int(round(lerp_float(float(start), float(end), factor)))
