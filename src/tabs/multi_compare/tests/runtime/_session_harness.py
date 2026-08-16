"""Shared fake core-store + dispatcher harness for multi_compare session tests.

The MC session slot is now written by the core Dispatcher (bound
``MultiCompareStore`` facade), not by ``MultiCompareTab``. These fakes emulate
the narrow slice of core behavior the facade depends on — active session
resolution, slot read/write, ``on_change`` emission, and an MC-only dispatcher
that reduces into the active session's slot — so session-isolation tests can
run without the full workspace machinery.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.multi_compare.models import MultiCompareState
from tabs.multi_compare.scene.store import reduce as mc_reduce
from tabs.multi_compare.tab import _STATE_SLOT


class FakeDispatcher:
    def __init__(self, core_store):
        self._core = core_store

    def dispatch(self, action, scope="viewport"):
        session = self._core.get_active_workspace_session()
        if session is None:
            return
        current = session.state_slots.get(_STATE_SLOT)
        if not isinstance(current, MultiCompareState):
            current = MultiCompareState()
        new_state = mc_reduce(current, action)
        if new_state is not current:
            session.state_slots[_STATE_SLOT] = new_state
            self._core.emit("multi_compare")

    def can_undo(self):
        return False

    def can_redo(self):
        return False

    def undo(self):
        return None

    def redo(self):
        return None


class FakeCoreStore:
    def __init__(self, session_ids):
        self.sessions = {
            sid: SimpleNamespace(id=sid, session_type="multi_compare", state_slots={})
            for sid in session_ids
        }
        self.active_session_id = session_ids[0]
        self._callbacks = []
        self.dispatcher = FakeDispatcher(self)

    def get_active_workspace_session(self):
        return self.sessions[self.active_session_id]

    def on_change(self, callback):
        self._callbacks.append(callback)

    def emit(self, scope):
        for callback in list(self._callbacks):
            callback(scope)

    def get_dispatcher(self):
        return self.dispatcher

    def ensure_slot(self, session_id, factory=None):
        from tabs.multi_compare.tab import _fresh_default_state

        session = self.sessions[session_id]
        if _STATE_SLOT not in session.state_slots:
            session.state_slots[_STATE_SLOT] = factory() if factory else _fresh_default_state()
        return session.state_slots[_STATE_SLOT]

    def switch_active(self, session_id):
        self.active_session_id = session_id