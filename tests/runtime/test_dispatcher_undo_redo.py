"""Dispatcher undo/redo: reference-snapshot stacks, per-session isolation,
coalescing of continuous gestures, loading-block, and transient-action
exclusion."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.state_management import slot_reducers as _slot_reducers_module
from core.state_management.actions import Action
from core.state_management.dispatcher import (
    Dispatcher,
    _COALESCE_TYPES,
    _UNDOABLE_TYPES,
)
from core.state_management.slot_reducers import register_state_slot_reducer


@pytest.fixture(autouse=True)
def _document_slot_reducer():
    """The Dispatcher syncs slots via the slot-reducer registry; register a
    ``document`` entry so the fake store's document participates in write-back
    and undo restore. Snapshot/restore the registry around each test."""
    saved = dict(_slot_reducers_module._SLOT_REDUCERS)
    register_state_slot_reducer("document", lambda state, action: state)
    yield
    _slot_reducers_module._SLOT_REDUCERS.clear()
    _slot_reducers_module._SLOT_REDUCERS.update(saved)


class _Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.state_slots: dict = {}


class _Store:
    def __init__(self, sessions: dict[str, _Session], active_id: str):
        self._sessions = sessions
        self.workspace = SimpleNamespace(active_session_id=active_id)
        self.settings = SimpleNamespace(current_language="en")
        self.viewport = SimpleNamespace(
            tag="initial",
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(unification_in_progress=False)
            ),
        )
        self.document = SimpleNamespace(seq=0)
        self.events: list[str] = []

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def get_active_workspace_session(self):
        return self._sessions.get(self.workspace.active_session_id)

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        if slot == "document":
            return self.document
        sess = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        return sess.state_slots.get(slot, default)

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=""):
        if slot == "document":
            self.document = value
            return
        sess = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        sess.state_slots[slot] = value

    def emit_state_change(self, scope):
        self.events.append(scope)


class _Reducer:
    """Stand-in for RootReducer: for undoable actions returns a fresh store
    carrying a distinguishable viewport/document pair (immutable-style, so the
    pre-dispatch refs stay untouched)."""

    def __init__(self):
        self._counter = 0

    def reduce(self, store, action: Action):
        if action.type not in _UNDOABLE_TYPES:
            return store
        self._counter += 1
        n = self._counter
        document = SimpleNamespace(seq=n)
        viewport = SimpleNamespace(
            tag=f"{action.type}#{n}",
            session_data=store.viewport.session_data,
        )
        return SimpleNamespace(
            viewport=viewport,
            document=document,
            settings=store.settings,
            get_session_state_slot=lambda slot, doc=document: (
                doc if slot == "document" else None
            ),
        )


def _mk_dispatcher():
    sessions = {"a": _Session("a"), "b": _Session("b")}
    store = _Store(sessions, "a")
    dispatcher = Dispatcher(store)
    dispatcher._reducer = _Reducer()
    return store, dispatcher


def _action(action_type: str) -> Action:
    from core.state_management.actions import SetSplitPositionAction

    if action_type == "SET_SPLIT_POSITION":
        return SetSplitPositionAction(0.5)
    from core.state_management.actions import ToggleOrientationAction

    if action_type == "TOGGLE_ORIENTATION":
        return ToggleOrientationAction(is_horizontal=True)
    from core.state_management.actions import SetPressedKeysAction

    return SetPressedKeysAction([])


def test_undo_redo_restores_viewport_and_document():
    store, dispatcher = _mk_dispatcher()
    first = store.viewport, store.document

    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    mid = store.viewport, store.document
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))
    assert store.viewport.tag == "TOGGLE_ORIENTATION#2"

    assert dispatcher.can_undo()
    dispatcher.undo()
    assert (store.viewport, store.document) == mid
    dispatcher.undo()
    assert (store.viewport, store.document) == first
    assert not dispatcher.can_undo()

    assert dispatcher.can_redo()
    dispatcher.redo()
    assert (store.viewport, store.document) == mid
    dispatcher.redo()
    assert store.viewport.tag == "TOGGLE_ORIENTATION#2"
    assert not dispatcher.can_redo()


def test_undo_redo_stacks_are_per_session():
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    assert dispatcher.can_undo()

    dispatcher.bind_history_for_session("b")
    assert not dispatcher.can_undo()
    dispatcher.undo()  # no-op on an empty bound stack
    assert store.viewport.tag == "SET_SPLIT_POSITION#1"

    dispatcher.bind_history_for_session("a")
    assert dispatcher.can_undo()
    dispatcher.undo()
    assert store.viewport.tag == "initial"


def test_coalesces_continuous_same_type():
    store, dispatcher = _mk_dispatcher()
    first = store.viewport
    for i in range(3):
        dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    assert len(dispatcher._undo_stack) == 1

    dispatcher.undo()
    assert store.viewport is first
    assert not dispatcher.can_undo()


def test_redo_cleared_on_new_dispatch():
    _, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    dispatcher.undo()
    assert dispatcher.can_redo()

    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))
    assert not dispatcher.can_redo()


def test_busy_loading_blocks_undo():
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    store.viewport.session_data.render_cache.unification_in_progress = True
    assert not dispatcher.can_undo()
    dispatcher.undo()
    assert store.viewport.tag == "SET_SPLIT_POSITION#1"  # unchanged
    store.viewport.session_data.render_cache.unification_in_progress = False
    assert dispatcher.can_undo()


def test_transient_actions_are_not_recorded():
    _, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_PRESSED_KEYS"))
    assert not dispatcher.can_undo()


def test_clear_history_clears_undo_redo():
    _, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    dispatcher.undo()
    dispatcher.clear_history()
    assert not dispatcher.can_undo()
    assert not dispatcher.can_redo()


def test_allowlist_and_coalesce_sets_are_consistent():
    assert _COALESCE_TYPES <= _UNDOABLE_TYPES


def test_undo_redo_emits_restored_slot_scopes():
    """Undo/redo must notify consumers of every restored slot scope (e.g.
    "document") besides "viewport" — tabs use the emit to re-sync state that
    the reference snapshot cannot carry (closed pixel stores after browsing
    undo)."""
    store, dispatcher = _mk_dispatcher()
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    store.events.clear()

    dispatcher.undo()
    assert "viewport" in store.events
    assert "document" in store.events

    store.events.clear()
    dispatcher.redo()
    assert "viewport" in store.events
    assert "document" in store.events


def test_rapid_same_type_burst_groups_into_one_step(monkeypatch):
    """Non-continuous same-type actions dispatched within the rapid window
    merge into one undo step (one undo returns to the pre-burst state)."""
    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 60)
    store, dispatcher = _mk_dispatcher()
    first = store.viewport, store.document

    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))

    assert len(dispatcher._undo_stack) == 1
    dispatcher.undo()
    assert (store.viewport, store.document) == first


def test_slow_same_type_stays_separate_steps(monkeypatch):
    """Same-type actions outside the rapid window are separate undo steps."""
    import time

    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 30)
    store, dispatcher = _mk_dispatcher()

    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))
    time.sleep(0.05)
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))

    assert len(dispatcher._undo_stack) == 2


def test_rapid_burst_then_pause_then_burst_creates_two_steps(monkeypatch):
    """A burst after a pause starts a new undo step (rolling window per
    type)."""
    import time

    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 40)
    store, dispatcher = _mk_dispatcher()

    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))  # merge (burst 1)
    time.sleep(0.06)
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))  # new step
    dispatcher.dispatch(_action("TOGGLE_ORIENTATION"))  # merge (burst 2)

    assert len(dispatcher._undo_stack) == 2


def test_continuous_coalescing_is_not_time_limited(monkeypatch):
    """Continuous gestures merge regardless of elapsed time (a drag can last
    seconds) — the rapid window must not apply to _COALESCE_TYPES."""
    import time

    from core.state_management import dispatcher as _dispatcher_module

    monkeypatch.setattr(_dispatcher_module, "_RAPID_ACTION_GROUP_MS", 10)
    store, dispatcher = _mk_dispatcher()

    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))
    time.sleep(0.05)
    dispatcher.dispatch(_action("SET_SPLIT_POSITION"))

    assert len(dispatcher._undo_stack) == 1