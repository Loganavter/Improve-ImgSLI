"""Declarative per-session chrome state for a tab (``SessionState`` facade).

One object owns a tab's small per-session UI state (toolbar switches and the
like) across its three homes:

1. the session slot (plain dict under ``namespace``, reduced by
   ``SessionStateSet``; or, with ``slot=``, the tab's own typed slot read and
   written through the tab's pure ``extract``/``merge``);
2. the last-used QSettings value ``f"{namespace}/chrome"`` (new sessions seed
   from it, and it survives app restarts);
3. project I/O via ``serialize``/``deserialize`` (plain ``{name: value}``).

Field types: ``bool``, ``int``, ``float``, ``str``, ``dict`` and ``list``
(containers are JSON round-tripped and deep-copied, never shared with the
default).

Lifecycle contract: ``serialize``/``deserialize`` run only on project save/load
and duplicate. A session SWITCH runs ``on_activated`` /
``on_active_session_changed`` only, so those delegates must call
``apply_from_slot`` (which reads the LIVE slot, never the project snapshot).

The facade wires no hooks itself; the tab's thin delegates call its methods.
The in-memory values always mirror the BOUND session (the one the widget shows);
``set`` writes to that session. Field values are coerced: a value of the wrong
type becomes the field default, unknown names are ignored on data paths.

Two sanctioned mechanisms exist for session chrome. This facade is one. The
other is image_compare's store-driven session ``viewport``, which is not a
violation of the ``tests/contracts`` session-persistence guard. Tabs with
their own slot model (e.g. multi_compare) use the typed-slot binding.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Callable

from PySide6.QtCore import QSettings

from core.plugin_system.settings import SETTINGS_APP, SETTINGS_ORG
from core.state_management.session_state_slots import (
    SessionStateSet,
    register_session_state_slot,
    register_typed_session_slot,
)

logger = logging.getLogger("ImproveImgSLI")

# Aliases kept so existing call sites (and any importer of these names) keep
# working; the canonical pair is the single source of the persisted identity.
_QS_ORG = SETTINGS_ORG
_QS_APP = SETTINGS_APP

_SUPPORTED_TYPES = (bool, str, int, float, dict, list)


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
    if typ in (dict, list):
        return copy.deepcopy(value) if isinstance(value, typ) else copy.deepcopy(default)
    return copy.deepcopy(default)


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
        slot: str | None = None,
        merge: Callable[[Any, dict], Any] | None = None,
        extract: Callable[[Any], dict] | None = None,
        last_used_key: str | None = None,
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
        self._slot_name = str(slot) if slot is not None else self._namespace
        self._typed = slot is not None
        self._merge = merge
        self._extract = extract
        self._last_used_key = last_used_key or f"{self._namespace}/chrome"
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
        slot: str | None = None,
        merge: Callable[[Any, dict], Any] | None = None,
        extract: Callable[[Any], dict] | None = None,
        last_used_key: str | None = None,
    ) -> "SessionState":
        """Bind a facade to ``tab``.

        Without ``slot`` the values live in the plain dict slot ``namespace``.
        With ``slot=<name>`` (a tab-owned typed slot) both ``merge`` and
        ``extract`` are required: ``merge(state, values) -> state`` must be pure
        and accept partial ``values``; ``extract(state) -> values`` is its
        inverse. ``last_used_key`` overrides the QSettings key (default
        ``f"{namespace}/chrome"``) so an existing last-used value stays readable.
        """
        if slot is None:
            if merge is not None or extract is not None:
                raise TypeError("SessionState.bind: merge/extract require slot=")
            register_session_state_slot(namespace)
        else:
            if merge is None or extract is None:
                raise TypeError("SessionState.bind: slot= requires merge= and extract=")
            register_typed_session_slot(slot, merge, extract)
        return cls(
            namespace=namespace,
            fields=fields,
            apply=apply,
            collect=collect,
            owner=type(tab).__name__,
            slot=slot,
            merge=merge,
            extract=extract,
            last_used_key=last_used_key,
        )

    # -- in-memory values --------------------------------------------------

    def get(self, field: str) -> Any:
        if field not in self._fields:
            raise KeyError(field)
        return copy.deepcopy(self._values[field])

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
            # A typed slot may hold edits made through the tab's own actions,
            # so only the changed field is written (the others stay as-is).
            payload = {field: value} if self._typed else self.as_dict()
            self._write_slot(self._session_id, payload)

    def as_dict(self) -> dict:
        return copy.deepcopy(self._values)

    def remember(self, values: dict) -> None:
        """Adopt ``values`` as the bound values and save them as last-used.

        No slot write: for tabs whose chrome is changed through their own
        actions, the slot is already current and only the mirror and QSettings
        need to follow.
        """
        if not isinstance(values, dict):
            return
        for name, value in values.items():
            if name in self._fields:
                typ, default = self._fields[name]
                self._values[name] = _coerce(typ, default, value)
        self._save_last_used()

    # -- lifecycle ---------------------------------------------------------

    def attach(self, context: Any) -> None:
        """Remember the context used for slot writes (store/dispatcher)."""
        if context is not None:
            self._context = context

    def apply_from_slot(self, context: Any, session_id: str) -> None:
        """Bind to ``session_id`` and apply its values (slot first, QSettings fallback).

        A slot that still holds ONLY the factory defaults carries nothing the
        user chose - it must not shadow the QSettings fallback (the config).
        Measured live 2026-10-22: the gallery restored "judgment_domain=
        algorithms" although the config said "ai" - the fix in ``seed_slot``
        alone was not enough, because the RESTORE path is this one.
        """
        self.attach(context)
        slot_values = self._slot_values(session_id)
        if slot_values is None or slot_values == self._defaults():
            values = self._last_used_values() or self._defaults()
        else:
            values = slot_values
        self._session_id = session_id
        self._values = dict(values)
        self._call_apply()

    def seed_slot(self, context: Any, session_id: str) -> None:
        """New session inherits last-used; an already active/bound session is applied.

        A typed slot is created at its factory defaults by the blueprint, so it
        has no "existing" values to keep: every new session takes last-used.
        """
        self.attach(context)
        existing = None if self._typed else self._slot_values(session_id)
        # A slot that holds ONLY the factory defaults carries nothing the user
        # chose. The blueprint auto-allocates the slot at the defaults, so
        # treating it as "existing" silently BLOCKED the documented
        # inheritance: "a NEW session inherits the last-used toolbar chrome
        # (QSettings) so it does not reset the switches" - the config route was
        # dead for every plain slot (measured live 2026-10-22: a config with
        # judgment_domain=ai was ignored and the app restored 'algorithms').
        # A slot with a NON-default value is the user's choice and wins.
        if existing is None or existing == self._defaults():
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
        return {name: copy.deepcopy(default) for name, (_t, default) in self._fields.items()}

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
            raw = store.get_session_state_slot(self._slot_name, session_id=session_id)
        except Exception:
            return None
        if self._typed:
            if raw is None or self._extract is None:
                return None
            try:
                values = self._extract(raw)
            except Exception:
                logger.debug("SessionState(%s) typed extract failed", self._namespace, exc_info=True)
                return None
            return self._coerced_all(values) if isinstance(values, dict) else None
        if not isinstance(raw, dict) or not any(n in raw for n in self._fields):
            return None
        return self._coerced_all(raw)

    def _write_slot(self, session_id: str, values: dict) -> None:
        store = self._store()
        if store is None:
            return
        action = SessionStateSet(namespace=self._slot_name, values=dict(values))
        try:
            getter = getattr(store, "get_dispatcher", None)
            dispatcher = getter() if callable(getter) else None
            if dispatcher is not None:
                dispatcher.dispatch(action, scope=self._slot_name, session_id=session_id)
            else:
                merged = self._merged_slot_value(store, session_id, values)
                if merged is not None:
                    store.set_session_state_slot(
                        self._slot_name, merged, session_id=session_id, emit_scope=None
                    )
        except Exception:
            logger.debug("SessionState(%s) slot write failed", self._namespace, exc_info=True)

    def _merged_slot_value(self, store: Any, session_id: str, values: dict) -> Any:
        """Dispatcher-less fallback: the same merge the slot reducer would apply."""
        current = store.get_session_state_slot(self._slot_name, session_id=session_id)
        if self._typed:
            if current is None or self._merge is None:
                return None
            return self._merge(current, dict(values))
        base = dict(current) if isinstance(current, dict) else {}
        base.update(values)
        return base

    def _active_session_id(self) -> str | None:
        store = self._store()
        if store is None:
            return None
        try:
            active = store.get_active_workspace_session()
        except Exception:
            return None
        return getattr(active, "id", None)

    def _save_last_used(self) -> None:
        try:
            settings = QSettings(_QS_ORG, _QS_APP)
            settings.setValue(self._last_used_key, json.dumps(self.as_dict()))
            settings.sync()
        except Exception:
            logger.debug("SessionState(%s) last-used save failed", self._namespace, exc_info=True)

    def _last_used_values(self) -> dict | None:
        try:
            raw = QSettings(_QS_ORG, _QS_APP).value(self._last_used_key)
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


__all__ = ["SessionState"]
