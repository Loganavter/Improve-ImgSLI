from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt

from shared_toolkit.ui.widgets.atomic.tooltips import PathTooltip
from . import layout as timeline_layout
from . import viewport as timeline_viewport

def mouse_press_event(widget, event):
    if event.button() != Qt.MouseButton.LeftButton:
        return

    toggle_group = timeline_layout.group_toggle_hit(widget, event.pos())
    if toggle_group is not None:
        widget._tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        widget._mouse_down = False
        widget._press_pos = None
        widget._toggle_group_collapsed(toggle_group)
        event.accept()
        return

    if timeline_viewport.is_on_gutter_handle(widget, event.pos().x()):
        widget._is_resizing_gutter = True
        widget._tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        widget.setCursor(Qt.CursorShape.SplitHCursor)
        event.accept()
        return

    sb_rect = timeline_viewport.sb_strip_rect(widget)
    if sb_rect.contains(QPointF(event.pos())):
        scroll_area = timeline_viewport.get_scroll_area(widget)
        if scroll_area is not None:
            h_bar = scroll_area.horizontalScrollBar()
            handle_rect = timeline_viewport.get_inner_sb_handle_rect(widget, sb_rect)
            padding = 8.0
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(20.0, (h_bar.pageStep() / total) * track_w) if total > 0 else 20.0
            if handle_rect.isEmpty() or not handle_rect.contains(QPointF(event.pos())):
                scroll_range = h_bar.maximum() - h_bar.minimum()
                viewport_x = event.pos().x() - h_bar.value()
                rel_x = viewport_x - widget.LEFT_GUTTER - padding - handle_w / 2.0
                if track_w - handle_w > 0 and scroll_range > 0:
                    new_val = h_bar.minimum() + int(rel_x / (track_w - handle_w) * scroll_range)
                    h_bar.setValue(max(h_bar.minimum(), min(new_val, h_bar.maximum())))
            widget._sb_dragging = True
            widget._sb_drag_start_x = event.pos().x() - h_bar.value()
            widget._sb_drag_start_value = h_bar.value()
            widget.update()
        event.accept()
        return

    x = max(widget.LEFT_GUTTER, event.pos().x())
    frame = timeline_viewport.pos_to_frame(widget, x)
    widget._scrub_visual_index = float(frame)
    widget._mouse_down = True
    widget._press_pos = event.pos()
    widget._press_frame = frame

    shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
    if shift_pressed:
        widget._is_selecting = True
        widget._has_selection = True
        widget._anchor_index = frame
        widget._drag_index = frame
    else:
        widget._is_selecting = False
        widget._has_selection = False
        widget._anchor_index = frame
        widget._drag_index = frame

    widget.set_current_frame(frame)
    widget.headMoved.emit(widget._current_index)
    widget.update()

def mouse_move_event(widget, event):
    if widget._sb_dragging:
        scroll_area = timeline_viewport.get_scroll_area(widget)
        if scroll_area is not None:
            sb_rect = timeline_viewport.sb_strip_rect(widget)
            h_bar = scroll_area.horizontalScrollBar()
            padding = 8.0
            track_w = sb_rect.width() - padding * 2
            total = h_bar.maximum() - h_bar.minimum() + h_bar.pageStep()
            handle_w = max(20.0, (h_bar.pageStep() / total) * track_w) if total > 0 else 20.0
            scroll_range = h_bar.maximum() - h_bar.minimum()
            if track_w - handle_w > 0 and scroll_range > 0:
                current_vp_x = event.pos().x() - h_bar.value()
                dx = current_vp_x - widget._sb_drag_start_x
                delta_val = int(dx / (track_w - handle_w) * scroll_range)
                h_bar.setValue(
                    max(h_bar.minimum(), min(widget._sb_drag_start_value + delta_val, h_bar.maximum()))
                )
        widget.update()
        event.accept()
        return

    if widget._is_resizing_gutter:
        scroll_area = timeline_viewport.get_scroll_area(widget)
        scroll_offset = scroll_area.horizontalScrollBar().value() if scroll_area else 0
        widget.LEFT_GUTTER = max(
            widget.MIN_LEFT_GUTTER,
            min(event.pos().x() - scroll_offset, widget.MAX_LEFT_GUTTER),
        )
        widget._last_min_zoom = timeline_viewport.calculate_min_zoom(widget)
        timeline_viewport.update_fixed_width(widget)
        widget.update()
        event.accept()
        return

    timeline_viewport.update_hover_tooltip(widget, event.pos())
    if timeline_layout.group_toggle_hit(widget, event.pos()) is not None:
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
    elif timeline_viewport.is_on_gutter_handle(widget, event.pos().x()):
        widget.setCursor(Qt.CursorShape.SplitHCursor)
    else:
        widget.unsetCursor()

    if event.buttons() & Qt.MouseButton.LeftButton:
        scrub_x = max(widget.LEFT_GUTTER, event.pos().x())
        frame = timeline_viewport.pos_to_frame(widget, scrub_x)
        widget._scrub_visual_index = float(frame)
        shift_pressed = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if (
            shift_pressed
            and not widget._is_selecting
            and widget._mouse_down
            and widget._press_pos is not None
        ):
            moved = (event.pos() - widget._press_pos).manhattanLength()
            if moved >= widget._drag_threshold_px:
                widget._is_selecting = True
                widget._has_selection = True
                widget._anchor_index = widget._press_frame
                widget._drag_index = frame

        if widget._is_selecting:
            widget._drag_index = frame

        widget.set_current_frame(frame)
        widget.headMoved.emit(widget._current_index)
        widget.update()

def leave_event(widget, event):
    widget.unsetCursor()
    widget._tooltip_timer.stop()
    widget._hover_tooltip_text = None
    widget._hover_tooltip_pos = None
    PathTooltip.get_instance().hide_tooltip()

def mouse_release_event(widget, event):
    if event.button() == Qt.MouseButton.LeftButton:
        if widget._sb_dragging:
            widget._sb_dragging = False
            widget.update()
            event.accept()
            return
        if widget._is_resizing_gutter:
            widget._is_resizing_gutter = False
            widget.unsetCursor()
            event.accept()
            return
        widget._scrub_visual_index = None
        widget._mouse_down = False
        widget._press_pos = None
    if widget._has_selection and widget._anchor_index == widget._drag_index:
        widget._has_selection = False
    widget._is_selecting = False
    widget.update()
