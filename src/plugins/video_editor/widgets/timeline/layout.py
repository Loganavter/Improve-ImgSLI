from __future__ import annotations

import logging
import math
from typing import Any

from PyQt6.QtCore import QPointF, QRectF
from . import viewport as timeline_viewport

logger = logging.getLogger("ImproveImgSLI")

MOTION_DIRECTION_TOLERANCE = 0.0015
MOTION_GAP_TOLERANCE = 0.0015
MOTION_SESSION_MERGE_DISTANCE = 0.06
MOTION_SESSION_GAP_DISTANCE = 0.08

def _segment_payload(
    x1: float,
    y: float,
    x2: float,
    start_kf: Any,
    end_kf: Any,
    *,
    curve_points: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    points = curve_points or [(x1, y), (x2, y)]
    return {
        "x1": x1,
        "y": y,
        "x2": x2,
        "start_kf": start_kf,
        "end_kf": end_kf,
        "curve_points": points,
    }

def _append_curve_point(
    points: list[tuple[float, float]], x: float, y: float, *, tolerance: float = 0.01
) -> None:
    if points and abs(points[-1][0] - x) <= tolerance and abs(points[-1][1] - y) <= tolerance:
        points[-1] = (x, y)
        return
    points.append((x, y))

def _interaction_session_value(widget, timestamp: float) -> str | None:
    session_track = _find_track(widget, "__input.interaction_session")
    if session_track is None:
        return None
    session_channel = session_track.channels.get("value")
    if session_channel is None or not session_channel.keyframes:
        return None
    value = None
    for keyframe in session_channel.keyframes:
        if math.isclose(float(keyframe.timestamp), float(timestamp), abs_tol=1e-9):
            value = keyframe.value
            break
    if value is None:
        value = _evaluate_channel_at_timestamp(session_channel, timestamp)
    return None if value is None else str(value)

def _segment_has_value_change(channel, start_kf, end_kf) -> bool:
    if not channel.interpolate_values:
        return True
    if channel.kind == "scalar":
        try:
            return not math.isclose(
                float(start_kf.value),
                float(end_kf.value),
                abs_tol=0.002,
            )
        except (TypeError, ValueError):
            return start_kf.value != end_kf.value
    return start_kf.value != end_kf.value

def _layout_values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), abs_tol=1e-9)
    return left == right

def _motion_vector(value_a: Any, value_b: Any) -> tuple[float, ...] | None:
    if isinstance(value_a, (int, float)) and isinstance(value_b, (int, float)):
        return (float(value_b) - float(value_a),)
    if all(hasattr(v, "x") and hasattr(v, "y") for v in (value_a, value_b)):
        return (
            float(value_b.x) - float(value_a.x),
            float(value_b.y) - float(value_a.y),
        )
    return None

def _component_direction(
    component: float, tolerance: float = MOTION_DIRECTION_TOLERANCE
) -> int:
    if component > tolerance:
        return 1
    if component < -tolerance:
        return -1
    return 0

def _directions_compatible(
    prev_vec: tuple[float, ...], next_vec: tuple[float, ...]
) -> bool:
    for prev_component, next_component in zip(prev_vec, next_vec):
        prev_dir = _component_direction(prev_component)
        next_dir = _component_direction(next_component)
        if prev_dir == 0 or next_dir == 0:
            continue
        if prev_dir != next_dir:
            return False
    return True

def _is_effectively_stationary(
    vec: tuple[float, ...], tolerance: float = MOTION_GAP_TOLERANCE
) -> bool:
    return all(abs(float(component)) <= tolerance for component in vec)

def _motion_magnitude(vec: tuple[float, ...] | None) -> float:
    if vec is None:
        return 0.0
    return math.sqrt(sum(float(component) * float(component) for component in vec))

