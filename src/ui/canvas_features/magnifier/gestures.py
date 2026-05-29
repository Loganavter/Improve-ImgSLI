"""Magnifier gesture bindings.

Declares which mouse gestures the magnifier feature claims. Shared event code
(``events/image_label/mouse.py``) walks these bindings via the gesture
resolver — no feature-specific branching lives in shared code.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt

from events.canvas_input.owner_ids import (
    CAPTURE_DRAG_OWNER,
    INTERNAL_SPLIT_DRAG_OWNER,
    KEYBOARD_MOVE_OWNER,
)
from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

from .interaction import (
    apply_capture_drag,
    is_point_in_overlay,
    pick_overlay_at,
    update_internal_split,
)


def _overlay_enabled(store) -> bool:
    try:
        return bool(store.viewport.view_state.overlay_enabled)
    except AttributeError:
        return False


def _space_pressed(store) -> bool:
    try:
        return bool(store.viewport.interaction_state.space_bar_pressed)
    except AttributeError:
        return False


def _shift_pressed(ctx) -> bool:
    return bool(ctx.modifiers & int(Qt.KeyboardModifier.ShiftModifier))


def _query(name):
    return get_canvas_feature_command_by_alias(name)


def _has_visible_overlay(store) -> bool:
    q = _query("overlay.active_state")
    if q is None:
        return False
    state = q(store) or {}
    return bool(state.get("visible_left", False) or state.get("visible_right", False))


def _has_both_sides_visible(store) -> bool:
    q = _query("overlay.active_state")
    if q is None:
        return False
    state = q(store) or {}
    return bool(state.get("visible_left", False) and state.get("visible_right", False))


def _active_combined(store) -> bool:
    q = _query("overlay.active_combined")
    return bool(q(store)) if q is not None else False


def _point_in_overlay(ctx) -> bool:
    return is_point_in_overlay(ctx.handler, ctx.local_pos)


# ---------- predicates ----------


def _matches_capture_drag(ctx) -> bool:
    if _space_pressed(ctx.store):
        return False
    return _overlay_enabled(ctx.store) and _has_visible_overlay(ctx.store)


def _matches_internal_split_drag(ctx) -> bool:
    if _space_pressed(ctx.store):
        return False
    if not _overlay_enabled(ctx.store):
        return False
    if not _active_combined(ctx.store):
        return False
    return _point_in_overlay(ctx)


def _matches_side_preview(ctx) -> bool:
    if not _space_pressed(ctx.store):
        return False
    if not _shift_pressed(ctx):
        return False
    if not _overlay_enabled(ctx.store):
        return False
    if not _active_combined(ctx.store):
        return False
    if not _has_both_sides_visible(ctx.store):
        return False
    return _point_in_overlay(ctx)


def _matches_keyboard_move_absorb(ctx) -> bool:
    if not _overlay_enabled(ctx.store):
        return False
    return bool(ctx.handler.input_session.has_owner(KEYBOARD_MOVE_OWNER))


# ---------- is_active ----------


def _is_capture_dragging(store) -> bool:
    return bool(store.viewport.interaction_state.is_dragging_overlay_handle)


def _is_internal_split_dragging(store) -> bool:
    return bool(store.viewport.interaction_state.is_dragging_overlay_split)


def _never_active(store) -> bool:
    return False


# ---------- begin / update / end ----------


def _begin_capture_drag(handler, local_pos) -> None:
    pick_overlay_at(handler, local_pos)
    cmd = _query("overlay.begin_capture_drag")
    if cmd is not None:
        cmd(handler)
    apply_capture_drag(handler, local_pos)


def _update_capture_drag(handler, local_pos) -> None:
    apply_capture_drag(handler, local_pos)


def _end_capture_drag(handler) -> None:
    cmd = _query("overlay.end_capture_drag")
    if cmd is not None:
        cmd(handler)
    if hasattr(handler.store, "emit_viewport_change"):
        handler.store.emit_viewport_change("interaction")


def _begin_internal_split_drag(handler, local_pos) -> None:
    cmd = _query("overlay.begin_internal_split_drag")
    if cmd is not None:
        cmd(handler)
    update_internal_split(handler, local_pos)


def _update_internal_split_drag(handler, local_pos) -> None:
    update_internal_split(handler, local_pos)


def _end_internal_split_drag(handler) -> None:
    cmd = _query("overlay.end_internal_split_drag")
    if cmd is not None:
        cmd(handler)


def _begin_side_preview_left(handler, local_pos) -> None:
    handler.preview.start_side_preview("left")


def _begin_side_preview_right(handler, local_pos) -> None:
    handler.preview.start_side_preview("right")


def build_magnifier_gesture_bindings() -> tuple[CanvasFeatureGestureBinding, ...]:
    LB = Qt.MouseButton.LeftButton.value
    RB = Qt.MouseButton.RightButton.value
    return (
        # Highest-priority: side preview (space+shift on combined overlay)
        CanvasFeatureGestureBinding(
            gesture_id="magnifier.side_preview_left",
            button=LB,
            matches=_matches_side_preview,
            is_active=_never_active,
            begin=_begin_side_preview_left,
            priority=1,
        ),
        CanvasFeatureGestureBinding(
            gesture_id="magnifier.side_preview_right",
            button=RB,
            matches=_matches_side_preview,
            is_active=_never_active,
            begin=_begin_side_preview_right,
            priority=1,
        ),
        # Absorb RB while keyboard-arrow movement is in progress
        CanvasFeatureGestureBinding(
            gesture_id="magnifier.keyboard_move_absorb",
            button=RB,
            matches=_matches_keyboard_move_absorb,
            is_active=_never_active,
            priority=5,
        ),
        # Standard magnifier drags
        CanvasFeatureGestureBinding(
            gesture_id="magnifier.capture_drag",
            button=LB,
            matches=_matches_capture_drag,
            is_active=_is_capture_dragging,
            begin=_begin_capture_drag,
            update=_update_capture_drag,
            end=_end_capture_drag,
            owner=CAPTURE_DRAG_OWNER,
            priority=10,
        ),
        CanvasFeatureGestureBinding(
            gesture_id="magnifier.internal_split_drag",
            button=RB,
            matches=_matches_internal_split_drag,
            is_active=_is_internal_split_dragging,
            begin=_begin_internal_split_drag,
            update=_update_internal_split_drag,
            end=_end_internal_split_drag,
            owner=INTERNAL_SPLIT_DRAG_OWNER,
            priority=10,
        ),
    )
