"""No-op dispatch regression net.

Invariant the whole dispatch path depends on: a reducer MUST return the
*identical* state object when an action changes nothing — ``Dispatcher``
drops the dispatch on ``is`` (``dispatcher.py:252-261``). Every reducer
that unconditionally ``replace()``s defeats that guard: value-equal but
identity-different ⇒ swap + history + emit. Live trace 2026-09-16 showed
1026/1349 ``dispatch.end`` with empty diff from exactly this shape.

Three layers (see plan ``noop-dispatch-guards-plan-2026-09-16``):
1. ``test_all_viewport_actions_covered`` — completeness meta-test: every
   viewport-affecting ``Action`` subclass must be either in ``NOOP_CASES``
   or in ``EXEMPT_WITH_REASON``. A newly added action fails the suite
   until its author registers a noop-case or documents an exemption.
2. ``test_noop_redispatch_returns_identical_state`` — parametrized over
   ``NOOP_CASES``: build the action from the state's *current* values
   (a genuine no-op), run the real slice reducer, assert ``result is
   state``. Fails on every unguarded branch, passes once guarded.
3. ``test_dispatcher_drops_identity_noop`` — locks the central ``is``
   contract with a stub reducer (same store ⇒ no history, no emit, no
   subscriber wakeup).
4. ``test_finish_cycle_on_converged_state_dispatches_nothing`` — the 8 ms
   timer path: finishing an already-finished cycle must not dispatch.
"""

from __future__ import annotations

import dataclasses
import importlib
from types import SimpleNamespace

import pytest

from core.state_management.action_base import Action
from core.state_management.dispatcher import Dispatcher
from core.state_management.reducers import (
    GeometryStateReducer,
    InteractionStateReducer,
    ViewStateReducer,
)
from core.store_viewport import GeometryState, InteractionState, ViewState
from domain.types import Point

from core.state_management.viewport_actions import (
    SetCanvasWidgetStateAction,
    SetChannelViewModeAction,
    SetDiffModeAction,
    SetIsDraggingSliderAction,
    SetMovementSpeedAction,
    SetShowingSingleImageModeAction,
    SetSplitPositionAction,
    SetSplitPositionVisualAction,
    ToggleOrientationAction,
)
from core.state_management.interaction_actions import (
    SetDraggingSplitLineAction,
    SetInteractionSessionIdAction,
    SetInteractiveModeAction,
    SetLastHorizontalMovementKeyAction,
    SetLastSpacingMovementKeyAction,
    SetLastVerticalMovementKeyAction,
    SetPressedKeysAction,
    SetResizeInProgressAction,
    SetSpaceBarPressedAction,
    SetUserInteractingAction,
)
from core.state_management.cache_actions import (
    ClearAllCachesAction,
    InvalidateGeometryCacheAction,
    InvalidateRenderCacheAction,
)
from core.state_management.geometry_actions import (
    SetFixedLabelDimensionsAction,
    SetImageDisplayRectAction,
    SetPixmapDimensionsAction,
)
from core.state_management.actions import (
    SetInteractiveInternalSplitVisualAction,
    SetInteractiveOffsetVisualAction,
    SetInteractiveSpacingVisualAction,
)
from domain.types import Rect
from tabs.image_compare.canvas.features.magnifier.input.actions import (
    SetDraggingCapturePointAction,
    SetDraggingSplitInMagnifierAction,
    SetMagnifierScreenCenterAction,
    SetMagnifierScreenSizeAction,
    SetMagnifierMovementInterpolationMethodAction,
    SetMagnifierSpacingRelativeVisualAction,
    ToggleMagnifierAction,
    SetOptimizeMagnifierMovementAction,
    SetHighlightedMagnifierElementAction,
    UpdateMagnifierCombinedStateAction,
)
from tabs.image_compare.canvas.features.magnifier.reducers.geometry import (
    reduce_magnifier_geometry_state,
)
from tabs.image_compare.canvas.features.magnifier.reducers.interaction import (
    reduce_magnifier_interaction_state,
)
from tabs.image_compare.canvas.features.magnifier.reducers.view import (
    reduce_magnifier_view_state,
)


_SENTINEL = object()

