"""Generic per-session UI-state slot (namespace -> plain dict).

A tab that keeps small "chrome" state per session (toolbar switches, view
modes) stores it in a session slot named after its namespace. The slot value
is a plain ``dict[str, scalar | dict | list]``; writes go through the generic
``SessionStateSet`` action, so the tab never needs a bespoke action/reducer
pair. ``tabs.use_cases.session_state.SessionState`` is the only intended
caller.

A tab whose slot already has its own typed model (e.g. a frozen dataclass
state) registers a *typed* slot instead: ``SessionStateSet`` writes for that
slot are routed through the tab's pure ``merge(state, values) -> state``
(via ``reduce_typed_session_slot`` from the tab's slot reducer), and the
facade reads it back through ``extract(state) -> values``.
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


@dataclass(frozen=True)
class TypedSlotCodec:
    merge: Callable[[Any, dict], Any]
    extract: Callable[[Any], dict]


_TYPED_SLOTS: dict[str, TypedSlotCodec] = {}


def register_typed_session_slot(
    slot_name: str,
    merge: Callable[[Any, dict], Any],
    extract: Callable[[Any], dict],
) -> None:
    """Declare ``slot_name`` as a typed slot with a pure merge/extract pair.

    Idempotent: a repeated bind (new tab instance) replaces the codec with an
    equivalent one. The slot's own reducer must call
    ``reduce_typed_session_slot`` for ``SessionStateSet`` to take effect.
    """
    _TYPED_SLOTS[str(slot_name)] = TypedSlotCodec(merge=merge, extract=extract)


def typed_session_slot(slot_name: str) -> TypedSlotCodec | None:
    return _TYPED_SLOTS.get(str(slot_name))


def reduce_typed_session_slot(slot_name: str, state: Any, action: Any) -> Any:
    """Apply a ``SessionStateSet`` for the typed ``slot_name`` via its merge.

    Pure. ``state`` must already be the slot's typed value (never ``None``).
    Actions for other namespaces, or slots without a codec, return ``state``
    unchanged; so does a merge that produces an equal value (no spurious emit).
    """
    codec = _TYPED_SLOTS.get(str(slot_name))
    if codec is None or not isinstance(action, SessionStateSet) or action.namespace != slot_name:
        return state
    merged = codec.merge(state, dict(action.values))
    return state if merged == state else merged


__all__ = [
    "SessionStateSet",
    "reduce_typed_session_slot",
    "register_session_state_slot",
    "register_typed_session_slot",
    "typed_session_slot",
]
