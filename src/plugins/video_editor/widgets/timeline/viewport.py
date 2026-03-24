from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QScrollArea, QWidget

from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from . import layout as timeline_layout

def footer_height(widget) -> int:
    return 42 + widget.SCROLLBAR_STRIP_HEIGHT

def vertical_scrollbar_width(widget) -> int:
    return 10

def vertical_scrollbar_gutter_width(widget) -> int:
    return 16

def right_inset(widget) -> int:
    return vertical_scrollbar_gutter_width(widget) if widget._v_scrollbar.isVisible() else 0

def content_viewport_bounds(widget) -> tuple[int, int]:
    content_top = 0
    content_bottom = widget.height() - footer_height(widget) - 2
    return content_top, content_bottom

def vertical_scroll_value(widget) -> int:
    return widget._v_scrollbar.value() if widget._v_scrollbar.isVisible() else 0

def update_vertical_scrollbar(widget) -> None:
    old_geometry = widget._v_scrollbar.geometry()
    was_visible = widget._v_scrollbar.isVisible()
    content_top, content_bottom = content_viewport_bounds(widget)
    viewport_h = max(0, content_bottom - content_top)
    content_h = max(0, widget.STRIP_HEIGHT + timeline_layout.rows_height(widget))
    max_scroll = max(0, content_h - viewport_h)
    widget._v_scrollbar.blockSignals(True)
    widget._v_scrollbar.setRange(0, max_scroll)
    widget._v_scrollbar.setPageStep(max(1, viewport_h))
    widget._v_scrollbar.setSingleStep(max(12, widget.CHANNEL_ROW_HEIGHT))
    widget._v_scrollbar.setValue(min(widget._v_scrollbar.value(), max_scroll))
    widget._v_scrollbar.blockSignals(False)
    widget._v_scrollbar.setVisible(max_scroll > 0)
    if max_scroll > 0:
        width = vertical_scrollbar_width(widget)
        gutter_width = vertical_scrollbar_gutter_width(widget)
        scroll_area = get_scroll_area(widget)
        scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
        viewport_width = get_viewport_width(widget)
        widget._v_scrollbar.setGeometry(
            max(0, scroll_offset + viewport_width - gutter_width + (gutter_width - width) // 2),
            content_top,
            width,
            viewport_h,
        )
        widget._v_scrollbar.raise_()
    new_geometry = widget._v_scrollbar.geometry()
    if was_visible or widget._v_scrollbar.isVisible():
        dirty = QRect(old_geometry)
        if not dirty.isNull():
            dirty = dirty.united(new_geometry)
        else:
            dirty = QRect(new_geometry)
        if not dirty.isNull():
            widget.update(dirty.adjusted(-4, -4, 4, 4))

def get_thumb_aspect_ratio(widget) -> float:
    if widget._thumb_indices:
        first = widget._thumb_indices[0]
        pm = widget._thumbnails.get(first)
        if pm and pm.height() > 0:
            return pm.width() / pm.height()
    return 16 / 9

def get_base_tile_width(widget) -> float:
    return max(1.0, widget.STRIP_HEIGHT * get_thumb_aspect_ratio(widget))

def frame_span(widget) -> int:
    return max(1, widget._total_frames - 1)

def get_logical_width(widget) -> float:
    base = get_base_tile_width(widget)
    return max(1.0, frame_span(widget) * base * widget._zoom_level)

def get_slot_width(widget) -> float:
    if widget._total_frames <= 1:
        return 1.0
    return get_logical_width(widget) / frame_span(widget)

def compute_total_frames(widget) -> int:
    duration = widget.get_total_duration()
    if duration <= 0:
        return 0
    return max(1, int(math.ceil(duration * widget._fps)) + 1)

def get_viewport_width(widget) -> int:
    viewport_width = 800
    parent = widget.parent()
    if parent:
        if isinstance(parent, QScrollArea):
            viewport_width = parent.viewport().width()
        elif isinstance(parent, QWidget):
            if isinstance(parent.parent(), QScrollArea):
                viewport_width = parent.parent().viewport().width()
            else:
                viewport_width = parent.width()
    return viewport_width

def calculate_min_zoom(widget) -> float:
    if widget._total_frames <= 0:
        return 0.1
    viewport_width = max(
        1,
        get_viewport_width(widget) - widget.LEFT_GUTTER - right_inset(widget),
    )
    content_at_zoom1 = widget._total_frames * get_base_tile_width(widget)
    if content_at_zoom1 <= 0:
        return 1.0
    return viewport_width / content_at_zoom1

def fit_view(widget) -> None:
    widget._zoom_level = calculate_min_zoom(widget)
    widget._last_min_zoom = widget._zoom_level
    update_fixed_width(widget)
    widget.update()

def update_fixed_width(widget) -> None:
    if widget._total_frames <= 0:
        return
    content_width = int(
        math.ceil(widget.LEFT_GUTTER + get_logical_width(widget) + right_inset(widget))
    )
    viewport_width = max(1, get_viewport_width(widget) - right_inset(widget))
    final_width = max(content_width, viewport_width + right_inset(widget))
    if widget.width() != final_width:
        widget.setFixedWidth(final_width)
    widget.update()

def format_time(seconds: float, step: float | None = None) -> str:
    seconds = round(float(seconds), 6)
    m = int(seconds // 60)
    s = int(seconds % 60)
    frac = max(0.0, seconds - math.floor(seconds))

    decimals = 1
    if step is not None and step > 0:
        if step >= 1.0:
            decimals = 0
        else:
            decimals = max(1, min(3, int(math.ceil(-math.log10(step) - 1e-9))))

    if decimals <= 0:
        return f"{m}:{s:02d}" if m > 0 else f"{s}"

    frac_text = f"{frac:.{decimals}f}".split(".")[1]
    if m > 0:
        return f"{m}:{s:02d}.{frac_text}"
    return f"{s}.{frac_text}"

def choose_ruler_step(duration: float, logical_width: float) -> float:
    if duration <= 0 or logical_width <= 0:
        return 1.0
    min_label_spacing_px = 72.0
    for step in (
        0.001,
        0.002,
        0.005,
        0.01,
        0.02,
        0.05,
        0.1,
        0.2,
        0.25,
        0.5,
        1.0,
        2.0,
        5.0,
        10.0,
        15.0,
        30.0,
        60.0,
    ):
        if (step / duration) * logical_width >= min_label_spacing_px:
            return step
    return 60.0

def choose_ruler_subdivisions(
    major_step: float,
    duration: float,
    logical_width: float,
) -> int:
    if major_step <= 0 or duration <= 0 or logical_width <= 0:
        return 1
    major_px = (major_step / duration) * logical_width
    if major_px >= 360:
        return 10
    if major_px >= 180:
        return 5
    if major_px >= 96:
        return 4
    if major_px >= 64:
        return 2
    return 1

def pos_to_frame(widget, x: float) -> int:
    if widget._total_frames <= 0:
        return 0
    logical_width = get_logical_width(widget)
    if logical_width <= 0:
        return 0
    ratio = (x - widget.LEFT_GUTTER) / logical_width
    frame = int(ratio * frame_span(widget))
    return max(0, min(frame, widget._total_frames - 1))

def pos_to_float_index(widget, x: float) -> float:
    if widget._total_frames <= 0:
        return 0.0
    logical_width = get_logical_width(widget)
    if logical_width <= 0:
        return 0.0
    ratio = (float(x) - widget.LEFT_GUTTER) / logical_width
    index = ratio * frame_span(widget)
    return max(0.0, min(index, float(widget._total_frames - 1)))

def frame_to_pos(widget, frame: int) -> int:
    if widget._total_frames <= 0:
        return widget.LEFT_GUTTER
    return int(widget.LEFT_GUTTER + frame * get_slot_width(widget))

def visual_pos_from_index(widget, float_index: float) -> float:
    if widget._total_frames <= 0:
        return float(widget.LEFT_GUTTER)
    return widget.LEFT_GUTTER + float_index * get_slot_width(widget)

def get_scroll_area(widget):
    parent = widget.parent()
    while parent:
        if isinstance(parent, QScrollArea):
            return parent
        parent = parent.parent()
    return None

def get_inner_sb_handle_rect(widget, sb_rect: QRectF) -> QRectF:
    scroll_area = get_scroll_area(widget)
    if scroll_area is None:
        return QRectF()
    h_bar = scroll_area.horizontalScrollBar()
    if h_bar.maximum() <= h_bar.minimum():
        return QRectF()
    total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
    if total <= 0:
        return QRectF()
    padding = 8.0
    track_w = sb_rect.width() - padding * 2
    if track_w <= 0:
        return QRectF()
    handle_w = max(20.0, (h_bar.pageStep() / total) * track_w)
    scroll_range = h_bar.maximum() - h_bar.minimum()
    ratio = (h_bar.value() - h_bar.minimum()) / scroll_range
    handle_x = sb_rect.left() + padding + ratio * (track_w - handle_w)
    thickness = 6.0
    handle_y = sb_rect.top() + (sb_rect.height() - thickness) / 2.0
    return QRectF(handle_x, handle_y, handle_w, thickness)

def draw_inner_scrollbar(
    widget,
    painter: QPainter,
    sb_rect: QRectF,
    idle_color: QColor | None = None,
    hover_color: QColor | None = None,
) -> None:
    if sb_rect.height() < 4:
        return
    handle_rect = get_inner_sb_handle_rect(widget, sb_rect)
    if handle_rect.isEmpty():
        return
    if idle_color is None:
        idle_color = QColor(0, 0, 0, 65)
    if hover_color is None:
        hover_color = QColor(0, 0, 0, 95)
    if widget._sb_dragging:
        color = widget.theme_manager.get_color("accent")
    elif sb_rect.contains(QPointF(widget.mapFromGlobal(widget.cursor().pos()))):
        color = hover_color
    else:
        color = idle_color
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    radius = handle_rect.height() / 2.0
    painter.drawRoundedRect(handle_rect, radius, radius)
    painter.restore()

def sb_strip_rect(widget) -> QRectF:
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    viewport_width = max(0, get_viewport_width(widget) - right_inset(widget))
    footer_top = widget.height() - footer_height(widget)
    return QRectF(
        scroll_offset + widget.LEFT_GUTTER,
        footer_top,
        max(0.0, viewport_width - widget.LEFT_GUTTER),
        widget.SCROLLBAR_STRIP_HEIGHT,
    )

def update_hover_tooltip(widget, pos) -> None:
    point = QPointF(pos)
    for rect, text in widget._hover_points:
        if rect.contains(point):
            widget._hover_tooltip_text = text
            widget._hover_tooltip_pos = widget.mapToGlobal(pos)
            if not widget._tooltip_timer.isActive():
                widget._tooltip_timer.start()
            return
    widget._tooltip_timer.stop()
    widget._hover_tooltip_text = None
    widget._hover_tooltip_pos = None
    PathTooltip.get_instance().hide_tooltip()

def show_hover_tooltip(widget) -> None:
    if widget._hover_tooltip_text and widget._hover_tooltip_pos is not None:
        PathTooltip.get_instance().show_tooltip(
            widget._hover_tooltip_pos,
            widget._hover_tooltip_text,
        )

def is_on_gutter_handle(widget, x: int) -> bool:
    scroll_area = get_scroll_area(widget)
    scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
    return abs(x - (scroll_offset + widget.LEFT_GUTTER)) <= widget.GUTTER_RESIZE_MARGIN

def tooltip_for_keyframe(widget, group, track, channel, keyframe) -> str:
    if track.kind == "color":
        r = timeline_layout._evaluate_channel_at_timestamp(track.channels.get("r"), keyframe.timestamp)
        g = timeline_layout._evaluate_channel_at_timestamp(track.channels.get("g"), keyframe.timestamp)
        b = timeline_layout._evaluate_channel_at_timestamp(track.channels.get("b"), keyframe.timestamp)
        a = timeline_layout._evaluate_channel_at_timestamp(track.channels.get("a"), keyframe.timestamp)
        if None not in {r, g, b}:
            value_text = f"rgba({int(r)}, {int(g)}, {int(b)}, {int(a if a is not None else 255)})"
            return (
                f"{group.label} / {track.label}"
                f"\nTime: {format_time(keyframe.timestamp)}"
                f"\nColor: {value_text}"
            )
    return (
        f"{group.label} / {track.label}"
        f"\nTime: {format_time(keyframe.timestamp)}"
        f"\n{channel.label}: {format_value(keyframe.value)}"
    )

def format_value(value) -> str:
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
