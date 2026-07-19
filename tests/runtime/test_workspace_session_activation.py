"""Workspace session activation notifies tabs when session_id changes."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QColor

from core.events import WorkspaceSessionActivatedEvent
from tabs.contract import TabContext, TabContract
from tabs.multi_compare.models import DEFAULT_DIVIDER_COLOR_RGBA
from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab
from tabs.multi_compare.widget import MultiCompareWidget
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


class _FakeWorkspaceStore:
    def __init__(self):
        self.sessions = {
            "a": SimpleNamespace(
                id="a",
                session_type="multi_compare",
                state_slots={},
            ),
            "b": SimpleNamespace(
                id="b",
                session_type="multi_compare",
                state_slots={},
            ),
        }
        self.active_session_id = "a"
        self.workspace = SimpleNamespace(active_session_id="a")

    def list_workspace_sessions(self):
        return tuple(self.sessions.values())

    def get_active_workspace_session(self):
        return self.sessions[self.active_session_id]

    def get_workspace_session(self, session_id: str):
        return self.sessions.get(session_id)

    def ensure_session_state_slot(
        self,
        slot_name,
        *,
        session_id=None,
        factory=None,
        default=None,
        emit_change=False,
    ):
        from tabs.multi_compare.tab import _fresh_default_state

        session = self.sessions[session_id or self.active_session_id]
        if slot_name not in session.state_slots:
            session.state_slots[slot_name] = (
                factory() if factory else (_fresh_default_state() if default is None else default)
            )
        return session.state_slots[slot_name]

    def set_session_state_slot(
        self,
        slot_name,
        value,
        *,
        session_id=None,
        emit_scope=None,
    ):
        session = self.sessions[session_id or self.active_session_id]
        session.state_slots[slot_name] = value
        return value

    def get_session_state_slot(self, slot_name, *, session_id=None, default=None):
        session = self.sessions[session_id or self.active_session_id]
        return session.state_slots.get(slot_name, default)


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


def test_switch_same_type_snapshots_do_not_cross_contaminate(qapp):
    """Switch A→B→A→B: each session slot keeps its own divider color."""
    widget = MultiCompareWidget()
    tab = MultiCompareTab()
    store = _FakeWorkspaceStore()
    context = SimpleNamespace(store=store)

    tab._widget = widget
    tab._store_context = store
    widget.store.subscribe(tab._on_widget_state_changed)

    tab.on_active_session_changed("a", context)
    widget.apply_divider_color(QColor(10, 20, 30, 40))
    assert store.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    store.active_session_id = "b"
    store.workspace.active_session_id = "b"
    tab.on_active_session_changed("b", context)
    assert (
        store.sessions["b"].state_slots[_STATE_SLOT].divider_settings.color_rgba
        == DEFAULT_DIVIDER_COLOR_RGBA
    )
    assert store.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    widget.apply_divider_color(QColor(1, 2, 3, 4))
    assert store.sessions["b"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        1,
        2,
        3,
        4,
    )
    assert store.sessions["a"].state_slots[_STATE_SLOT].divider_settings.color_rgba == (
        10,
        20,
        30,
        40,
    )

    store.active_session_id = "a"
    store.workspace.active_session_id = "a"
    tab.on_active_session_changed("a", context)
    assert widget.state.divider_settings.color_rgba == (10, 20, 30, 40)

    store.active_session_id = "b"
    store.workspace.active_session_id = "b"
    tab.on_active_session_changed("b", context)
    assert widget.state.divider_settings.color_rgba == (1, 2, 3, 4)
