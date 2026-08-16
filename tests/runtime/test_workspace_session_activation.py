"""Workspace session activation notifies tabs when session_id changes.

multi_compare's own per-session state-slot isolation is covered in
``src/tabs/multi_compare/tests/runtime/test_session_state_slot_isolation.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.events import WorkspaceSessionActivatedEvent
from tabs.contract import TabContext, TabContract
from tabs.registry import TabRegistry


class _RecordingTab(TabContract):
    session_type = "test_tab"
    display_name = "Test"

    def __init__(self):
        self.active_changed: list[str] = []

    def create_page(self, parent, context):
        from PySide6.QtWidgets import QWidget

        return QWidget(parent)

    def on_activated(self, context: TabContext) -> None:
        session = context.store.get_active_workspace_session()
        if session is not None:
            self.on_active_session_changed(session.id, context)

    def on_active_session_changed(self, session_id: str, context: TabContext) -> None:
        self.active_changed.append(session_id)


class _FakeStore:
    def __init__(self, sessions: dict[str, SimpleNamespace], active_id: str):
        self._sessions = sessions
        self._active_id = active_id

    def get_active_workspace_session(self):
        return self._sessions.get(self._active_id)


def test_notify_active_session_changed_same_type(qapp):
    TabRegistry._instance = None
    registry = TabRegistry()
    registry._tabs["test_tab"] = _RecordingTab()
    store = _FakeStore(
        {
            "a": SimpleNamespace(id="a", session_type="test_tab"),
            "b": SimpleNamespace(id="b", session_type="test_tab"),
        },
        "a",
    )
    registry._context = TabContext(store=store)
    registry._active_session_type = "test_tab"
    registry._active_session_id = "a"

    registry.notify_active_session_changed("b", "test_tab", "a")
    registry.notify_active_session_changed("a", "test_tab", "b")

    tab = registry._tabs["test_tab"]
    assert tab.active_changed == ["b", "a"]
    assert registry._active_session_id == "a"


def test_activated_event_carries_previous_session_id():
    event = WorkspaceSessionActivatedEvent(
        session_id="x",
        session_type="image_compare",
        previous_session_id="y",
    )
    assert event.previous_session_id == "y"