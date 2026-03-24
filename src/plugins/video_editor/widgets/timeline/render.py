from __future__ import annotations

import bisect
import math
from types import SimpleNamespace

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

from . import layout as timeline_layout
from . import primitives as timeline_primitives
from . import theme as timeline_theme
from . import viewport as timeline_viewport

def _channel_value_at_timestamp(channel, timestamp: float, *, prefer_exact: bool = False):
    if channel is None:
        return None
    keyframes = channel.keyframes
    if not keyframes:
        return None
    if prefer_exact:
        exact_value = None
        for keyframe in keyframes:
            if math.isclose(float(keyframe.timestamp), float(timestamp), abs_tol=1e-9):
                exact_value = keyframe.value
            elif float(keyframe.timestamp) > float(timestamp):
                break
        if exact_value is not None:
            return exact_value
    return timeline_layout._evaluate_channel_at_timestamp(channel, timestamp)

def _color_track_value(track, timestamp: float) -> QColor | None:
    r = _channel_value_at_timestamp(track.channels.get("r"), timestamp, prefer_exact=True)
    g = _channel_value_at_timestamp(track.channels.get("g"), timestamp, prefer_exact=True)
    b = _channel_value_at_timestamp(track.channels.get("b"), timestamp, prefer_exact=True)
    a = _channel_value_at_timestamp(track.channels.get("a"), timestamp, prefer_exact=True)
    if None in {r, g, b}:
        return None
    try:
        return QColor(int(r), int(g), int(b), int(a if a is not None else 255))
    except (TypeError, ValueError):
        return None

def _segment_color(widget, track, channel, timestamp: float, fallback: QColor) -> QColor:
    if track.kind == "color":
        color = _color_track_value(track, timestamp)
        if color is not None:
            if color.alpha() <= 0:
                color.setAlpha(255)
            return color
    return timeline_theme.track_value_color(
        widget,
        track_id=track.id,
        track_kind=track.kind,
        channel_kind=channel.kind,
        value=timeline_layout._evaluate_channel_at_timestamp(channel, timestamp),
        fallback=fallback,
    )

