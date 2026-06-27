from __future__ import annotations

from domain.types import Point

from ..actions import (
    SetDraggingCapturePointAction,
    SetDraggingSplitInMagnifierAction,
    SetMagnifierInternalSplitAction,
    SetMagnifierPositionAction,
)
from .common import dispatch_viewport_action, emit_interaction_update


def begin_capture_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingCapturePointAction(True)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_overlay_handle = True
    emit_interaction_update(actions)


def end_capture_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingCapturePointAction(False)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_overlay_handle = False
    emit_interaction_update(actions)


def update_capture_drag(actions, position: Point) -> None:
    clamped = Point(
        float(position.x),
        float(position.y),
    )
    if dispatch_viewport_action(actions, SetMagnifierPositionAction(clamped)):
        emit_interaction_update(actions)
        return
    store = getattr(actions, "store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    from ..store import active_magnifier_id, update_magnifier_model

    update_magnifier_model(
        viewport.view_state,
        viewport.render_config,
        active_magnifier_id(viewport.view_state) or "default",
        position=clamped,
    )
    emit_interaction_update(actions)


def begin_internal_split_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingSplitInMagnifierAction(True)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_overlay_split = True
    emit_interaction_update(actions)


def end_internal_split_drag(actions) -> None:
    if dispatch_viewport_action(actions, SetDraggingSplitInMagnifierAction(False)):
        emit_interaction_update(actions)
        return
    viewport = getattr(getattr(actions, "store", None), "viewport", None)
    if viewport is None:
        return
    viewport.interaction_state.is_dragging_overlay_split = False
    emit_interaction_update(actions)


def update_internal_split_drag(actions, split: float) -> None:
    clamped = max(0.0, min(1.0, float(split)))
    if dispatch_viewport_action(actions, SetMagnifierInternalSplitAction(clamped)):
        emit_interaction_update(actions)
        return
    store = getattr(actions, "store", None)
    viewport = getattr(store, "viewport", None) if store is not None else None
    if viewport is None:
        return
    from ..store import active_magnifier_id, update_magnifier_model

    update_magnifier_model(
        viewport.view_state,
        viewport.render_config,
        active_magnifier_id(viewport.view_state) or "default",
        internal_split=clamped,
    )
    emit_interaction_update(actions)