# Each entry: (action class, slice kind, make_state, make_action, reducer).
# make_action MUST build the action from make_state()'s current values, so
# the dispatch is a genuine no-op. The reducer must then return the
# *identical* object (``is``), which is what lets Dispatcher drop it.
NOOP_CASES: list[tuple] = [
    # --- core ViewState ---
    (SetSplitPositionAction, "view", ViewState,
     lambda: SetSplitPositionAction(position=0.5), ViewStateReducer.reduce),
    (SetSplitPositionVisualAction, "view", ViewState,
     lambda: SetSplitPositionVisualAction(position=0.5), ViewStateReducer.reduce),
    (ToggleOrientationAction, "view", ViewState,
     lambda: ToggleOrientationAction(is_horizontal=False), ViewStateReducer.reduce),
    (SetMovementSpeedAction, "view", ViewState,
     lambda: SetMovementSpeedAction(speed=2.0), ViewStateReducer.reduce),
    (SetDiffModeAction, "view", ViewState,
     lambda: SetDiffModeAction(mode="off"), ViewStateReducer.reduce),
    (SetChannelViewModeAction, "view", ViewState,
     lambda: SetChannelViewModeAction(mode="RGB"), ViewStateReducer.reduce),
    (SetShowingSingleImageModeAction, "view", ViewState,
     lambda: SetShowingSingleImageModeAction(mode=0), ViewStateReducer.reduce),
    (SetCanvasWidgetStateAction, "view",
     lambda: ViewState(canvas_widget_state={"x": _SENTINEL}),
     lambda: SetCanvasWidgetStateAction(feature="x", state=_SENTINEL),
     ViewStateReducer.reduce),
    (InvalidateRenderCacheAction, "view", ViewState,
     InvalidateRenderCacheAction, ViewStateReducer.reduce),
    (SetHighlightedMagnifierElementAction, "view", ViewState,
     lambda: SetHighlightedMagnifierElementAction(element=None),
     reduce_magnifier_view_state),
    (UpdateMagnifierCombinedStateAction, "view", ViewState,
     lambda: UpdateMagnifierCombinedStateAction(is_combined=False),
     reduce_magnifier_view_state),
    (SetMagnifierSpacingRelativeVisualAction, "view", ViewState,
     lambda: SetMagnifierSpacingRelativeVisualAction(spacing=0.0),
     reduce_magnifier_view_state),
    (SetMagnifierMovementInterpolationMethodAction, "view", ViewState,
     lambda: SetMagnifierMovementInterpolationMethodAction(method="linear"),
     reduce_magnifier_view_state),
    (ToggleMagnifierAction, "view", ViewState,
     lambda: ToggleMagnifierAction(enabled=False), reduce_magnifier_view_state),
    (SetOptimizeMagnifierMovementAction, "view", ViewState,
     lambda: SetOptimizeMagnifierMovementAction(enabled=True),
     reduce_magnifier_view_state),
    # --- core InteractionState ---
    (SetInteractiveModeAction, "interaction", InteractionState,
     lambda: SetInteractiveModeAction(enabled=False),
     InteractionStateReducer.reduce),
    (SetIsDraggingSliderAction, "interaction", InteractionState,
     lambda: SetIsDraggingSliderAction(is_dragging=False),
     InteractionStateReducer.reduce),
    (SetResizeInProgressAction, "interaction", InteractionState,
     lambda: SetResizeInProgressAction(enabled=False),
     InteractionStateReducer.reduce),
    (SetDraggingSplitLineAction, "interaction", InteractionState,
     lambda: SetDraggingSplitLineAction(enabled=False),
     InteractionStateReducer.reduce),
    (SetPressedKeysAction, "interaction", InteractionState,
     lambda: SetPressedKeysAction(keys=set()), InteractionStateReducer.reduce),
    (SetSpaceBarPressedAction, "interaction", InteractionState,
     lambda: SetSpaceBarPressedAction(enabled=False),
     InteractionStateReducer.reduce),
    (SetInteractionSessionIdAction, "interaction", InteractionState,
     lambda: SetInteractionSessionIdAction(session_id=0),
     InteractionStateReducer.reduce),
    (SetUserInteractingAction, "interaction", InteractionState,
     lambda: SetUserInteractingAction(enabled=False),
     InteractionStateReducer.reduce),
    (SetLastHorizontalMovementKeyAction, "interaction", InteractionState,
     lambda: SetLastHorizontalMovementKeyAction(key=None),
     InteractionStateReducer.reduce),
    (SetLastVerticalMovementKeyAction, "interaction", InteractionState,
     lambda: SetLastVerticalMovementKeyAction(key=None),
     InteractionStateReducer.reduce),
    (SetLastSpacingMovementKeyAction, "interaction", InteractionState,
     lambda: SetLastSpacingMovementKeyAction(key=None),
     InteractionStateReducer.reduce),
    # --- core GeometryState ---
    (SetPixmapDimensionsAction, "geometry", GeometryState,
     lambda: SetPixmapDimensionsAction(width=0, height=0),
     GeometryStateReducer.reduce),
    (SetImageDisplayRectAction, "geometry", GeometryState,
     lambda: SetImageDisplayRectAction(rect=Rect()), GeometryStateReducer.reduce),
    (SetFixedLabelDimensionsAction, "geometry", GeometryState,
     lambda: SetFixedLabelDimensionsAction(width=None, height=None),
     GeometryStateReducer.reduce),
    (InvalidateGeometryCacheAction, "geometry", GeometryState,
     InvalidateGeometryCacheAction, GeometryStateReducer.reduce),
    (ClearAllCachesAction, "geometry", GeometryState,
     ClearAllCachesAction, GeometryStateReducer.reduce),
    # --- magnifier geometry slice (live-trace storm: 508/session) ---
    (SetMagnifierScreenCenterAction, "geometry", GeometryState,
     lambda: SetMagnifierScreenCenterAction(center=Point()),
     reduce_magnifier_geometry_state),
    (SetMagnifierScreenSizeAction, "geometry", GeometryState,
     lambda: SetMagnifierScreenSizeAction(size=0),
     reduce_magnifier_geometry_state),
    # --- magnifier interaction slice (live-trace storm: 270/session) ---
    (SetDraggingCapturePointAction, "interaction", InteractionState,
     lambda: SetDraggingCapturePointAction(enabled=False),
     reduce_magnifier_interaction_state),
    (SetDraggingSplitInMagnifierAction, "interaction", InteractionState,
     lambda: SetDraggingSplitInMagnifierAction(enabled=False),
     reduce_magnifier_interaction_state),
    (SetInteractiveOffsetVisualAction, "interaction", InteractionState,
     lambda: SetInteractiveOffsetVisualAction(offset=Point(0.0, 0.0)),
     reduce_magnifier_interaction_state),
    (SetInteractiveSpacingVisualAction, "interaction", InteractionState,
     lambda: SetInteractiveSpacingVisualAction(spacing=0.1),
     reduce_magnifier_interaction_state),
    (SetInteractiveInternalSplitVisualAction, "interaction", InteractionState,
     lambda: SetInteractiveInternalSplitVisualAction(split=0.5),
     reduce_magnifier_interaction_state),
]

