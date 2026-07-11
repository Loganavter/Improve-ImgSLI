"""Drag-drop-of-slots gesture binding.

Fallback left-button gesture: uses a high priority number (evaluated last),
so it only wins the press once ``grid_dividers`` has already refused the same
click (a divider hit takes precedence — see ``grid_dividers/gestures.py``'s
lower priority number, same ordering the inline code used before this
extraction). Matches whenever the press lands on a leaf cell; the QDrag only
actually fires once the cursor crosses Qt's drag-start distance threshold on
a subsequent move (mirrors the previous inline ``mouseMoveEvent`` check),
handled in ``update``.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding

from tabs.multi_compare.canvas.features.drag_drop_overlay.input.interaction import begin_slot_press, end_slot_press, maybe_start_slot_drag

SLOT_DRAG_OWNER = "multi_compare.slot_drag"


def _matches_slot_press(ctx) -> bool:
    handler = ctx.handler
    return handler._leaf_at(ctx.local_pos.toPoint(), handler._leaf_rects()) is not None


def _is_slot_press_active(handler) -> bool:
    return handler._lmb_press_slot_id is not None


def _begin(handler, local_pos) -> None:
    begin_slot_press(handler, local_pos)


def _update(handler, local_pos) -> None:
    maybe_start_slot_drag(handler, local_pos)


def _end(handler) -> None:
    end_slot_press(handler)


def build_drag_drop_gesture_bindings() -> tuple[CanvasFeatureGestureBinding, ...]:
    return (
        CanvasFeatureGestureBinding(
            gesture_id="drag_drop_overlay.slot_drag",
            button=Qt.MouseButton.LeftButton.value,
            matches=_matches_slot_press,
            is_active=_is_slot_press_active,
            begin=_begin,
            update=_update,
            end=_end,
            owner=SLOT_DRAG_OWNER,
            priority=1000,
        ),
    )
