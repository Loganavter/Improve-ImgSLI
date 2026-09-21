"""Store silent-failure paths fail loud (never silent-drop).

Covers ``task-fix-store-silent-2026-09-20``:
- ``Store.transact`` without a dispatcher raises (loud) instead of
  swallowing every action.
- ``Store.transact`` sequential fallback logs each failed action and
  re-raises instead of ``continue``-ing in silence.
- ``Store.publish`` emit errors are logged, never swallowed.
- ``Store.batch_changes`` flushes only on success; a raising block
  discards queued scopes and propagates.
- ``register_state_slot_reducer`` warns on duplicate-with-different
  reducer; ``unregister_state_slot_reducer`` removes (True) or reports
  missing (False).
- ``Dispatcher`` optimistic-retry exhaustion is logged, never a silent
  no-op drop.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from core.state_management import slot_reducers as _slot_reducers_module
from core.state_management.slot_reducers import (
    register_state_slot_reducer,
    unregister_state_slot_reducer,
)
from core.store import Store


@pytest.fixture()
def _saved_slot_reducers():
    saved = dict(_slot_reducers_module._SLOT_REDUCERS)
    yield
    _slot_reducers_module._SLOT_REDUCERS.clear()
    _slot_reducers_module._SLOT_REDUCERS.update(saved)


def _action(action_type: str):
    from core.state_management.actions import SetSplitPositionAction

    return SetSplitPositionAction(0.5)


def test_transact_without_dispatcher_raises_loudly(caplog):
    store = Store()
    assert store.get_dispatcher() is None
    with caplog.at_level(logging.ERROR, logger="ImproveImgSLI"):
        with pytest.raises(RuntimeError, match="requires a dispatcher"):
            store.transact([_action("SET_SPLIT_POSITION")], scope="document")
    assert any("transact" in r.message for r in caplog.records)


def test_transact_sequential_fallback_logs_and_reraises(caplog):
    from core.state_management.transaction import TransactionAction

    store = Store()
    calls: list = []

    class _BoomDispatcher:
        def dispatch(self, action, scope="viewport"):
            calls.append(getattr(action, "type", None))
            raise ValueError("boom")

    store.set_dispatcher(_BoomDispatcher())
    with caplog.at_level(logging.ERROR, logger="ImproveImgSLI"):
        with pytest.raises(ValueError, match="boom"):
            store.transact(
                [_action("SET_SPLIT_POSITION"), _action("SET_SPLIT_POSITION")],
                scope="viewport",
            )
    # TransactionAction dispatch failed (1 call), then sequential fallback
    # re-dispatched the first inner action and re-raised loudly.
    assert calls[0] == "TRANSACTION"
    assert any("sequential" in r.message for r in caplog.records)


def test_publish_emit_error_logged_not_swallowed(caplog):
    store = Store()
    store.on_change(lambda _scope: (_ for _ in ()).throw(ValueError("bad subscriber")))
    with caplog.at_level(logging.ERROR, logger="ImproveImgSLI"):
        store.publish("lod_available")  # must not raise
    assert any("publish" in r.message for r in caplog.records)


def test_batch_changes_flushes_on_success_only():
    store = Store()
    seen: list = []
    store.on_change(seen.append)

    with store.batch_changes():
        store.emit_state_change("viewport")
        store.emit_state_change("document")
        store.emit_state_change("viewport")
        assert seen == []
    assert seen == ["viewport", "document"]

    # Failure: queued scopes discarded, exception propagates, depth reset.
    seen.clear()
    with pytest.raises(ValueError, match="mid-batch"):
        with store.batch_changes():
            store.emit_state_change("viewport")
            raise ValueError("mid-batch")
    assert seen == []
    store.emit_state_change("viewport")
    assert seen == ["viewport"]


def test_batch_changes_nested_failure_discards_all():
    store = Store()
    seen: list = []
    store.on_change(seen.append)

    with pytest.raises(ValueError, match="inner"):
        with store.batch_changes():
            store.emit_state_change("viewport")
            with store.batch_changes():
                store.emit_state_change("document")
                raise ValueError("inner")
    assert seen == []
    assert store._change_batch_depth == 0


def test_slot_register_duplicate_warns_and_replaces(_saved_slot_reducers, caplog):
    first = lambda state, action: state
    second = lambda state, action: state
    register_state_slot_reducer("dup.slot", first)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        register_state_slot_reducer("dup.slot", second)
    assert any("duplicate" in r.message for r in caplog.records)
    assert _slot_reducers_module._SLOT_REDUCERS["dup.slot"] is second


def test_slot_register_same_reducer_stays_quiet(_saved_slot_reducers, caplog):
    reducer = lambda state, action: state
    register_state_slot_reducer("same.slot", reducer)
    with caplog.at_level(logging.WARNING, logger="ImproveImgSLI"):
        register_state_slot_reducer("same.slot", reducer)
    assert not [r for r in caplog.records if "duplicate" in r.message]


def test_slot_unregister(_saved_slot_reducers):
    reducer = lambda state, action: state
    assert unregister_state_slot_reducer("missing.slot") is False
    register_state_slot_reducer("gone.slot", reducer)
    assert unregister_state_slot_reducer("gone.slot") is True
    assert "gone.slot" not in _slot_reducers_module._SLOT_REDUCERS


class _FlappingStore:
    """Every ``viewport`` read returns a fresh object → the dispatcher's
    optimistic identity check always observes a concurrent mutation."""

    def __init__(self):
        self.settings = SimpleNamespace(current_language="en")
        self._slots: dict = {}
        self.events: list = []

    @property
    def viewport(self):
        return SimpleNamespace(tag="flap")

    @viewport.setter
    def viewport(self, value):
        pass

    def get_active_workspace_session(self):
        return None

    def get_workspace_session(self, session_id):
        return None

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        return self._slots.setdefault(slot, SimpleNamespace(tag=slot))

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=""):
        self._slots[slot] = value

    def emit_state_change(self, scope):
        self.events.append(scope)


def test_dispatcher_retry_exhaustion_logged(caplog, _saved_slot_reducers):
    from core.state_management.dispatcher import Dispatcher

    register_state_slot_reducer("document", lambda state, action: state)
    store = _FlappingStore()
    dispatcher = Dispatcher(store)

    class _FreshReducer:
        def reduce(self, store_arg, action):
            viewport = SimpleNamespace(tag="new")
            return SimpleNamespace(
                viewport=viewport,
                settings=store_arg.settings,
                get_session_state_slot=lambda slot: store_arg.get_session_state_slot(slot),
            )

    dispatcher._reducer = _FreshReducer()
    with caplog.at_level(logging.ERROR, logger="ImproveImgSLI"):
        dispatcher.dispatch(_action("SET_SPLIT_POSITION"), scope="viewport")
    assert any("exhausted" in r.message for r in caplog.records)
    assert store.events == []