# Action classes deliberately NOT covered by NOOP_CASES, with reasons.
# A class added to the scanned modules that lands in neither table FAILS
# the completeness test — that is the "catch it anywhere" mechanism.
EXEMPT_WITH_REASON: dict = {
    # Model-based magnifier branches: need a MagnifierWidgetState fixture
    # with a live model; a defaults-built action always changes state.
    # (Keys carry the "magnifier:" module prefix used by the scan.)
    "magnifier:SetMagnifierSizeRelativeAction": "model-based, needs widget-state fixture",
    "magnifier:SetCaptureSizeRelativeAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierVisibilityAction": "model-based, needs widget-state fixture",
    "magnifier:ToggleMagnifierOrientationAction": "model-based, needs widget-state fixture",
    "magnifier:ToggleFreezeMagnifierAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierPositionAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierInternalSplitAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierOffsetRelativeAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierSpacingRelativeAction": "model-based, needs widget-state fixture",
    "magnifier:SetMagnifierOffsetRelativeVisualAction": "model-based, needs widget-state fixture",
    "magnifier:SetActiveMagnifierIdAction": "needs fixture with known active_id",
    "magnifier:SetMagnifierLaserEnabledAction": "model-based, needs widget-state fixture",
}

_SCANNED_MODULES = [
    "core.state_management.viewport_actions",
    "core.state_management.interaction_actions",
    "core.state_management.geometry_actions",
    "tabs.image_compare.canvas.features.magnifier.input.actions",
]


