from __future__ import annotations

from dataclasses import replace

from core.state_management.action_base import Action
from core.state_management.actions import (
    SetInteractiveInternalSplitVisualAction,
    SetInteractiveOffsetVisualAction,
    SetInteractiveSpacingVisualAction,
)
from ..actions import (
    SetDraggingCapturePointAction,
    SetDraggingSplitInMagnifierAction,
)

def reduce_magnifier_interaction_state(interaction_state, action: Action):
    if isinstance(action, SetDraggingCapturePointAction):
        return replace(interaction_state, is_dragging_overlay_handle=action.enabled)
    if isinstance(action, SetDraggingSplitInMagnifierAction):
        return replace(interaction_state, is_dragging_overlay_split=action.enabled)
    if isinstance(action, SetInteractiveOffsetVisualAction):
        return replace(
            interaction_state,
            interactive_offset_relative_visual=action.offset,
        )
    if isinstance(action, SetInteractiveSpacingVisualAction):
        return replace(
            interaction_state,
            interactive_spacing_relative_visual=action.spacing,
        )
    if isinstance(action, SetInteractiveInternalSplitVisualAction):
        return replace(
            interaction_state,
            interactive_internal_split_visual=action.split,
        )
    return interaction_state
