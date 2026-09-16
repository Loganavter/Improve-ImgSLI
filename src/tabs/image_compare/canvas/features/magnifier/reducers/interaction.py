from __future__ import annotations

from dataclasses import replace

from core.state_management.action_base import Action
from core.state_management.actions import (
    SetInteractiveInternalSplitVisualAction,
    SetInteractiveOffsetVisualAction,
    SetInteractiveSpacingVisualAction,
)

from tabs.image_compare.canvas.features.magnifier.input.actions import (
    SetDraggingCapturePointAction,
    SetDraggingSplitInMagnifierAction,
)


def reduce_magnifier_interaction_state(interaction_state, action: Action):
    if isinstance(action, SetDraggingCapturePointAction):
        if interaction_state.is_dragging_overlay_handle == action.enabled:
            return interaction_state
        return replace(interaction_state, is_dragging_overlay_handle=action.enabled)
    if isinstance(action, SetDraggingSplitInMagnifierAction):
        if interaction_state.is_dragging_overlay_split == action.enabled:
            return interaction_state
        return replace(interaction_state, is_dragging_overlay_split=action.enabled)
    if isinstance(action, SetInteractiveOffsetVisualAction):
        if interaction_state.interactive_offset_relative_visual == action.offset:
            return interaction_state
        return replace(
            interaction_state,
            interactive_offset_relative_visual=action.offset,
        )
    if isinstance(action, SetInteractiveSpacingVisualAction):
        if interaction_state.interactive_spacing_relative_visual == action.spacing:
            return interaction_state
        return replace(
            interaction_state,
            interactive_spacing_relative_visual=action.spacing,
        )
    if isinstance(action, SetInteractiveInternalSplitVisualAction):
        if interaction_state.interactive_internal_split_visual == action.split:
            return interaction_state
        return replace(
            interaction_state,
            interactive_internal_split_visual=action.split,
        )
    return interaction_state
