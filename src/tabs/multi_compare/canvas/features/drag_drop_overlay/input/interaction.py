"""Slot drag-drop interaction helpers.

Drag-distance-threshold math and QDrag kickoff live here, operating purely
on the canvas widget ``handler`` — mirrors ``image_compare``'s
``divider/interaction.py`` pattern (a free function taking ``handler``, not
a method), so the gesture binding in ``gestures.py`` stays a thin adapter.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication


def _pick_leaf(handler, local_pos: QPointF):
    return handler._leaf_at(local_pos.toPoint(), handler._leaf_rects())


def begin_slot_press(handler, local_pos: QPointF) -> None:
    picked = _pick_leaf(handler, local_pos)
    if picked is None:
        return
    leaf, _rect = picked
    handler._lmb_press_pos = local_pos
    handler._lmb_press_slot_id = leaf.slot_id


def maybe_start_slot_drag(handler, local_pos: QPointF) -> None:
    if handler._lmb_press_pos is None or handler._lmb_press_slot_id is None:
        return
    delta = local_pos - handler._lmb_press_pos
    if (delta.x() ** 2 + delta.y() ** 2) < (QApplication.startDragDistance() ** 2):
        return
    slot_id = handler._lmb_press_slot_id
    handler._lmb_press_pos = None
    handler._lmb_press_slot_id = None
    handler._start_internal_drag(slot_id)


def end_slot_press(handler) -> None:
    handler._lmb_press_pos = None
    handler._lmb_press_slot_id = None