def _iter_action_classes():
    for mod_name in _SCANNED_MODULES:
        module = importlib.import_module(mod_name)
        prefix = "magnifier:" if "magnifier" in mod_name else ""
        for name, obj in vars(module).items():
            if (
                isinstance(obj, type)
                and issubclass(obj, Action)
                and obj is not Action
            ):
                yield prefix + name, obj


def test_all_viewport_actions_covered():
    # Core visual actions are registered under plain names; the magnifier
    # module's legacy dupes carry the "magnifier:" prefix (exempt, audit
    # pending).
    covered = {cls.__name__ for cls, *_ in NOOP_CASES}
    problems = []
    for key, cls in _iter_action_classes():
        if key in EXEMPT_WITH_REASON:
            continue
        plain = key.split(":")[-1]
        if plain in covered or key in covered:
            continue
        problems.append(
            f"{key}: add a NOOP_CASES entry or document exemption in "
            f"EXEMPT_WITH_REASON ({__file__})"
        )
    assert not problems, "uncovered viewport actions:\n" + "\n".join(problems)


def test_noop_cases_reference_real_actions():
    for cls, *_ in NOOP_CASES:
        assert isinstance(cls, type) and issubclass(cls, Action), cls


@pytest.mark.parametrize("case_id", range(len(NOOP_CASES)))
def test_noop_redispatch_returns_identical_state(case_id):
    cls, _slice, make_state, make_action, reducer = NOOP_CASES[case_id]
    state = make_state()
    action = make_action() if callable(make_action) else make_action()
    result = reducer(state, action)
    assert result is state, (
        f"{cls.__name__}: reducer allocated a new state object for an "
        f"action that changes nothing — Dispatcher cannot drop it "
        f"(see dispatcher.py:252-261)"
    )


class _ProbeStore:
    """Minimal harness for the central ``is``-guard contract."""

    def __init__(self):
        self.viewport = object()
        self.settings = object()
        self.emits: list = []
        self.slots: dict = {}

    def get_session_state_slot(self, slot, **kwargs):
        return self.slots.get(slot)

    def set_session_state_slot(self, slot, value, **kwargs):
        self.slots[slot] = value

    def get_workspace_session(self, session_id):
        return None

    def get_active_workspace_session(self):
        return None

    def emit_state_change(self, scope):
        self.emits.append(scope)


def test_dispatcher_drops_identity_noop():
    from core.state_management.actions import SetSplitPositionAction as AnyAction

    store = _ProbeStore()
    dispatcher = Dispatcher(store)
    calls = []
    dispatcher._subscribers.append(calls.append)
    # Stub reducer: the whole-store no-change path (RootReducer returns the
    # same store object when nothing changed, reducers.py:419-424).
    dispatcher._reducer = SimpleNamespace(
        reduce=lambda _store, _action: _store
    )
    dispatcher.dispatch(AnyAction(position=0.5))
    assert store.emits == [], "identity no-op must not emit"
    assert calls == [], "identity no-op must not wake subscribers"
    assert dispatcher._action_history == [], "identity no-op must not pollute history"


def test_finish_cycle_on_converged_state_dispatches_nothing(monkeypatch):
    import tabs.image_compare.canvas.features.magnifier.input.keyboard_movement as km

    monkeypatch.setattr(km, "clear_presenter_render_snapshots", lambda presenter: None)
    monkeypatch.setattr(km, "emit_update_request", lambda presenter: None)

    dispatched: list = []

    store = SimpleNamespace(
        viewport=SimpleNamespace(
            view_state=SimpleNamespace(split_position=0.5),
            interaction_state=SimpleNamespace(
                is_interactive_mode=False,
                interactive_offset_relative_visual=Point(0.0, 0.0),
                interactive_spacing_relative_visual=0.0,
                interactive_internal_split_visual=0.5,
            ),
        ),
        emit_viewport_change=lambda scope: None,
        invalidate_render_cache=lambda: None,
    )
    store._dispatcher = SimpleNamespace(
        dispatch=lambda action, scope="viewport": dispatched.append(action)
    )

    controller = km.InteractiveMovementController(store, lambda: None)
    controller._finish_interactive_cycle(handler=None)

    assert dispatched == [], (
        f"finishing an already-converged cycle dispatched "
        f"{[type(a).__name__ for a in dispatched]} — the 8 ms pump's "
        f"steady-idle guarantee is broken"
    )
