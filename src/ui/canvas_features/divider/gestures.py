"""Divider gesture bindings.

Splitter drag is the fallback left-button gesture (lowest priority); it wins
whenever no overlay-style feature claims the click first.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from events.canvas_input.owner_ids import SPLIT_DRAG_OWNER
from ui.canvas_infra.scene.widget_contract import CanvasFeatureGestureBinding
from ui.canvas_infra.scene.widget_registry import get_canvas_feature_command_by_alias

from .interaction import apply_split_drag

def _matches_split_drag(ctx) -> bool:
    try:
        if ctx.store.viewport.interaction_state.space_bar_pressed:
            return False
    except AttributeError:
        pass
    return True

def _is_split_dragging(store) -> bool:
    return bool(store.viewport.interaction_state.is_dragging_split_line)

def _begin_split_drag(handler, local_pos) -> None:
    cmd = get_canvas_feature_command_by_alias("splitter.begin_drag")
    if cmd is not None:
        cmd(handler)
    apply_split_drag(handler, local_pos)

def _update_split_drag(handler, local_pos) -> None:
    apply_split_drag(handler, local_pos)

def _end_split_drag(handler) -> None:
    cmd = get_canvas_feature_command_by_alias("splitter.end_drag")
    if cmd is not None:
        cmd(handler)

def build_divider_gesture_bindings() -> tuple[CanvasFeatureGestureBinding, ...]:
    return (
        CanvasFeatureGestureBinding(
            gesture_id="divider.split_drag",
            button=Qt.MouseButton.LeftButton.value,
            matches=_matches_split_drag,
            is_active=_is_split_dragging,
            begin=_begin_split_drag,
            update=_update_split_drag,
            end=_end_split_drag,
            owner=SPLIT_DRAG_OWNER,
            priority=1000,
        ),
    )
