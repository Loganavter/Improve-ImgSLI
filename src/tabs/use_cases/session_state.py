"""Declarative per-session chrome state for a tab (``SessionState`` facade).

One object owns a tab's small per-session UI state (toolbar switches and the
like) across its three homes:

1. the session slot ``namespace`` (plain dict, reduced by ``SessionStateSet``);
2. the last-used QSettings value ``f"{namespace}/chrome"`` (new sessions seed
   from it, and it survives app restarts);
3. project I/O via ``serialize``/``deserialize`` (plain ``{name: value}``).

Lifecycle contract: ``serialize``/``deserialize`` run only on project save/load
and duplicate. A session SWITCH runs ``on_activated`` /
``on_active_session_changed`` only, so those delegates must call
``apply_from_slot`` (which reads the LIVE slot, never the project snapshot).

The facade wires no hooks itself; the tab's thin delegates call its methods.
The in-memory dict always mirrors the BOUND session (the one the widget shows);
``set`` writes to that session. Field values are coerced: a value of the wrong
type becomes the field default, unknown names are ignored on data paths.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from PySide6.QtCore import QSettings

from core.state_management.session_state_slots import (
    SessionStateSet,
    register_session_state_slot,
)

logger = logging.getLogger("ImproveImgSLI")

_QS_ORG = "improve-imgsli"
_QS_APP = "improve-imgsli"

_SUPPORTED_TYPES = (bool, str, int, float)


def _coerce(typ: type, default: Any, value: Any) -> Any:
    if typ is bool:
        return value if isinstance(value, bool) else default
    if typ is int:
        return value if isinstance(value, int) and not isinstance(value, bool) else default
    if typ is float:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return default
    if typ is str:
        return value if isinstance(value, str) else default
    return default


class SessionState:
    """Declarative session-scoped chrome state; see the module docstring."""

    def __init__(
        self,
        *,
        namespace: str,
        fields: dict,
        apply: Callable[[dict], None],
        collect: Callable[[], dict] | None,
        owner: str,
    ) -> None:
        for name, spec in fields.items():
            typ, _default = spec
            if typ not in _SUPPORTED_TYPES:
                raise TypeError(f"SessionState field {name!r}: unsupported type {typ!r}")
        self._namespace = str(namespace)
        self._fields: dict[str, tuple[type, Any]] = {n: (s[0], s[1]) for n, s in fields.items()}
        self._apply = apply
        self._collect = collect
        self._owner = owner
        self._values: dict[str, Any] = self._defaults()
        self._context: Any = None
        self._session_id: str | None = None

    @classmethod
    def bind(
        cls,
        tab: Any,
        *,
        namespace: str,
        fields: dict,
        apply: Callable[[dict], None],
        collect: Callable[[], dict] | None = None,
    ) -> "SessionState":
        register_session_state_slot(namespace)
        return cls(
            namespace=namespace,
            fields=fields,
            apply=apply,
            collect=collect,
            owner=type(tab).__name__,
        )

    # -- in-memory values --------------------------------------------------

    def get(self, field: str) -> Any:
        if field not in self._fields:
            raise KeyError(field)
        return self._values[field]

    def set(self, field: str, value: Any) -> None:
        if field not in self._fields:
            raise KeyError(field)
        typ, default = self._fields[field]
        value = _coerce(typ, default, value)
        if value == self._values[field]:
            return
        self._values[field] = value
        self._save_last_used()
        if self._session_id is not None:
            self._write_slot(self._session_id, self.as_dict())

    def as_dict(self) -> dict:
        return dict(self._values)

    # -- lifecycle ---------------------------------------------------------

    def attach(self, context: Any) -> None:
        """Remember the context used for slot writes (store/dispatcher)."""
        if context is not None:
            self._context = context

    def apply_from_slot(self, context: Any, session_id: str) -> None:
        """Bind to ``session_id`` and apply its values (slot first, QSettings fallback)."""
        self.attach(context)
        values = self._slot_values(session_id) or self._last_used_values() or self._defaults()
        self._session_id = session_id
        self._values = dict(values)
        self._call_apply()

    def seed_slot(self, context: Any, session_id: str) -> None:
        """New session inherits last-used; an already active/bound session is applied."""
        self.attach(context)
        existing = self._slot_values(session_id)
        if existing is None:
            values = self._last_used_values() or self._defaults()
            self._write_slot(session_id, values)
        else:
            values = existing
        if self._session_id == session_id or self._active_session_id() == session_id:
            self._session_id = session_id
            self._values = dict(values)
            self._call_apply()

    # -- project I/O -------------------------------------------------------

    def serialize(self, context: Any = None, session_id: str | None = None) -> dict:
        """``{name: value}`` for ``session_id`` (its slot) or the bound session."""
        if context is not None and session_id is not None:
            slot = self._slot_values(session_id, context=context)
            if slot is not None:
                return slot
        if self._collect is not None:
            return self._coerced_all(self._collect())
        return self.as_dict()

    def deserialize(self, data: dict, context: Any = None, session_id: str | None = None) -> None:
        """Load a snapshot. ``session_id=None`` updates the bound in-memory values;
        an explicit id writes that session's slot (and memory when bound to it)."""
        if not isinstance(data, dict):
            return
        values = self._coerced_all(data)
        if session_id is None:
            self._values = values
            return
        self.attach(context)
        self._write_slot(session_id, values)
        if session_id == self._session_id:
            self._values = dict(values)

    # -- internals ---------------------------------------------------------

    def _defaults(self) -> dict:
        return {name: default for name, (_t, default) in self._fields.items()}

    def _coerced_all(self, data: dict) -> dict:
        out = self._defaults()
        for name, (typ, default) in self._fields.items():
            if name in data:
                out[name] = _coerce(typ, default, data[name])
        return out

    def _call_apply(self) -> None:
        try:
            self._apply(self.as_dict())
        except Exception:
            logger.debug("SessionState(%s) apply failed for %s", self._namespace, self._owner, exc_info=True)

    def _store(self, context: Any = None) -> Any:
        ctx = context if context is not None else self._context
        return getattr(ctx, "store", None)

    def _slot_values(self, session_id: str, *, context: Any = None) -> dict | None:
        store = self._store(context)
        if store is None:
            return None
        try:
            raw = store.get_session_state_slot(self._namespace, session_id=session_id)
        except Exception:
            return None
        if not isinstance(raw, dict) or not any(n in raw for n in self._fields):
            return None
        return self._coerced_all(raw)

    def _write_slot(self, session_id: str, values: dict) -> None:
        store = self._store()
        if store is None:
            return
        action = SessionStateSet(namespace=self._namespace, values=dict(values))
        try:
            dispatcher = store.get_dispatcher()
            if dispatcher is not None:
                dispatcher.dispatch(action, scope=self._namespace, session_id=session_id)
            else:
                store.set_session_state_slot(
                    self._namespace, dict(values), session_id=session_id, emit_scope=None
                )
        except Exception:
            logger.debug("SessionState(%s) slot write failed", self._namespace, exc_info=True)

    def _active_session_id(self) -> str | None:
        store = self._store()
        if store is None:
            return None
        try:
            active = store.get_active_workspace_session()
        except Exception:
            return None
        return getattr(active, "id", None)

    def _qs_key(self) -> str:
        return f"{self._namespace}/chrome"

    def _save_last_used(self) -> None:
        try:
            settings = QSettings(_QS_ORG, _QS_APP)
            settings.setValue(self._qs_key(), json.dumps(self.as_dict()))
            settings.sync()
        except Exception:
            logger.debug("SessionState(%s) last-used save failed", self._namespace, exc_info=True)

    def _last_used_values(self) -> dict | None:
        try:
            raw = QSettings(_QS_ORG, _QS_APP).value(self._qs_key())
            if not raw:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8")
            data = json.loads(str(raw))
            if not isinstance(data, dict):
                return None
            return self._coerced_all(data)
        except Exception:
            logger.debug("SessionState(%s) last-used load failed", self._namespace, exc_info=True)
            return None