def _motion_merge_decision(
    widget,
    prev_start_kf,
    prev_end_kf,
    start_kf,
    end_kf,
) -> tuple[bool, dict[str, Any]]:
    prev_session = _interaction_session_value(widget, float(prev_end_kf.timestamp))
    next_session = _interaction_session_value(widget, float(start_kf.timestamp))
    same_session = (
        prev_session is not None
        and next_session is not None
        and prev_session == next_session
    )
    prev_vec = _motion_vector(prev_start_kf.value, prev_end_kf.value)
    next_vec = _motion_vector(start_kf.value, end_kf.value)
    gap_vec = _motion_vector(prev_end_kf.value, start_kf.value)
    diagnostics = {
        "prev_session": prev_session,
        "next_session": next_session,
        "same_session": same_session,
        "prev_vec": prev_vec,
        "next_vec": next_vec,
        "gap_vec": gap_vec,
        "prev_mag": _motion_magnitude(prev_vec),
        "next_mag": _motion_magnitude(next_vec),
        "gap_mag": _motion_magnitude(gap_vec),
        "reason": "merge",
    }
    if (
        prev_session is not None
        and next_session is not None
        and prev_session != next_session
    ):
        diagnostics["reason"] = "session_changed"
        return False, diagnostics
    if prev_vec is None or next_vec is None:
        diagnostics["reason"] = "missing_motion_vector"
        return True, diagnostics

    if not _directions_compatible(prev_vec, next_vec):
        if not same_session:
            diagnostics["reason"] = "direction_conflict_cross_session"
            return False, diagnostics
        if max(_motion_magnitude(prev_vec), _motion_magnitude(next_vec)) > MOTION_SESSION_MERGE_DISTANCE:
            diagnostics["reason"] = "direction_conflict_large_motion"
            return False, diagnostics

    if gap_vec is None:
        diagnostics["reason"] = "missing_gap_vector"
        return True, diagnostics
    if _is_effectively_stationary(gap_vec):
        diagnostics["reason"] = "stationary_gap"
        return True, diagnostics
    if same_session and _motion_magnitude(gap_vec) <= MOTION_SESSION_GAP_DISTANCE:
        diagnostics["reason"] = "small_gap_same_session"
        return True, diagnostics
    diagnostics["reason"] = "gap_too_large"
    return False, diagnostics

def _curve_y_for_keyframe(
    active_segment_index: int,
    row_center_y: float,
    stagger_px: float,
    point_index: int,
) -> float:
    base_direction = -1.0 if active_segment_index % 2 == 0 else 1.0
    if point_index % 2 == 0:
        return row_center_y + base_direction * stagger_px
    return row_center_y + base_direction * stagger_px * 0.35

def rebuild_row_layout(widget) -> None:
    widget._row_layout = []
    if widget._timeline_model is None:
        return

    for group in widget._timeline_model.groups.values():
        group_items = []
        for track in group.tracks.values():
            if not should_show_track(widget, track):
                continue
            visible = visible_channels(widget, track)
            if not visible:
                continue
            if len(visible) == 1:
                group_items.append(("track_single", group, track, visible[0]))
            else:
                for index, channel in enumerate(visible):
                    group_items.append(("channel", group, track, channel, index == 0))

        if group_items:
            widget._row_layout.append(("group", group))
            if getattr(widget, "_is_group_collapsed")(group):
                continue
            else:
                widget._row_layout.extend(group_items)

def group_toggle_hit(widget, pos) -> Any | None:
    if not widget._row_layout:
        return None

    scroll_area = timeline_viewport.get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(widget)
    y = widget.STRIP_HEIGHT - timeline_viewport.vertical_scroll_value(widget)

    for item in widget._row_layout:
        if y >= rows_bottom:
            break
        if item[0] == "group":
            group = item[1]
            rect = widget._group_chevron_rect(
                widget._group_header_rect(scroll_offset, y)
            )
            if rect.contains(QPointF(pos)):
                return group
            y += widget.GROUP_HEADER_HEIGHT
        elif item[0] == "track_single":
            y += widget.TRACK_ROW_HEIGHT
        else:
            y += widget.CHANNEL_ROW_HEIGHT

    return None

