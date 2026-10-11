"""Divider/label chrome survives switch-away/back, new sessions, and project I/O.

Drives the real facade-bound hooks (``on_session_created``,
``on_active_session_changed``, ``on_widget_state_changed``,
``serialize_session``/``deserialize_session``) against a small store whose
dispatcher runs the real MC slot reducer. QSettings is in-memory.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from tabs.multi_compare.bootstrap_reducers import _reduce_multi_compare_state
from tabs.multi_compare.models import MultiCompareDividerSettings, MultiCompareState
from tabs.multi_compare.tab import MultiCompareTab
from tabs.multi_compare.use_cases import persistence
from tabs.multi_compare.use_cases.persistence import _STATE_SLOT

DEFAULT_COLOR = (255, 255, 255, 255)
EDITED_COLOR = (9, 8, 7, 6)


@pytest.fixture(autouse=True)
def _memory_qsettings(monkeypatch):
    mem: dict = {}

    class _FakeQSettings:
        def __init__(self, *_args):
            pass

        def value(self, key, default=None):
            return mem.get(key, default)

        def setValue(self, key, value):
            mem[key] = value

        def sync(self):
            pass

    from tabs.use_cases import session_state as _mod

    monkeypatch.setattr(_mod, "QSettings", _FakeQSettings)
    return mem


class _Store:
    def __init__(self):
        self.sessions: dict[str, SimpleNamespace] = {}
        self.active: str | None = None

    def add(self, sid: str) -> str:
        self.sessions[sid] = SimpleNamespace(id=sid, session_type="multi_compare", state_slots={})
        return sid

    def get_workspace_session(self, sid):
        return self.sessions.get(sid)

    def list_workspace_sessions(self):
        return tuple(self.sessions.values())

    def get_active_workspace_session(self):
        return self.sessions.get(self.active) if self.active else None

    def ensure_session_state_slot(self, name, *, session_id=None, factory=None, default=None, emit_change=False):
        session = self.sessions[session_id or self.active]
        if name not in session.state_slots:
            session.state_slots[name] = factory() if factory else default
        return session.state_slots[name]

    def get_session_state_slot(self, name, *, session_id=None, default=None):
        session = self.sessions.get(session_id or self.active)
        if session is None:
            return default
        return session.state_slots.get(name, default)

    def set_session_state_slot(self, name, value, *, session_id=None, emit_scope=None):
        self.sessions[session_id or self.active].state_slots[name] = value
        return value

    def get_dispatcher(self):
        return self

    def dispatch(self, action, scope="viewport", session_id=None):
        target = session_id or self.active
        cur = self.get_session_state_slot(_STATE_SLOT, session_id=target)
        new = _reduce_multi_compare_state(cur, action)
        if new is not cur:
            self.set_session_state_slot(_STATE_SLOT, new, session_id=target)


def _ctx(store):
    return SimpleNamespace(store=store)


def _divider_color(store, sid):
    return store.get_session_state_slot(_STATE_SLOT, session_id=sid).divider_settings.color_rgba


def _edit_divider(store, tab, sid, color):
    """User edit: MC dispatch changed the slot, then the widget-state hook fires."""
    state = store.get_session_state_slot(_STATE_SLOT, session_id=sid)
    new = replace(state, divider_settings=MultiCompareDividerSettings(color_rgba=color))
    store.set_session_state_slot(_STATE_SLOT, new, session_id=sid)
    persistence.on_widget_state_changed(
        tab, SimpleNamespace(type="multi_compare/set_divider_settings"), new
    )


def test_chrome_survives_switch_away_and_back(qapp):
    store = _Store()
    s1 = store.add("mc1")
    s2 = store.add("mc2")
    store.active = s1
    ctx = _ctx(store)
    tab = MultiCompareTab()
    tab.on_session_created(s1, ctx)
    tab.on_active_session_changed(s1, ctx)
    _edit_divider(store, tab, s1, EDITED_COLOR)
    store.sessions[s2].state_slots[_STATE_SLOT] = MultiCompareState()

    tab.on_active_session_changed(s2, ctx)
    assert _divider_color(store, s2) == DEFAULT_COLOR
    assert tab._session_state.get("divider")["color_rgba"] == list(DEFAULT_COLOR)

    tab.on_active_session_changed(s1, ctx)
    assert _divider_color(store, s1) == EDITED_COLOR
    assert tab._session_state.get("divider")["color_rgba"] == list(EDITED_COLOR)


def test_new_session_seeds_from_last_used(qapp):
    store = _Store()
    s1 = store.add("mc1")
    store.active = s1
    ctx = _ctx(store)
    tab = MultiCompareTab()
    tab.on_session_created(s1, ctx)
    tab.on_active_session_changed(s1, ctx)
    _edit_divider(store, tab, s1, EDITED_COLOR)

    s2 = store.add("mc2")
    store.active = s2
    tab.on_session_created(s2, ctx)
    assert _divider_color(store, s2) == EDITED_COLOR
    assert _divider_color(store, s1) == EDITED_COLOR  # seed never rewrites the source


def test_project_serialize_deserialize_keeps_chrome(qapp):
    store = _Store()
    s1 = store.add("mc1")
    store.active = s1
    ctx = _ctx(store)
    tab = MultiCompareTab()
    tab.on_session_created(s1, ctx)
    _edit_divider(store, tab, s1, EDITED_COLOR)

    data = persistence.serialize_session(tab, s1, ctx)
    assert data["divider_settings"]["color_rgba"] == list(EDITED_COLOR)
    assert "label_settings" in data

    s2 = store.add("mc2")
    persistence.deserialize_session(tab, s2, data, ctx)
    assert _divider_color(store, s2) == EDITED_COLOR


def test_chrome_merge_is_pure_and_partial():
    base = MultiCompareState()
    merged = persistence.chrome_merge(base, {"divider": persistence.chrome_extract(base)["divider"] | {"thickness": 9}})
    assert merged.divider_settings.thickness == 9
    assert merged.label_settings == base.label_settings
    assert persistence.chrome_merge(base, {}) is base
    assert base.divider_settings.thickness == 4
