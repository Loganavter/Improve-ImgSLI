"""Generic per-session UI-state slot (namespace -> plain dict).

A tab that keeps small "chrome" state per session (toolbar switches, view
modes) stores it in a session slot named after its namespace. The slot value
is a plain ``dict[str, scalar]``; writes go through the generic
``SessionStateSet`` action, so the tab never needs a bespoke action/reducer
pair. ``tabs.use_cases.session_state.SessionState`` is the only intended
caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from core.state_management.action_base import Action, ActionType
from core.state_management.slot_reducers import register_state_slot_reducer

MergeFn = Callable[[dict, dict], dict]


@dataclass
class SessionStateSet(Action):
    """Merge ``values`` into the ``namespace`` session slot (plain dict)."""

    namespace: str = ""
    values: dict = field(default_factory=dict)
    type: str = field(default=ActionType.SESSION_STATE_SET.value, kw_only=True)

    def __post_init__(self):
        self.namespace = str(self.namespace or "")
        self.values = dict(self.values or {})

    def get_payload(self):
        return {"namespace": self.namespace, "fields": sorted(self.values)}


def _default_merge(current: dict, values: dict) -> dict:
    current.update(values)
    return current


_REGISTERED: dict[str, Callable[[Any, Any], Any]] = {}


def register_session_state_slot(namespace: str, reduce_fn: MergeFn | None = None) -> None:
    """Make ``namespace`` a session slot reduced by ``SessionStateSet``.

    ``reduce_fn(current_dict, values_dict) -> dict`` decides how a write
    combines with the stored dict (default: shallow merge). Idempotent per
    namespace: repeated binds (new tab instances, tests) keep the first reducer.
    """
    namespace = str(namespace)
    if namespace in _REGISTERED:
        return
    merge = reduce_fn or _default_merge

    def _reduce(state: Any, action: Any) -> Any:
        if not isinstance(action, SessionStateSet) or action.namespace != namespace:
            return state
        current = dict(state) if isinstance(state, dict) else {}
        merged = merge(dict(current), dict(action.values))
        if merged == current:
            return state
        return merged

    _REGISTERED[namespace] = _reduce
    register_state_slot_reducer(namespace, _reduce)


__all__ = ["SessionStateSet", "register_session_state_slot"]