def _draw_color_track_segments(
    widget,
    painter: QPainter,
    *,
    group,
    track,
    duration: float,
    logical_width: float,
    row_center_y: float,
    start_x: float,
    end_x: float,
    point_radius: float,
    stagger_px: float = 7.0,
) -> None:
    timestamps = sorted(
        {
            float(keyframe.timestamp)
            for channel in track.channels.values()
            for keyframe in channel.keyframes
        }
    )
    if not timestamps:
        return

    color_states: list[tuple[float, QColor]] = []
    for timestamp in timestamps:
        color = _color_track_value(track, timestamp)
        if color is None:
            continue
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        if color_states:
            prev_color = color_states[-1][1]
            prev_rgba = (
                prev_color.red(),
                prev_color.green(),
                prev_color.blue(),
                prev_color.alpha(),
            )
            if rgba == prev_rgba:
                continue
        color_states.append((timestamp, color))

    if not color_states:
        return

    left_bound = start_x - 12.0
    right_bound = end_x + 12.0
    segments: list[tuple[float, float, float, QColor, object, object]] = []

    for index, (timestamp, color) in enumerate(color_states):
        end_timestamp = (
            color_states[index + 1][0]
            if index + 1 < len(color_states)
            else duration
        )
        start_x_pos = timeline_layout.time_to_x(widget, timestamp, duration, logical_width)
        end_x_pos = timeline_layout.time_to_x(widget, end_timestamp, duration, logical_width)
        direction = -1.0 if index % 2 == 0 else 1.0
        y = row_center_y + direction * stagger_px
        start_keyframe_ref = SimpleNamespace(timestamp=timestamp, value=color)
        end_keyframe_ref = SimpleNamespace(timestamp=end_timestamp, value=color)
        segments.append(
            (start_x_pos, end_x_pos, y, color, start_keyframe_ref, end_keyframe_ref)
        )

    if not segments:
        return

    for x1, x2, y, color, _, _ in segments:
        if x2 < left_bound:
            continue
        if x1 > right_bound:
            break
        painter.setPen(QPen(color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    painter.setPen(QPen(QColor(40, 40, 46), 1))
    for x1, x2, y, color, start_keyframe_ref, end_keyframe_ref in segments:
        painter.setBrush(QBrush(color))
        if left_bound <= x1 <= right_bound:
            painter.drawEllipse(QPointF(x1, y), point_radius, point_radius)
            widget._hover_points.append(
                (
                    QRectF(x1 - 6, y - 6, 12, 12),
                    timeline_viewport.tooltip_for_keyframe(
                        widget,
                        group,
                        track,
                        next(iter(track.channels.values())),
                        start_keyframe_ref,
                    ),
                )
            )
        if left_bound <= x2 <= right_bound:
            painter.drawEllipse(QPointF(x2, y), point_radius, point_radius)
            widget._hover_points.append(
                (
                    QRectF(x2 - 6, y - 6, 12, 12),
                    timeline_viewport.tooltip_for_keyframe(
                        widget,
                        group,
                        track,
                        next(iter(track.channels.values())),
                        end_keyframe_ref,
                    ),
                ),
            )

def _draw_enum_track_segments(
    widget,
    painter: QPainter,
    *,
    group,
    track,
    channel,
    duration: float,
    logical_width: float,
    row_center_y: float,
    start_x: float,
    end_x: float,
    point_radius: float,
    line_col: QColor,
    stagger_px: float = 7.0,
) -> None:
    keyframes = channel.keyframes
    if not keyframes:
        return

    states: list[tuple[float, object]] = []
    for keyframe in keyframes:
        timestamp = float(keyframe.timestamp)
        value = keyframe.value
        if states and states[-1][1] == value:
            continue
        states.append((timestamp, value))

    if not states:
        return

    left_bound = start_x - 12.0
    right_bound = end_x + 12.0
    segments: list[tuple[float, float, float, object, object]] = []
    active_index = 0

    for index, (timestamp, value) in enumerate(states):
        end_timestamp = states[index + 1][0] if index + 1 < len(states) else float(duration)
        if end_timestamp < timestamp:
            continue
        if not timeline_layout._is_track_active(widget, track, channel, timestamp):
            continue
        x1 = timeline_layout.time_to_x(widget, timestamp, duration, logical_width)
        x2 = timeline_layout.time_to_x(widget, end_timestamp, duration, logical_width)
        direction = -1.0 if active_index % 2 == 0 else 1.0
        y = row_center_y + direction * stagger_px
        start_ref = SimpleNamespace(timestamp=timestamp, value=value)
        end_ref = SimpleNamespace(timestamp=end_timestamp, value=value)
        segments.append((x1, x2, y, start_ref, end_ref))
        active_index += 1

    for x1, x2, y, _, _ in segments:
        if x2 < left_bound:
            continue
        if x1 > right_bound:
            break
        if abs(x2 - x1) <= 0.01:
            continue
        painter.setPen(QPen(line_col, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(x1, y), QPointF(x2, y))

    painter.setPen(QPen(QColor(40, 40, 46), 1))
    point_positions: set[tuple[float, float]] = set()
    for x1, x2, y, start_ref, end_ref in segments:
        if left_bound <= x1 <= right_bound:
            point_key = (round(x1, 4), round(y, 4))
            if point_key not in point_positions:
                point_positions.add(point_key)
                painter.setBrush(QBrush(line_col))
                painter.drawEllipse(QPointF(x1, y), point_radius, point_radius)
                widget._hover_points.append(
                    (
                        QRectF(x1 - 6, y - 6, 12, 12),
                        timeline_viewport.tooltip_for_keyframe(
                            widget,
                            group,
                            track,
                            channel,
                            start_ref,
                        ),
                    )
                )
        if left_bound <= x2 <= right_bound and not math.isclose(
            float(end_ref.timestamp), float(duration), abs_tol=1e-9
        ):
            point_key = (round(x2, 4), round(y, 4))
            if point_key not in point_positions:
                point_positions.add(point_key)
                painter.setBrush(QBrush(line_col))
                painter.drawEllipse(QPointF(x2, y), point_radius, point_radius)
                widget._hover_points.append(
                    (
                        QRectF(x2 - 6, y - 6, 12, 12),
                        timeline_viewport.tooltip_for_keyframe(
                            widget,
                            group,
                            track,
                            channel,
                            end_ref,
                        ),
                    )
                )

def _curve_path(points: list[tuple[float, float]]) -> QPainterPath:
    path = QPainterPath()
    if not points:
        return path
    path.moveTo(QPointF(points[0][0], points[0][1]))
    if len(points) == 1:
        return path
    if len(points) == 2:
        path.lineTo(QPointF(points[1][0], points[1][1]))
        return path

    for index in range(1, len(points) - 1):
        current_x, current_y = points[index]
        next_x, next_y = points[index + 1]
        mid_x = (current_x + next_x) * 0.5
        mid_y = (current_y + next_y) * 0.5
        path.quadTo(
            QPointF(current_x, current_y),
            QPointF(mid_x, mid_y),
        )
    last_x, last_y = points[-1]
    path.lineTo(QPointF(last_x, last_y))
    return path

def draw_thumbnail_strip(widget, painter: QPainter, *, canvas_bg: QColor, content_start_x: float, strip_top: float, width: int, start_x: float, end_x: float, logical_width: float, slot_width: float) -> None:
    painter.fillRect(QRectF(content_start_x, strip_top, width - content_start_x, widget.STRIP_HEIGHT), canvas_bg)
    base_tile = timeline_viewport.get_base_tile_width(widget)
    frame_step = 1 if slot_width >= base_tile else math.ceil(base_tile / slot_width)
    draw_w = frame_step * slot_width
    first_frame = max(0, int((start_x - content_start_x) / draw_w) * frame_step)
    last_frame = min(widget._total_frames, int((end_x - content_start_x) / draw_w + 1) * frame_step + frame_step)

    frame_idx = first_frame
    while frame_idx < last_frame:
        block_x = content_start_x + frame_idx * slot_width
        block_w = draw_w
        if block_x + block_w > content_start_x + logical_width:
            block_w = content_start_x + logical_width - block_x
        if block_w <= 0:
            break
        thumb_idx = -1
        if widget._thumb_indices:
            pos = bisect.bisect_right(widget._thumb_indices, frame_idx)
            thumb_idx = widget._thumb_indices[pos - 1] if pos > 0 else widget._thumb_indices[0]
        if thumb_idx != -1:
            pix = widget._thumbnails.get(thumb_idx)
            if pix and pix.height() > 0:
                painter.drawPixmap(QRectF(block_x, strip_top, block_w, float(widget.STRIP_HEIGHT)), pix, QRectF(pix.rect()))
        frame_idx += frame_step

def _draw_keyframe_segments(widget, painter: QPainter, *, group, track, channel, duration: float, logical_width: float, row_center_y: float, start_x: float, end_x: float, line_col: QColor, point_radius: float) -> None:
    if track.kind == "color":
        _draw_color_track_segments(
            widget,
            painter,
            group=group,
            track=track,
            duration=duration,
            logical_width=logical_width,
            row_center_y=row_center_y,
            start_x=start_x,
            end_x=end_x,
            point_radius=point_radius,
        )
        return
    if track.kind == "enum":
        _draw_enum_track_segments(
            widget,
            painter,
            group=group,
            track=track,
            channel=channel,
            duration=duration,
            logical_width=logical_width,
            row_center_y=row_center_y,
            start_x=start_x,
            end_x=end_x,
            point_radius=point_radius,
            line_col=line_col,
        )
        return
    segments = timeline_layout.visible_keyframe_segments(widget, track, channel, duration, logical_width, row_center_y, start_x, end_x)
    if segments:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for segment in segments:
            curve_points = segment.get("curve_points") or [
                (segment["x1"], segment["y"]),
                (segment["x2"], segment["y"]),
            ]
            segment_col = _segment_color(
                widget,
                track,
                channel,
                float(segment["start_kf"].timestamp),
                line_col,
            )
            painter.setPen(QPen(segment_col, 1.5))
            painter.drawPath(_curve_path(curve_points))

    drawn_points: set[tuple[float, float]] = set()

    def _draw_point_once(x: float, y: float, color: QColor, tooltip: str) -> None:
        key = (round(float(x), 2), round(float(y), 2))
        if key in drawn_points:
            return
        drawn_points.add(key)
        painter.setPen(QPen(QColor(40, 40, 46), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QPointF(x, y), point_radius, point_radius)
        widget._hover_points.append((QRectF(x - 6, y - 6, 12, 12), tooltip))

    for segment in segments:
        curve_points = segment.get("curve_points") or [
            (segment["x1"], segment["y"]),
            (segment["x2"], segment["y"]),
        ]
        x1, y1 = curve_points[0]
        x2, y2 = curve_points[-1]
        start_kf = segment["start_kf"]
        end_kf = segment["end_kf"]
        start_col = _segment_color(
            widget,
            track,
            channel,
            float(start_kf.timestamp),
            line_col,
        )
        end_col = _segment_color(
            widget,
            track,
            channel,
            float(end_kf.timestamp),
            line_col,
        )
        _draw_point_once(
            x1,
            y1,
            start_col,
            timeline_viewport.tooltip_for_keyframe(widget, group, track, channel, start_kf),
        )
        _draw_point_once(
            x2,
            y2,
            end_col,
            timeline_viewport.tooltip_for_keyframe(widget, group, track, channel, end_kf),
        )

def draw_rows(widget, painter: QPainter, *, width: int, rows_top: int, rows_bottom: int, content_start_x: float, start_x: float, end_x: float, duration: float, logical_width: float, is_dark: bool, gutter_bg: QColor, track_bg: QColor, lane_bg: QColor, text_col: QColor, sep_soft: QColor) -> None:
    content_top = 0
    y = rows_top
    for item in widget._row_layout:
        if item[0] == "group":
            group = item[1]
            row_h = widget.GROUP_HEADER_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(0, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft)
            y += row_h
            continue

        if item[0] == "track_single":
            _kind, group, track, channel = item
            row_h = widget.TRACK_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            line_col = timeline_theme.track_line_color(widget, track.id, track.kind, channel.kind)
            gutter_track_bg = timeline_theme.group_content_bg(widget, track_bg, group, 46 if is_dark else 22)
            painter.fillRect(QRectF(0, y, width, row_h), gutter_track_bg)
            painter.fillRect(QRectF(content_start_x, y, width - content_start_x, row_h), lane_bg)
            painter.setPen(QPen(QColor(210, 210, 214), 1))
            painter.drawLine(0, y + row_h, width, y + row_h)
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(18, y, max(40, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
            row_center_y = y + row_h / 2.0
            painter.setPen(QPen(QColor(190, 190, 196), 1))
            painter.drawLine(content_start_x, int(row_center_y), width, int(row_center_y))
            _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=4.0)
            y += row_h
            continue

        _kind, group, track, channel, is_first_channel = item
        row_h = widget.CHANNEL_ROW_HEIGHT
        row_bottom = y + row_h
        if row_bottom <= content_top:
            y += row_h
            continue
        if y >= rows_bottom:
            break
        line_col = timeline_theme.track_line_color(widget, track.id, track.kind, channel.kind)
        if is_first_channel:
            painter.fillRect(QRectF(0, y, width, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 42 if is_dark else 18))
        else:
            painter.fillRect(QRectF(0, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, 24 if is_dark else 10))
        painter.fillRect(QRectF(content_start_x, y, width - content_start_x, row_h), lane_bg)
        painter.setPen(QPen(QColor(210, 210, 214), 1))
        painter.drawLine(0, y + row_h, width, y + row_h)
        if is_first_channel:
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(18, y, max(40, widget.LEFT_GUTTER * 0.44 - 22), row_h), track.label, text_col)
        channel_col = QColor(text_col)
        channel_col.setAlpha(215 if is_first_channel else 195)
        timeline_primitives.draw_channel_label(
            widget,
            painter,
            QRectF(max(42, widget.LEFT_GUTTER * 0.50), y, widget.LEFT_GUTTER - max(42, widget.LEFT_GUTTER * 0.50) - 12, row_h),
            channel.label,
            channel_col,
            line_col,
        )
        row_center_y = y + row_h / 2.0
        painter.setPen(QPen(QColor(190, 190, 196), 1))
        painter.drawLine(content_start_x, int(row_center_y), width, int(row_center_y))
        _draw_keyframe_segments(widget, painter, group=group, track=track, channel=channel, duration=duration, logical_width=logical_width, row_center_y=row_center_y, start_x=start_x, end_x=end_x, line_col=line_col, point_radius=3.5)
        y += row_h

def draw_footer_and_ruler(widget, painter: QPainter, *, width: int, content_start_x: float, footer_height: int, footer_top: int, scrollbar_strip_top: int, ruler_top: int, ruler_bottom: int, scroll_offset: int, viewport_width: int, duration: float, logical_width: float, start_x: float, end_x: float, is_dark: bool, footer_bg: QColor, sep_strong: QColor, sep_soft: QColor, grid_col: QColor, text_col: QColor, sb_idle: QColor, sb_hover: QColor) -> None:
    painter.fillRect(QRectF(content_start_x, footer_top, width - content_start_x, footer_height), footer_bg)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(0, int(footer_top), width, int(footer_top))
    timeline_primitives.draw_vertical_scrollbar_track(widget, painter, footer_bg)
    sb_rect = QRectF(scroll_offset + content_start_x, scrollbar_strip_top, max(0.0, viewport_width - content_start_x), widget.SCROLLBAR_STRIP_HEIGHT)
    timeline_viewport.draw_inner_scrollbar(widget, painter, sb_rect, sb_idle, sb_hover)
    painter.setPen(QPen(sep_soft, 1))
    painter.drawLine(0, int(ruler_top) - 1, width, int(ruler_top) - 1)
    painter.setPen(QPen(grid_col, 1))
    painter.drawLine(content_start_x, ruler_bottom - 1, width, ruler_bottom - 1)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(0, widget.height() - 1, width, widget.height() - 1)
    if duration <= 0:
        return
    step_sec = timeline_viewport.choose_ruler_step(duration, logical_width)
    minor_divisions = timeline_viewport.choose_ruler_subdivisions(step_sec, duration, logical_width)
    ruler_font = painter.font()
    ruler_font.setPointSize(max(8, ruler_font.pointSize() - 2))
    painter.setFont(ruler_font)
    if minor_divisions > 1:
        minor_step = step_sec / minor_divisions
        minor_tick_col = QColor(grid_col)
        minor_tick_col.setAlpha(150 if is_dark else 180)
        painter.setPen(QPen(minor_tick_col, 1))
        minor_steps_count = int(math.floor(duration / minor_step + 1e-9))
        for minor_index in range(minor_steps_count + 1):
            if minor_index % minor_divisions == 0:
                continue
            t_minor = minor_index * minor_step
            x = content_start_x + (t_minor / duration) * logical_width
            if x >= start_x - 20 and x <= end_x + 20:
                is_mid_tick = minor_divisions % 2 == 0 and minor_index % (minor_divisions // 2) == 0
                tick_bottom = ruler_top + (7 if is_mid_tick else 5)
                painter.drawLine(int(x), ruler_top, int(x), tick_bottom)
    major_steps_count = int(math.floor(duration / step_sec + 1e-9))
    for major_index in range(major_steps_count + 1):
        t = major_index * step_sec
        x = content_start_x + (t / duration) * logical_width
        if x >= start_x - 50 and x <= end_x + 50:
            label_text = timeline_viewport.format_time(t, step_sec)
            painter.setPen(QPen(text_col, 1))
            painter.drawLine(int(x), ruler_top, int(x), ruler_top + 10)
            text_rect = QRectF(x + 4, ruler_top + 11, 52, max(18, ruler_bottom - ruler_top - 11 - 4))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label_text)

def draw_sticky_gutter_overlay(widget, painter: QPainter, *, scroll_offset: int, rows_top: int, rows_bottom: int, footer_top: int, gutter_bg: QColor, track_bg: QColor, text_col: QColor, sep_color: QColor | None = None, sep_soft: QColor | None = None) -> None:
    gx = scroll_offset
    content_top = 0
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    painter.save()
    painter.setClipRect(QRectF(gx, 0, widget.LEFT_GUTTER + 2, footer_top))
    timeline_primitives.draw_gutter_background(widget, painter, QRectF(gx, 0, widget.LEFT_GUTTER, widget.height()), gutter_bg, sep_soft if sep_soft is not None else QColor(text_col))
    y = rows_top
    for item in widget._row_layout:
        if item[0] == "group":
            group = item[1]
            row_h = widget.GROUP_HEADER_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            timeline_primitives.draw_group_header_label(widget, painter, QRectF(gx, y, widget.LEFT_GUTTER, row_h), group, group.label, text_col, sep_soft if sep_soft is not None else QColor(text_col))
            y += row_h
        elif item[0] == "track_single":
            _kind, group, track, _channel = item
            row_h = widget.TRACK_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 46 if widget.theme_manager.is_dark() else 22))
            timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER - 30), row_h), track.label, text_col)
            y += row_h
        else:
            _kind, group, track, channel, is_first_channel = item
            row_h = widget.CHANNEL_ROW_HEIGHT
            row_bottom = y + row_h
            if row_bottom <= content_top:
                y += row_h
                continue
            if y >= rows_bottom:
                break
            line_col = timeline_theme.track_color(widget, track.kind, channel.kind)
            if is_first_channel:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, track_bg, group, 42 if widget.theme_manager.is_dark() else 18))
                timeline_primitives.draw_track_title_label(widget, painter, QRectF(gx + 18, y, max(40.0, widget.LEFT_GUTTER * 0.44 - 22), row_h), track.label, text_col)
            else:
                painter.fillRect(QRectF(gx, y, widget.LEFT_GUTTER, row_h), timeline_theme.group_content_bg(widget, gutter_bg, group, 24 if widget.theme_manager.is_dark() else 10))
            channel_col = QColor(text_col)
            channel_col.setAlpha(215 if is_first_channel else 195)
            ch_x = gx + max(42.0, widget.LEFT_GUTTER * 0.50)
            timeline_primitives.draw_channel_label(widget, painter, QRectF(ch_x, y, widget.LEFT_GUTTER - (ch_x - gx) - 12, row_h), channel.label, channel_col, line_col)
            y += row_h
    line_color = sep_color if sep_color is not None else text_col
    painter.setPen(QPen(line_color, 1))
    painter.drawLine(int(gx + widget.LEFT_GUTTER), 0, int(gx + widget.LEFT_GUTTER), widget.height())
    painter.restore()