def visible_channels(widget, track):
    if track.id == "view.interpolation_method":
        enabled_track = _find_track(widget, "magnifier.default.enabled")
        enabled_channel = enabled_track.channels.get("value") if enabled_track is not None else None
        if enabled_channel is not None and any(bool(kf.value) for kf in enabled_channel.keyframes):
            return [channel for channel in track.channels.values() if channel.keyframes]
    if track.kind == "color":
        channels = [channel for channel in track.channels.values() if channel.keyframes]
        if not channels:
            return []
        changed = next((channel for channel in channels if channel_has_changes(channel)), None)
        return [changed or channels[0]]
    channels = []
    for channel in track.channels.values():
        if not channel.keyframes:
            continue
        if channel_has_changes(channel):
            channels.append(channel)
    return channels

def channel_has_changes(channel) -> bool:
    if len(channel.keyframes) < 2:
        return False

    first = channel.keyframes[0].value
    for keyframe in channel.keyframes[1:]:
        if keyframe.value != first:
            return True
    return False

def should_show_track(widget, track) -> bool:
    if track.id.startswith("__") or track.kind in {"state", "source", "label"}:
        return False

    if track.id in widget._PROMINENT_TRACK_IDS:
        return any(channel_has_changes(channel) for channel in track.channels.values())

    if track.kind == "mask3":
        return any(channel_has_changes(channel) for channel in track.channels.values())

    if track.kind == "color":
        return any(channel_has_changes(channel) for channel in track.channels.values())

    if track.kind in {"bool", "enum"}:
        if track.id == "view.interpolation_method":
            enabled_track = _find_track(widget, "magnifier.default.enabled")
            enabled_channel = enabled_track.channels.get("value") if enabled_track is not None else None
            if enabled_channel is not None and any(bool(kf.value) for kf in enabled_channel.keyframes):
                return True
        return any(channel_has_changes(channel) for channel in track.channels.values())

    return any(channel_has_changes(channel) for channel in track.channels.values())

def rows_height(widget) -> int:
    height = 0
    for item in widget._row_layout:
        if item[0] == "group":
            height += widget.GROUP_HEADER_HEIGHT
        elif item[0] == "track_single":
            height += widget.TRACK_ROW_HEIGHT
        else:
            height += widget.CHANNEL_ROW_HEIGHT
    return height

def ensure_preferred_height(widget) -> None:
    final_height = max(
        120,
        widget.STRIP_HEIGHT
        + widget.RULER_HEIGHT
        + widget.SCROLLBAR_STRIP_HEIGHT
        + max(widget.TRACK_ROW_HEIGHT * 2, 40),
    )
    widget.setMinimumHeight(final_height)
    timeline_viewport.update_vertical_scrollbar(widget)

def content_duration(widget) -> float:
    if widget._timeline_model is not None and widget._timeline_model.sample_timestamps:
        return widget._timeline_model.get_duration()
    return widget.get_total_duration()

def time_to_frame_index(widget, timestamp: float) -> float:
    if widget._total_frames <= 0:
        return 0.0
    frame_index = max(0.0, float(timestamp) * widget._fps)
    return max(0.0, min(frame_index, max(0.0, widget._total_frames - 1)))

def time_to_x(widget, timestamp: float, duration: float, logical_width: float) -> float:
    if duration <= 0 or logical_width <= 0:
        return float(widget.LEFT_GUTTER)
    clamped = max(0.0, min(float(timestamp), duration))
    return timeline_viewport.visual_pos_from_index(widget, time_to_frame_index(widget, clamped))

def _find_track(widget, track_id: str):
    timeline_model = getattr(widget, "_timeline_model", None)
    if timeline_model is None:
        return None
    for group in timeline_model.groups.values():
        track = group.tracks.get(track_id)
        if track is not None:
            return track
    return None

