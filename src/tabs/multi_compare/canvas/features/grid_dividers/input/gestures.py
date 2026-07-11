"""Divider-drag gesture binding for multi_compare's N-way grid dividers.

Lowest priority number among multi_compare's left-button gestures, so it is
evaluated first and claims the press whenever the cursor is over a divider
gap — mirroring the previous inline ``mousePressEvent`` ordering, where the
divider hit-test ran before the leaf pick. ``drag_drop_overlay``'s slot-drag
binding (much higher priority number) only ever gets evaluated once this one
has refused the same click.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding

from tabs.multi_compare.canvas.features.grid_dividers.input.interaction import begin_divider_drag, end_divider_drag, update_divider_drag

DIVIDER_DRAG_OWNER = "multi_compare.divider_drag"


def _matches_divider_press(ctx) -> bool:
    from tabs.multi_compare.ui.canvas_widget import _dividers_locked

    handler = ctx.handler
    if _dividers_locked(handler.state):
        return False
    return handler._divider_at(ctx.local_pos) is not None


def _is_divider_dragging(handler) -> bool:
    return handler._divider_drag is not None


def _begin(handler, local_pos) -> None:
    begin_divider_drag(handler, local_pos)


def _update(handler, local_pos) -> None:
    update_divider_drag(handler, local_pos)


def _end(handler) -> None:
    end_divider_drag(handler)


def build_grid_dividers_gesture_bindings() -> tuple[CanvasFeatureGestureBinding, ...]:
    return (
        CanvasFeatureGestureBinding(
            gesture_id="grid_dividers.split_drag",
            button=Qt.MouseButton.LeftButton.value,
            matches=_matches_divider_press,
            is_active=_is_divider_dragging,
            begin=_begin,
            update=_update,
            end=_end,
            owner=DIVIDER_DRAG_OWNER,
            priority=100,
        ),
    )