def draw_sticky_right_gutter_overlay(widget, painter: QPainter, *, gutter_x: float, footer_bg: QColor, sep_soft: QColor) -> None:
    gutter_width = timeline_viewport.right_inset(widget)
    if gutter_width <= 0:
        return
    painter.save()
    painter.setClipRect(QRectF(gutter_x, 0, gutter_width, widget.height()))
    timeline_primitives.draw_right_gutter_background(
        widget,
        painter,
        QRectF(gutter_x, 0, gutter_width, widget.height()),
        footer_bg,
        sep_soft,
    )
    painter.restore()

def paint_timeline(widget, painter: QPainter, event) -> None:
    timeline_viewport.update_vertical_scrollbar(widget)
    colors = timeline_theme.build_theme_colors(widget)
    is_dark = colors["is_dark"]
    accent = colors["accent"]
    text_col = colors["text_col"]
    canvas_bg = colors["canvas_bg"]
    gutter_bg = colors["gutter_bg"]
    track_bg = colors["track_bg"]
    lane_bg = colors["lane_bg"]
    grid_col = colors["grid_col"]
    footer_bg = colors["footer_bg"]
    sep_strong = colors["sep_strong"]
    sep_soft = colors["sep_soft"]
    sb_idle = colors["sb_idle"]
    sb_hover = colors["sb_hover"]

    widget._hover_points = []
    painter.fillRect(widget.rect(), canvas_bg)
    timeline_primitives.draw_gutter_background(widget, painter, QRectF(0, 0, widget.LEFT_GUTTER, widget.height()), gutter_bg, sep_soft)
    if widget._total_frames <= 0:
        return
    width = widget.width()
    logical_width = timeline_viewport.get_logical_width(widget)
    slot_width = timeline_viewport.get_slot_width(widget)
    content_scroll_y = timeline_viewport.vertical_scroll_value(widget)
    strip_top = -content_scroll_y
    footer_height = timeline_viewport.footer_height(widget)
    footer_top = widget.height() - footer_height
    scrollbar_strip_top = footer_top
    ruler_top = footer_top + widget.SCROLLBAR_STRIP_HEIGHT + 2
    ruler_bottom = widget.height() - 6
    content_start_x = widget.LEFT_GUTTER
    scroll_area = timeline_viewport.get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = timeline_viewport.get_viewport_width(widget)
    visible_right = scroll_offset + viewport_width
    content_right = visible_right - timeline_viewport.right_inset(widget)
    content_viewport_width = max(0, viewport_width - timeline_viewport.right_inset(widget))
    clip_rect = event.rect()
    start_x = max(content_start_x, clip_rect.left())
    end_x = min(clip_rect.right(), content_right)
    painter.save()
    painter.setClipRect(QRectF(0, 0, content_right, footer_top))
    draw_thumbnail_strip(widget, painter, canvas_bg=canvas_bg, content_start_x=content_start_x, strip_top=strip_top, width=content_right, start_x=start_x, end_x=end_x, logical_width=logical_width, slot_width=slot_width)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(text_col, 1))
    duration = timeline_layout.content_duration(widget)
    painter.setPen(QPen(sep_strong, 1))
    painter.drawLine(widget.LEFT_GUTTER, 0, widget.LEFT_GUTTER, widget.height())
    _content_top, rows_bottom = timeline_viewport.content_viewport_bounds(widget)
    rows_top = widget.STRIP_HEIGHT - content_scroll_y
    draw_rows(widget, painter, width=content_right, rows_top=rows_top, rows_bottom=rows_bottom, content_start_x=content_start_x, start_x=start_x, end_x=end_x, duration=duration, logical_width=logical_width, is_dark=is_dark, gutter_bg=gutter_bg, track_bg=track_bg, lane_bg=lane_bg, text_col=text_col, sep_soft=sep_soft)
    painter.restore()
    if widget._has_selection:
        x_anchor = timeline_viewport.frame_to_pos(widget, widget._anchor_index)
        x_drag = timeline_viewport.frame_to_pos(widget, widget._drag_index)
        x_start = min(x_anchor, x_drag)
        x_end = max(x_anchor, x_drag)
        fill = QColor(accent)
        fill.setAlpha(45)
        painter.fillRect(QRectF(x_start, 0, max(0.0, min(x_end, content_right) - x_start), footer_top), fill)
    draw_footer_and_ruler(widget, painter, width=content_right, content_start_x=content_start_x, footer_height=footer_height, footer_top=footer_top, scrollbar_strip_top=scrollbar_strip_top, ruler_top=ruler_top, ruler_bottom=ruler_bottom, scroll_offset=scroll_offset, viewport_width=content_viewport_width, duration=duration, logical_width=logical_width, start_x=start_x, end_x=end_x, is_dark=is_dark, footer_bg=footer_bg, sep_strong=sep_strong, sep_soft=sep_soft, grid_col=grid_col, text_col=text_col, sb_idle=sb_idle, sb_hover=sb_hover)
    x_head = timeline_viewport.visual_pos_from_index(widget, widget._scrub_visual_index if widget._scrub_visual_index is not None else widget._visual_index)
    timeline_primitives.draw_playhead(widget, painter, x_head=x_head, footer_top=footer_top, width=content_right)
    draw_sticky_gutter_overlay(widget, painter, scroll_offset=scroll_offset, rows_top=rows_top, rows_bottom=rows_bottom, footer_top=footer_top, gutter_bg=gutter_bg, track_bg=track_bg, text_col=text_col, sep_color=sep_strong, sep_soft=sep_soft)
    draw_sticky_right_gutter_overlay(
        widget,
        painter,
        gutter_x=content_right,
        footer_bg=footer_bg,
        sep_soft=sep_soft,
    )
