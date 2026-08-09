"""multi_compare's own per-session state-slot isolation on session switch."""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtGui import QColor

from tabs.multi_compare.models import DEFAULT_DIVIDER_COLOR_RGBA
from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab
from tabs.multi_compare.widget import MultiCompareWidget


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
