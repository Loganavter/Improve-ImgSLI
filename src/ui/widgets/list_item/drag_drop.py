"""Drag-and-drop / row-move state machine for RatingListItem.

Functions take the owning ``RatingListItem`` as their first argument (see
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases/ module" pattern).
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.config import get_dragdrop_service
from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip


def find_panel(widget):
    # Generic ListPanel (the app picker's panels are ListPanel instances).
    parent = widget.parentWidget()
    while parent is not None:
        if parent.objectName() == "ListPanel":
            return parent
        parent = parent.parentWidget()
    return None


def drag_indices(widget) -> list[int]:
    """Indices to move: multi-selection if this row is in it, else self."""
    panel = find_panel(widget)
    if panel is None:
        return [widget.index]
    getter = getattr(panel, "selected_indices", None)
    if not callable(getter):
        return [widget.index]
    selected = sorted(getter())
    if widget.index in selected and len(selected) > 1:
        return selected
    return [widget.index]


def set_batch_dragging_state(widget, dragging: bool, indices) -> None:
    panel = find_panel(widget)
    if panel is not None and hasattr(panel, "set_items_dragging"):
        panel.set_items_dragging(indices, bool(dragging))
        return
    widget.set_dragging_state(dragging)


def drag_allowed(widget) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        getter = getattr(parent, "is_drag_enabled", None)
        if callable(getter):
            return bool(getter())
        parent = parent.parentWidget()
    return True


def handle_button_event_filter(widget, obj, event):
    """Drag-cancel watchdog for the nested +/- buttons.

    Returns True if the event was swallowed (mirrors the original
    ``eventFilter`` contract), else None so the caller falls through to
    ``super().eventFilter()``.
    """
    btn_plus = getattr(widget, "btn_plus", None)
    btn_minus = getattr(widget, "btn_minus", None)
    if obj not in (btn_plus, btn_minus):
        return None

    if event.type() == QEvent.Type.MouseMove and (
        event.buttons() & Qt.MouseButton.LeftButton
    ):
        if widget._active_button is obj and not widget._is_drag_initiated:
            try:
                obj._initial_delay_timer.stop()
                obj._repeat_timer.stop()
            except Exception:
                pass
            distance = (
                event.globalPosition() - widget._drag_start_pos_global
            ).manhattanLength()
            if distance >= QApplication.startDragDistance():
                from ui.widgets.list_item import rating_gestures

                rating_gestures.cancel_button_interaction(widget)

        return True

    return None


def mouse_move_event(widget, event) -> None:
    if not (event.buttons() & Qt.MouseButton.LeftButton):
        return
    if widget._is_drag_initiated:
        return
    if not drag_allowed(widget):
        return

    current_global_pos = widget.mapToGlobal(event.position().toPoint())
    start_global_pos = widget.mapToGlobal(widget.drag_start_pos)
    distance = (current_global_pos - start_global_pos).manhattanLength()

    if distance >= QApplication.startDragDistance():
        if widget.item_type == "image" and widget._active_button:
            try:
                widget._active_button._initial_delay_timer.stop()
                widget._active_button._repeat_timer.stop()
            except Exception:
                pass
            if widget._gesture_tx is not None:
                widget._gesture_tx.rollback()
                widget._gesture_tx = None

        widget.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()

        widget._is_drag_initiated = True
        panel = find_panel(widget)
        if panel is not None and widget.index not in panel.selected_indices():
            # Dragging a row outside the marquee selection collapses it;
            # dragging a selected row keeps it (multi-move).
            panel.clear_selection()
        service = get_dragdrop_service()
        if service is not None and not service.is_dragging():
            service.start_drag(widget, event)
        widget._notify_flyout_drop_indicator(event.globalPosition())


def notify_flyout_clear_indicator(widget) -> None:
    widget._notify_flyout_clear_indicator()
