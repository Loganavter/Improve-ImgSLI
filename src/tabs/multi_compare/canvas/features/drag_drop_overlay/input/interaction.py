"""Slot drag-drop interaction helpers.

Drag-distance-threshold math and QDrag kickoff live here, operating purely
on the canvas widget ``handler`` — mirrors ``image_compare``'s
``divider/interaction.py`` pattern (a free function taking ``handler``, not
a method), so the gesture binding in ``gestures.py`` stays a thin adapter.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from tabs.multi_compare.scene import actions


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
    try:
        from tabs.multi_compare.debug import mc_dnd_debug

        mc_dnd_debug("internal drag: kickoff source_slot=%s", slot_id)
    except Exception:
        pass
    handler._start_internal_drag(slot_id)


def end_slot_press(handler) -> None:
    """Release the pending press; a click that never crossed the drag
    threshold (``_lmb_press_slot_id`` still set) toggles focus on that slot,
    filling the split view with just that image (see ``composition_builder``'s
    ``focused_slot_id`` handling)."""
    slot_id = handler._lmb_press_slot_id
    handler._lmb_press_pos = None
    handler._lmb_press_slot_id = None
    if slot_id is None:
        return
    new_focus = None if handler.state.is_focused else slot_id
    handler._do_dispatch(actions.set_focus(new_focus))