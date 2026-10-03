"""Session-targeted dispatch (Wave CORE write side).

Read-side isolation shipped earlier (own-session reads, inactive-skip);
``Dispatcher.dispatch`` still addressed the ACTIVE session only, so a
background tab's late worker completion landing while another tab was
active wrote into the FOREIGN active session's slots. ``dispatch`` /
``transact`` / ``RootReducer.reduce`` now take an optional ``session_id``:
None (default) is exactly today's active behavior, an explicit id routes
snapshot → reduce → write-back plus history bookkeeping to that session.

Real ``Store`` + real ``Dispatcher`` throughout (concurrency-test
precedent); a probe slot reducer under a unique name stands in for any
tab-owned slot. The probe reducer is unregistered after each test so the
global registry never leaks.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from core.state_management.action_base import Action
from core.state_management.dispatcher import Dispatcher
from core.state_management.slot_reducers import (
    register_state_slot_reducer,
    unregister_state_slot_reducer,
)
from core.store import Store

PROBE_SLOT = "__wave_core_probe__"


@dataclass
class _ProbeSet(Action):
    type: str = "PROBE_SET"
    value: object = None

    def get_payload(self) -> dict:
        return {"value": self.value}


def _probe_reducer(current, action):
    if getattr(action, "type", None) == "PROBE_SET":
        return action.value
    return current


@pytest.fixture()
def probe_store():
    """Real Store + Dispatcher with two image_compare sessions, B active."""
    register_state_slot_reducer(PROBE_SLOT, _probe_reducer)
    try:
        store = Store()
        dispatcher = Dispatcher(store)
        store.set_dispatcher(dispatcher)
        sess_a = store.create_workspace_session(
            session_type="image_compare", activate=False
        )
        sess_b = store.create_workspace_session(
            session_type="image_compare", activate=False
        )
        assert store.switch_workspace_session(sess_b.id)
        dispatcher.bind_history_for_session(sess_b.id)
        yield store, dispatcher, sess_a, sess_b
    finally:
        unregister_state_slot_reducer(PROBE_SLOT)


def _slot(store, session_id):
    return store.get_session_state_slot(PROBE_SLOT, session_id=session_id)


def test_background_session_dispatch_lands_in_own_slots(probe_store) -> None:
    """Explicit id routes the write to that session; active untouched."""
    store, dispatcher, sess_a, sess_b = probe_store
    viewport_b_before = sess_b.viewport
    viewport_a_before = sess_a.viewport

    dispatcher.dispatch(_ProbeSet(value="for-A"), scope="probe", session_id=sess_a.id)

    assert _slot(store, sess_a.id) == "for-A"
    assert _slot(store, sess_b.id) is None
    assert store.get_active_workspace_session().id == sess_b.id
    # No cross-session viewport aliasing: B keeps its own viewport object,
    # A never receives the active-derived one.
    assert sess_b.viewport is viewport_b_before
    assert sess_a.viewport is viewport_a_before
    assert sess_a.viewport is not sess_b.viewport


def test_default_dispatch_unchanged_active_behavior(probe_store) -> None:
    """No session_id: write lands in the ACTIVE session exactly as before."""
    store, dispatcher, sess_a, sess_b = probe_store

    dispatcher.dispatch(_ProbeSet(value="for-active"), scope="probe")

    assert _slot(store, sess_b.id) == "for-active"
    assert _slot(store, sess_a.id) is None


def test_explicit_history_binds_target_session(probe_store) -> None:
    """This dispatch's history lands in the target's stacks; the standing
    binding (active tab's undo) is never moved by a background dispatch."""
    store, dispatcher, sess_a, sess_b = probe_store

    dispatcher.dispatch(_ProbeSet(value="for-A"), scope="probe", session_id=sess_a.id)

    assert len(sess_a.state_slots["action_history"]) == 1
    assert sess_a.state_slots["action_history"][0].value == "for-A"
    assert sess_a.state_slots["undo_stack"] == []
    assert sess_a.state_slots["redo_stack"] == []
    assert sess_b.state_slots.get("action_history") == []
    assert dispatcher._bound_session_id == sess_b.id

    dispatcher.dispatch(_ProbeSet(value="for-active"), scope="probe")
    assert len(sess_b.state_slots["action_history"]) == 1
    assert len(sess_a.state_slots["action_history"]) == 1


def test_interleaved_dispatches_stay_isolated(probe_store) -> None:
    """Alternating background/foreground writes (incl. transact) accumulate
    per-session without leaking — the sequential form of the
    concurrent-interleaving case (snapshot vs write-back address the same
    targeted session, so no retry/mis-write path is involved)."""
    store, dispatcher, sess_a, sess_b = probe_store

    for i in range(3):
        dispatcher.dispatch(
            _ProbeSet(value=f"a-{i}"), scope="probe", session_id=sess_a.id
        )
        dispatcher.dispatch(_ProbeSet(value=f"b-{i}"), scope="probe")
    store.transact(
        [_ProbeSet(value="a-tx1"), _ProbeSet(value="a-tx2")],
        scope="probe",
        session_id=sess_a.id,
    )

    assert _slot(store, sess_a.id) == "a-tx2"
    assert _slot(store, sess_b.id) == "b-2"
    assert len(sess_a.state_slots["action_history"]) == 4
    assert len(sess_b.state_slots["action_history"]) == 3


def test_unknown_session_id_fails_open_to_active(probe_store) -> None:
    """Bogus id: fail-open to today's active behavior, never a silent drop."""
    store, dispatcher, sess_a, sess_b = probe_store
    seen: list = []
    dispatcher.subscribe(seen.append)

    dispatcher.dispatch(_ProbeSet(value="bogus"), scope="probe", session_id="nope")

    assert _slot(store, sess_b.id) == "bogus"
    assert _slot(store, sess_a.id) is None
    assert [a.value for a in seen] == ["bogus"]


def test_explicit_dispatch_emits_scope_unchanged(probe_store) -> None:
    """Emit scope is untouched by targeting (subscribers still filter)."""
    store, dispatcher, sess_a, sess_b = probe_store
    emitted: list = []
    store.on_change(emitted.append)

    dispatcher.dispatch(_ProbeSet(value="for-A"), scope="probe", session_id=sess_a.id)

    assert emitted == ["probe"]


def test_threaded_targeted_dispatch_loses_nothing(probe_store) -> None:
    """Threads racing background/foreground dispatches: no lost history,
    every write lands in its addressed session (optimistic retry covers a
    concurrent mutation of the TARGET session consistently)."""
    store, dispatcher, sess_a, sess_b = probe_store
    per_thread = 5
    thread_count = 4
    barrier = threading.Barrier(thread_count)
    errors: list = []

    def worker(tid: int):
        try:
            barrier.wait(timeout=5)
            for i in range(per_thread):
                if tid % 2 == 0:
                    dispatcher.dispatch(
                        _ProbeSet(value=f"t{tid}-{i}"),
                        scope="probe",
                        session_id=sess_a.id,
                    )
                else:
                    dispatcher.dispatch(_ProbeSet(value=f"t{tid}-{i}"), scope="probe")
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive(), "targeted dispatch thread hung - deadlock"

    assert not errors, f"worker errors: {errors}"
    total_history = len(sess_a.state_slots["action_history"]) + len(
        sess_b.state_slots["action_history"]
    )
    assert total_history == thread_count * per_thread, (
        f"history lost entries: {total_history} != {thread_count * per_thread}"
    )
    assert _slot(store, sess_a.id) in {f"t{tid}-{i}" for tid in (0, 2) for i in range(per_thread)}
    assert _slot(store, sess_b.id) in {f"t{tid}-{i}" for tid in (1, 3) for i in range(per_thread)}


def test_traced_dispatch_forwards_session_id(probe_store) -> None:
    """Instrumentation stays signature-transparent (prod incident 2026-10-03).

    With tracing installed AND enabled, ``dispatch(..., session_id=...)``
    must reach the real dispatcher (previously ``traced_dispatch`` lacked
    the kwarg → TypeError → gallery dispatches died under --debug and every
    tab switch restored empty slots). Patched class restored afterwards so
    no global state leaks into other tests.
    """
    from core.state_management import dispatcher as dispatcher_mod
    from core.tracing import instrumentation as instrumentation_mod
    from core.tracing.tracer import Tracer

    orig_dispatch = dispatcher_mod.Dispatcher.dispatch
    tracer = Tracer.instance()
    was_enabled = bool(Tracer.enabled())
    try:
        instrumentation_mod.install_instrumentation()
        store, dispatcher, sess_a, sess_b = probe_store
        assert store.get_active_workspace_session().id == sess_b.id
        dispatcher.dispatch(_ProbeSet(value="traced-a"), scope="test", session_id=sess_a.id)
        assert _slot(store, sess_a.id) == "traced-a"
        assert _slot(store, sess_b.id) is None
        try:
            tracer.enable()
            dispatcher.dispatch(_ProbeSet(value="traced-a2"), scope="test", session_id=sess_a.id)
        finally:
            if not was_enabled:
                tracer.disable()
        assert _slot(store, sess_a.id) == "traced-a2"
        assert _slot(store, sess_b.id) is None
    finally:
        dispatcher_mod.Dispatcher.dispatch = orig_dispatch
        try:
            if Tracer.enabled() != was_enabled:
                tracer.enable() if was_enabled else tracer.disable()
        except Exception:
            pass
