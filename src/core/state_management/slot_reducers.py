"""Registry for tab-owned session state slot reducers.

Core does not know what any given session state slot contains — it only
knows the generic slot name/value pairs on ``WorkspaceSession.state_slots``
(see ``session_blueprints``). A tab that wants ``RootReducer`` to run
its actions through a slot's value registers a reducer function here,
keyed by slot name; ``RootReducer.reduce`` calls whatever is registered
without importing the tab's domain types.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("ImproveImgSLI")

SlotReducer = Callable[[Any, Any], Any]

_SLOT_REDUCERS: dict[str, SlotReducer] = {}


def register_state_slot_reducer(slot_name: str, reducer: SlotReducer) -> None:
    """Register ``reducer`` for ``slot_name`` (idempotent for same reducer).

    A duplicate registration with a *different* reducer is logged loudly
    (warning) before replacing — two tabs claiming the same slot would
    otherwise silently steal each other's reduce path with zero log lines.
    Re-registering the identical reducer (e.g. repeated ensure-calls) is
    expected and stays at debug level.
    """
    existing = _SLOT_REDUCERS.get(slot_name)
    if existing is not None and existing is not reducer:
        logger.warning(
            "register_state_slot_reducer: duplicate registration for slot "
            "%r — replacing %r with %r",
            slot_name,
            existing,
            reducer,
        )
    _SLOT_REDUCERS[slot_name] = reducer


def unregister_state_slot_reducer(slot_name: str) -> bool:
    """Remove the reducer for ``slot_name``. Returns True when one existed."""
    if slot_name not in _SLOT_REDUCERS:
        logger.debug(
            "unregister_state_slot_reducer: no reducer registered for slot %r",
            slot_name,
        )
        return False
    del _SLOT_REDUCERS[slot_name]
    return True



def iter_state_slot_reducers() -> tuple[tuple[str, SlotReducer], ...]:
    return tuple(_SLOT_REDUCERS.items())