def _evaluate_channel_at_timestamp(channel, timestamp: float):
    keyframes = channel.keyframes
    if not keyframes:
        return None
    if timestamp <= keyframes[0].timestamp:
        return keyframes[0].value
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
                    return current.value
            return previous.value
        previous = current
    return keyframes[-1].value

def _is_track_active(widget, track, channel, timestamp: float) -> bool:
    if channel.kind == "bool":
        value = _evaluate_channel_at_timestamp(channel, timestamp)
        return bool(value)

    if channel.kind == "enum":
        value = _evaluate_channel_at_timestamp(channel, timestamp)
        if track.id == "comparison.diff_mode":
            return str(value).lower() != "off"
        if track.id == "comparison.channel_view_mode":
            return str(value).upper() != "RGB"
        return bool(value)

    if track.id.startswith("magnifier.default.") and track.id != "magnifier.default.enabled":
        enabled_track = _find_track(widget, "magnifier.default.enabled")
        if enabled_track is not None:
            enabled_channel = enabled_track.channels.get("value")
            if enabled_channel is not None:
                return bool(_evaluate_channel_at_timestamp(enabled_channel, timestamp))

    return True

def _activity_boundary_timestamps(widget, track, channel, start_ts: float, end_ts: float) -> list[float]:
    boundaries: list[float] = [float(start_ts), float(end_ts)]

    def append_channel_boundaries(source_channel) -> None:
        if source_channel is None:
            return
        for keyframe in source_channel.keyframes:
            ts = float(keyframe.timestamp)
            if start_ts < ts < end_ts:
                boundaries.append(ts)

    if channel.kind in {"bool", "enum"}:
        append_channel_boundaries(channel)

    if track.id.startswith("magnifier.default.") and track.id != "magnifier.default.enabled":
        enabled_track = _find_track(widget, "magnifier.default.enabled")
        enabled_channel = enabled_track.channels.get("value") if enabled_track is not None else None
        append_channel_boundaries(enabled_channel)

    return sorted(set(boundaries))

def _active_time_ranges(widget, track, channel, start_ts: float, end_ts: float) -> list[tuple[float, float]]:
    bounds = _activity_boundary_timestamps(widget, track, channel, start_ts, end_ts)
    ranges: list[tuple[float, float]] = []
    for idx in range(len(bounds) - 1):
        seg_start = bounds[idx]
        seg_end = bounds[idx + 1]
        if seg_end <= seg_start:
            continue
        probe = seg_start + (seg_end - seg_start) * 0.5
        if _is_track_active(widget, track, channel, probe):
            ranges.append((seg_start, seg_end))
    return ranges

