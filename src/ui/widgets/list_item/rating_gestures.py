"""Rating +/- gesture handling for RatingListItem.

Functions take the owning ``RatingListItem`` as their first argument (see
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases/ module" pattern).
"""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QCursor


def _clear_panel_selection(widget) -> None:
    from ui.widgets.list_item import drag_drop

    panel = drag_drop.find_panel(widget)
    if panel is not None and hasattr(panel, "clear_selection"):
        panel.clear_selection()


def on_plus_clicked(widget) -> None:
    if widget._is_drag_initiated or widget._active_button not in (None, widget.btn_plus):
        return
    _clear_panel_selection(widget)
    if widget._gesture_tx is not None:
        widget._gesture_tx.apply_delta(+1)
    else:
        widget._increment_rating(widget.list_num, widget.index)
    update_label_from_store(widget)


def on_minus_clicked(widget) -> None:
    if widget._is_drag_initiated or widget._active_button not in (None, widget.btn_minus):
        return
    _clear_panel_selection(widget)
    if widget._gesture_tx is not None:
        widget._gesture_tx.apply_delta(-1)
    else:
        widget._decrement_rating(widget.list_num, widget.index)
    update_label_from_store(widget)


def on_button_pressed(widget, button) -> None:
    if widget.item_type != "image":
        return
    widget._active_button = button
    widget._drag_start_pos_global = QPointF(QCursor.pos())
    widget.drag_start_pos = widget.mapFromGlobal(QCursor.pos())
    starting_score = widget._get_rating(widget.list_num, widget.index)
    widget._gesture_tx = widget._create_rating_gesture(
        widget.list_num,
        widget.index,
        starting_score,
    )


def on_button_released(widget, button) -> None:
    if widget._active_button is not button:
        return
    if widget._gesture_tx is not None and not widget._is_drag_initiated:
        widget._gesture_tx.commit()
        widget._gesture_tx = None
        update_label_from_store(widget)
    widget._active_button = None


def cancel_button_interaction(widget) -> None:
    if widget._gesture_tx is not None:
        widget._gesture_tx.rollback()
        widget._gesture_tx = None
    widget._active_button = None


def update_label_from_store(widget) -> None:
    if widget.item_type != "image":
        return
    widget.rating_label.setText(str(widget._get_rating(widget.list_num, widget.index)))


def wheel_event(widget, event) -> None:
    if widget.item_type != "image":
        return

    pos = event.position().toPoint()

    if widget.rating_label.geometry().contains(pos):
        delta = event.angleDelta().y()
        if delta > 0:
            widget._increment_rating(widget.list_num, widget.index)
        else:
            widget._decrement_rating(widget.list_num, widget.index)
        update_label_from_store(widget)
        event.accept()
    else:
        event.ignore()


def maybe_commit_gesture(widget) -> None:
    if (
        widget.item_type == "image"
        and widget._gesture_tx is not None
        and widget._active_button is None
    ):
        widget._gesture_tx.commit()
        widget._gesture_tx = None
        update_label_from_store(widget)
