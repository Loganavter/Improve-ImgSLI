from __future__ import annotations

from dataclasses import replace

from core.state_management.action_base import Action
from core.state_management.actions import (
    SetInteractiveInternalSplitVisualAction,
    SetInteractiveOffsetVisualAction,
    SetInteractiveSpacingVisualAction,
)
from core.store_viewport import ViewState
from ..actions import (
    SetActiveMagnifierIdAction,
    SetCaptureSizeRelativeAction,
    SetHighlightedMagnifierElementAction,
    SetMagnifierInternalSplitAction,
    SetMagnifierLaserEnabledAction,
    SetMagnifierOffsetRelativeAction,
    SetMagnifierOffsetRelativeVisualAction,
    SetMagnifierPositionAction,
    SetMagnifierSizeRelativeAction,
    SetMagnifierSpacingRelativeAction,
    SetMagnifierSpacingRelativeVisualAction,
    SetMagnifierVisibilityAction,
    SetOptimizeMagnifierMovementAction,
    ToggleFreezeMagnifierAction,
    ToggleMagnifierAction,
    ToggleMagnifierOrientationAction,
    UpdateMagnifierCombinedStateAction,
)

from ..models import MagnifierModel
from ..state import clone_magnifier_widget_state, get_magnifier_widget_state

def _active_magnifier_id(view_state: ViewState) -> str:
    return get_magnifier_widget_state(view_state).active_id or "default"

def _ensure_active_magnifier_model(view_state: ViewState):
    state = clone_magnifier_widget_state(view_state)
    magnifiers = state.models
    active_id = _active_magnifier_id(view_state)
    model = magnifiers.get(active_id)
    if model is None:
        model = MagnifierModel(
            id=active_id,
            divider_color=state.default_divider_color,
            border_color=state.default_border_color,
            divider_visible=state.default_divider_visible,
            divider_thickness=state.default_divider_thickness,
        )
    magnifiers[active_id] = model
    state.active_id = active_id
    return state, active_id, magnifiers, model

def _replace_widget_state(view_state: ViewState, state) -> ViewState:
    canvas_widget_state = dict(view_state.canvas_widget_state)
    canvas_widget_state["magnifier"] = state
    return replace(view_state, canvas_widget_state=canvas_widget_state)

def reduce_magnifier_view_state(view_state: ViewState, action: Action) -> ViewState:
    if isinstance(action, SetMagnifierSizeRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.size_relative = action.size
        magnifiers[active_id] = model
        state.default_size_relative = action.size
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetCaptureSizeRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.capture_size_relative = action.size
        magnifiers[active_id] = model
        state.default_capture_size_relative = action.size
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleMagnifierAction):
        state = clone_magnifier_widget_state(view_state)
        state.enabled = bool(action.enabled)
        if action.enabled and not state.active_id:
            state.active_id = "default"
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierVisibilityAction):
        payload = action.get_payload()
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        if payload.get("left") is not None:
            model.visible_left = payload["left"]
        if payload.get("center") is not None:
            model.visible_center = payload["center"]
        if payload.get("right") is not None:
            model.visible_right = payload["right"]
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleMagnifierOrientationAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.is_horizontal = action.is_horizontal
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, ToggleFreezeMagnifierAction):
        payload = action.get_payload()
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.freeze = payload["freeze"]
        model.frozen_position = payload.get("frozen_position")
        if payload.get("new_offset") is not None:
            model.offset_relative = payload["new_offset"]
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierPositionAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.position = action.position
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierInternalSplitAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.internal_split = max(0.0, min(1.0, action.split))
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, UpdateMagnifierCombinedStateAction):
        return view_state
    if isinstance(action, SetActiveMagnifierIdAction):
        state = clone_magnifier_widget_state(view_state)
        state.active_id = action.magnifier_id
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierOffsetRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.offset_relative = action.offset
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierSpacingRelativeAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.spacing_relative = action.spacing
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierOffsetRelativeVisualAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.offset_relative = action.offset
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetMagnifierSpacingRelativeVisualAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.spacing_relative = action.spacing
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    if isinstance(action, SetOptimizeMagnifierMovementAction):
        state = clone_magnifier_widget_state(view_state)
        canvas_widget_state = dict(view_state.canvas_widget_state)
        canvas_widget_state["magnifier"] = state
        return replace(
            view_state,
            optimize_interactive_movement=action.enabled,
            canvas_widget_state=canvas_widget_state,
        )
    if isinstance(action, SetHighlightedMagnifierElementAction):
        return replace(view_state, highlighted_overlay_element=action.element)
    if isinstance(action, SetMagnifierLaserEnabledAction):
        state, active_id, magnifiers, model = _ensure_active_magnifier_model(view_state)
        model.show_laser = bool(action.enabled)
        magnifiers[active_id] = model
        return _replace_widget_state(view_state, state)
    return view_state