def visible_keyframe_segments(
    widget,
    track,
    channel,
    duration: float,
    logical_width: float,
    row_center_y: float,
    start_x: float,
    end_x: float,
    stagger_px: float = 7.0,
) -> list[dict[str, Any]]:
    if not channel.keyframes:
        return []

    keyframes = channel.keyframes
    is_active_bool_channel = channel.kind == "bool"
    if len(keyframes) < 2:
        keyframe = keyframes[0]
        if not _is_track_active(widget, track, channel, keyframe.timestamp):
            return []
        x = time_to_x(widget, keyframe.timestamp, duration, logical_width)
        if x < start_x - 12.0 or x > end_x + 12.0:
            return []
        point_y = row_center_y if is_active_bool_channel else row_center_y - stagger_px
        return [(x, point_y, x, keyframe, keyframe)]

    segments: list[dict[str, Any]] = []
    left_bound = start_x - 12.0
    right_bound = end_x + 12.0
    active_segment_index = 0

    for idx in range(len(keyframes) - 1):
        start_kf = keyframes[idx]
        end_kf = keyframes[idx + 1]
        if track.id == "view.interpolation_method":
            if not _is_track_active(widget, track, channel, start_kf.timestamp):
                continue
            x1 = time_to_x(widget, start_kf.timestamp, duration, logical_width)
            x2 = time_to_x(widget, end_kf.timestamp, duration, logical_width)
            if abs(x2 - x1) <= 0.01:
                continue
            direction = -1.0 if active_segment_index % 2 == 0 else 1.0
            active_segment_index += 1
            if x2 < left_bound:
                continue
            if x1 > right_bound:
                break
            y = row_center_y if is_active_bool_channel else row_center_y + direction * stagger_px
            segments.append(
                _segment_payload(x1, y, x2, start_kf, end_kf)
            )
            continue

        if math.isclose(
            float(start_kf.timestamp), float(end_kf.timestamp), abs_tol=1e-9
        ) and _segment_has_value_change(channel, start_kf, end_kf):
            prev_kf = keyframes[idx - 1] if idx > 0 else None
            next_kf = keyframes[idx + 2] if idx + 2 < len(keyframes) else None
            if (
                channel.interpolate_values
                and prev_kf is not None
                and _layout_values_equal(prev_kf.value, start_kf.value)
                and next_kf is not None
                and float(next_kf.timestamp) > float(end_kf.timestamp)
                and not _layout_values_equal(next_kf.value, end_kf.value)
            ):
                continue
            x = time_to_x(widget, start_kf.timestamp, duration, logical_width)
            if left_bound <= x <= right_bound:
                y = row_center_y if is_active_bool_channel else row_center_y
                segments.append(
                    _segment_payload(x, y, x, start_kf, end_kf,
                                     curve_points=[(x, y)])
                )
            continue

        for seg_start_ts, seg_end_ts in _active_time_ranges(
            widget, track, channel, start_kf.timestamp, end_kf.timestamp
        ):
            if end_kf.interpolation == "cut":
                continue
            if channel.interpolate_values and not _segment_has_value_change(
                channel, start_kf, end_kf
            ):
                continue
            x1 = time_to_x(widget, seg_start_ts, duration, logical_width)
            x2 = time_to_x(widget, seg_end_ts, duration, logical_width)
            if (
                channel.interpolate_values
                and segments
                and start_kf.interpolation != "cut"
            ):
                should_merge, diagnostics = _motion_merge_decision(
                    widget,
                    segments[-1]["start_kf"],
                    segments[-1]["end_kf"],
                    start_kf,
                    end_kf,
                )
                if should_merge:
                    prev_segment = segments[-1]
                    curve_points = list(prev_segment["curve_points"])
                    point_index = len(curve_points)
                    curve_y = _curve_y_for_keyframe(
                        active_segment_index=max(0, active_segment_index - 1),
                        row_center_y=row_center_y,
                        stagger_px=stagger_px,
                        point_index=point_index,
                    )
                    _append_curve_point(curve_points, x1, curve_y)
                    _append_curve_point(curve_points, x2, curve_y)
                    segments[-1] = _segment_payload(
                        prev_segment["x1"],
                        prev_segment["y"],
                        x2,
                        prev_segment["start_kf"],
                        end_kf,
                        curve_points=curve_points,
                    )
                    continue
            direction = -1.0 if active_segment_index % 2 == 0 else 1.0
            if x2 < left_bound:
                continue
            if x1 > right_bound:
                break
            y = row_center_y if is_active_bool_channel else row_center_y + direction * stagger_px
            active_segment_index += 1
            if is_active_bool_channel:
                curve_points = [(x1, y), (x2, y)]
            else:
                curve_points = [
                    (x1, _curve_y_for_keyframe(active_segment_index - 1, row_center_y, stagger_px, 0)),
                    (x2, _curve_y_for_keyframe(active_segment_index - 1, row_center_y, stagger_px, 1)),
                ]
            segments.append(
                _segment_payload(
                    x1,
                    y,
                    x2,
                    start_kf,
                    end_kf,
                    curve_points=curve_points,
                )
            )
    return segments
