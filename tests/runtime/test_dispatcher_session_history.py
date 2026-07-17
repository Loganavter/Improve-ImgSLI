"""Per-session action history isolation in Dispatcher."""

from __future__ import annotations

from types import SimpleNamespace

from core.state_management.actions import SetDebugModeEnabledAction
from core.state_management.dispatcher import Dispatcher


class _FakeSession:
    def __init__(self, session_id: str):
        self.id = session_id
        self.state_slots: dict = {}


class _FakeStore:
    def __init__(self, sessions: dict[str, _FakeSession], active_id: str):
        self._sessions = sessions
        self.workspace = SimpleNamespace(active_session_id=active_id)
        self.settings = SimpleNamespace(current_language="en")
        self.viewport = SimpleNamespace(session_data=SimpleNamespace())
        self._callbacks = []

    def get_workspace_session(self, session_id: str):
        return self._sessions.get(session_id)

    def get_active_workspace_session(self):
        return self._sessions.get(self.workspace.active_session_id)

    def get_session_state_slot(self, slot_name, *, session_id=None, default=None):
        session = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        return session.state_slots.get(slot_name, default)

    def set_session_state_slot(self, slot_name, value, *, session_id=None, emit_scope=""):
        session = (
            self._sessions[session_id]
            if session_id is not None
            else self.get_active_workspace_session()
        )
        session.state_slots[slot_name] = value

    def emit_state_change(self, _scope):
        pass


def test_dispatcher_history_isolated_per_session():
    sessions = {
        "a": _FakeSession("a"),
        "b": _FakeSession("b"),
    }
    store = _FakeStore(sessions, "a")
    dispatcher = Dispatcher(store)

    dispatcher.bind_history_for_session("a")
    dispatcher._action_history.append(SetDebugModeEnabledAction(True))
    assert len(sessions["a"].state_slots["action_history"]) == 1

    dispatcher.bind_history_for_session("b")
    assert dispatcher.get_action_history() == []

    dispatcher._action_history.append(SetDebugModeEnabledAction(False))
    assert len(sessions["b"].state_slots["action_history"]) == 1
    assert len(sessions["a"].state_slots["action_history"]) == 1

    dispatcher.bind_history_for_session("a")
    assert len(dispatcher.get_action_history()) == 1
    assert dispatcher.get_action_history()[0].enabled is True
