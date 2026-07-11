"""Registry for tab-owned session state slot reducers.

Core does not know what any given session state slot contains — it only
knows the generic slot name/value pairs on ``WorkspaceSession.state_slots``
(see ``core.session_blueprints``). A tab that wants ``RootReducer`` to run
its actions through a slot's value registers a reducer function here,
keyed by slot name; ``RootReducer.reduce`` calls whatever is registered
without importing the tab's domain types.
"""

from __future__ import annotations

from typing import Any, Callable

SlotReducer = Callable[[Any, Any], Any]

_SLOT_REDUCERS: dict[str, SlotReducer] = {}


def register_state_slot_reducer(slot_name: str, reducer: SlotReducer) -> None:
    _SLOT_REDUCERS[slot_name] = reducer


def get_state_slot_reducer(slot_name: str) -> SlotReducer | None:
    return _SLOT_REDUCERS.get(slot_name)


def iter_state_slot_reducers() -> tuple[tuple[str, SlotReducer], ...]:
    return tuple(_SLOT_REDUCERS.items())
