"""Reducer registration for multi_compare — imported once at plugin load.

Registers ``multi_compare.state`` as a core session-state slot reducer (the
same mechanism image_compare uses for ``document``), so MC actions flow
through the core ``Dispatcher`` and the session slot is the single source of
truth (see state-unification-plan.md, private
improve-imgsli-internal-docs repo).
"""

from __future__ import annotations

from core.state_management.slot_reducers import register_state_slot_reducer
from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene.store import (
    MultiCompareAction,
    reduce as mc_reduce,
)

_SLOT_NAME = "multi_compare.state"


def _reduce_multi_compare_state(state, action):
    """Core slot-reducer wrapper: only handle MC actions.

    ``RootReducer.reduce`` runs every registered slot reducer against every
    dispatched action; IC (and other) actions must pass through unchanged so
    the MC reducer's own "unhandled action" warning never fires for them.
    """
    if not isinstance(action, MultiCompareAction):
        return state
    if state is None:
        state = MultiCompareState()
    return mc_reduce(state, action)


def register_multi_compare_reducers() -> None:
    register_state_slot_reducer(_SLOT_NAME, _reduce_multi_compare_state)
