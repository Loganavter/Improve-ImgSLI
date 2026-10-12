"""Gallery toolbar chrome survives via the SessionState facade (3 cases).

Drives the real ``ImageGalleryTab`` delegates over a fake store whose
dispatcher reduces through the registered slot reducers, and a fake widget
that records what the facade applies.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.state_management.slot_reducers import iter_state_slot_reducers
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state.models import fresh_gallery_slot_state
from tabs.image_gallery.tab import ImageGalleryTab
from tabs.image_gallery.widget import ImageGalleryWidget


@pytest.fixture(autouse=True)
def _memory_qsettings(monkeypatch):
    """In-memory QSettings: never touch the real user config."""
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
    yield mem


class _Session(SimpleNamespace):
    pass


class _Store:
    def __init__(self):
        self.sessions: dict[str, _Session] = {}
        self.active: str | None = None

    def add(self, sid: str):
        self.sessions[sid] = _Session(
            id=sid,
            session_type="image_gallery",
            state_slots={GALLERY_SLOT_NAME: fresh_gallery_slot_state()},
        )
        return sid

    def get_workspace_session(self, sid):
        return self.sessions.get(sid)

    def get_active_workspace_session(self):
        return self.sessions.get(self.active) if self.active else None

    def get_session_state_slot(self, name, session_id=None, default=None):
        sess = self.sessions.get(session_id or self.active)
        return default if sess is None else sess.state_slots.get(name, default)

    def set_session_state_slot(self, name, value, session_id=None, emit_scope=None):
        self.sessions[session_id or self.active].state_slots[name] = value

    def get_dispatcher(self):
        return _Dispatcher(self)


class _Dispatcher:
    def __init__(self, store: _Store):
        self._store = store

    def dispatch(self, action, scope="viewport", session_id=None):
        target = session_id or self._store.active
        for name, reducer in iter_state_slot_reducers():
            if name != action.namespace:
                continue
            cur = self._store.get_session_state_slot(name, session_id=target)
            new = reducer(cur, action)
            if new is not cur:
                self._store.set_session_state_slot(name, new, session_id=target)


class _Widget:
    """Records facade applies and reuses the real toggle persistence."""

    def __init__(self):
        self.view_list = False
        self.domain = "algorithms"
        self._view_mode = False
        self._judgment_domain = "algorithms"
        self._session_state = None

    def attach_session_state(self, state):
        self._session_state = state

    def apply_view_prefs(self, *, view_list, judgment_domain):
        self._view_mode = self.view_list = bool(view_list)
        self._judgment_domain = self.domain = str(judgment_domain)

    def toggle(self, view_list, domain):
        self._view_mode = self.view_list = view_list
        self._judgment_domain = self.domain = domain
        ImageGalleryWidget._persist_view_prefs(self)


def _tab(store: _Store, widget: _Widget) -> ImageGalleryTab:
    tab = ImageGalleryTab()
    tab._widget = widget
    tab._controller = SimpleNamespace(clear_to_empty=lambda: None)
    widget.attach_session_state(tab._session_state)
    return tab


def _ctx(store):
    return SimpleNamespace(store=store)


def _activate(store, tab, sid):
    store.active = sid
    tab.on_active_session_changed(sid, _ctx(store))


def test_switch_away_and_back_keeps_switches():
    store = _Store()
    a = store.add("A")
    b = store.add("B")
    widget = _Widget()
    tab = _tab(store, widget)
    tab.on_session_created(a, _ctx(store))
    _activate(store, tab, a)
    widget.toggle(True, "ai")

    tab.on_session_created(b, _ctx(store))
    _activate(store, tab, b)
    assert (widget.view_list, widget.domain) == (True, "ai")  # inherited
    widget.toggle(False, "algorithms")

    _activate(store, tab, a)
    assert (widget.view_list, widget.domain) == (True, "ai")
    _activate(store, tab, b)
    assert (widget.view_list, widget.domain) == (False, "algorithms")


def test_new_session_inherits_last_used():
    store = _Store()
    a = store.add("A")
    widget = _Widget()
    tab = _tab(store, widget)
    tab.on_session_created(a, _ctx(store))
    _activate(store, tab, a)
    widget.toggle(True, "ai")

    fresh = store.add("NEW")
    tab.on_session_created(fresh, _ctx(store))
    _activate(store, tab, fresh)
    assert (widget.view_list, widget.domain) == (True, "ai")


def test_serialize_deserialize_roundtrip_restores_switches():
    store = _Store()
    a = store.add("A")
    widget = _Widget()
    tab = _tab(store, widget)
    tab.on_session_created(a, _ctx(store))
    _activate(store, tab, a)
    widget.toggle(True, "ai")

    snapshot = tab.serialize_session(a, _ctx(store))
    assert snapshot["view_list"] is True
    assert snapshot["judgment_domain"] == "ai"

    restored = store.add("R")
    tab2 = _tab(store, _Widget())
    tab2.on_session_created(restored, _ctx(store))
    tab2.deserialize_session(restored, snapshot, _ctx(store))
    _activate(store, tab2, restored)
    assert (tab2._widget.view_list, tab2._widget.domain) == (True, "ai")
