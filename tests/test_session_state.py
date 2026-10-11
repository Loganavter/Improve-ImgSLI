"""SessionState facade: slot + QSettings last-used + project I/O (fake store)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.state_management.slot_reducers import iter_state_slot_reducers
from tabs.use_cases.session_state import SessionState

NS = "test_session_chrome"
FIELDS = {"view_list": (bool, False), "judgment_domain": (str, "algorithms")}


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


class _Store:
    def __init__(self):
        self.slots: dict[str, dict] = {}
        self.active: str | None = None
        self.dispatches = 0

    def add(self, sid):
        self.slots[sid] = {}
        return sid

    def get_active_workspace_session(self):
        return SimpleNamespace(id=self.active) if self.active else None

    def get_session_state_slot(self, name, session_id=None, default=None):
        return self.slots.get(session_id or self.active, {}).get(name, default)

    def set_session_state_slot(self, name, value, session_id=None, emit_scope=None):
        self.slots[session_id or self.active][name] = value

    def get_dispatcher(self):
        store = self

        class _D:
            def dispatch(self, action, scope="viewport", session_id=None):
                store.dispatches += 1
                target = session_id or store.active
                reducers = dict(iter_state_slot_reducers())
                cur = store.get_session_state_slot(action.namespace, session_id=target)
                new = reducers[action.namespace](cur, action)
                if new is not cur:
                    store.set_session_state_slot(action.namespace, new, session_id=target)

        return _D()


class _Ctx:
    def __init__(self, store):
        self.store = store


def _facade(apply_log: list, collect=None):
    return SessionState.bind(
        SimpleNamespace(),
        namespace=NS,
        fields=FIELDS,
        apply=lambda d: apply_log.append(dict(d)),
        collect=collect,
    )


def _qs_value(mem):
    raw = mem.get(f"{NS}/chrome")
    return json.loads(raw) if raw else None


def test_set_writes_slot_and_qsettings(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    log: list = []
    state = _facade(log)
    state.apply_from_slot(_Ctx(store), s1)

    state.set("view_list", True)
    state.set("judgment_domain", "ai")

    assert store.slots[s1][NS] == {"view_list": True, "judgment_domain": "ai"}
    assert _qs_value(_memory_qsettings) == {"view_list": True, "judgment_domain": "ai"}
    assert state.as_dict() == {"view_list": True, "judgment_domain": "ai"}


def test_set_is_change_guarded(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    state.set("view_list", False)  # already False
    assert store.dispatches == 0
    state.set("view_list", True)
    assert store.dispatches == 1
    state.set("view_list", True)
    assert store.dispatches == 1


def test_seed_new_session_inherits_last_used(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    state.set("view_list", True)

    s2 = store.add("S2")
    log: list = []
    state2 = _facade(log)
    state2.seed_slot(_Ctx(store), s2)

    assert store.slots[s2][NS] == {"view_list": True, "judgment_domain": "algorithms"}
    assert log == []  # not active/bound -> no apply


def test_seed_applies_when_session_is_active(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    state.set("judgment_domain", "ai")

    s2 = store.add("S2")
    store.active = s2
    log: list = []
    _facade(log).seed_slot(_Ctx(store), s2)
    assert log == [{"view_list": False, "judgment_domain": "ai"}]


def test_apply_from_slot_is_slot_first_then_qsettings(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    state.set("view_list", True)  # QSettings now True

    s2 = store.add("S2")
    store.slots[s2][NS] = {"view_list": False, "judgment_domain": "algorithms"}
    log: list = []
    f = _facade(log)
    f.apply_from_slot(_Ctx(store), s2)
    assert log[-1] == {"view_list": False, "judgment_domain": "algorithms"}  # slot wins

    s3 = store.add("S3")  # empty slot -> QSettings fallback
    f.apply_from_slot(_Ctx(store), s3)
    assert log[-1] == {"view_list": True, "judgment_domain": "algorithms"}


def test_serialize_deserialize_roundtrip(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    state.set("view_list", True)
    state.set("judgment_domain", "ai")

    data = state.serialize(_Ctx(store), s1)
    assert data == {"view_list": True, "judgment_domain": "ai"}

    other = _facade([])
    other.deserialize(data)
    assert other.serialize() == data


def test_deserialize_writes_target_slot_and_ignores_unknown_keys():
    store = _Store()
    s1 = store.add("S1")
    state = _facade([])
    state.deserialize({"view_list": True, "bogus": 42}, _Ctx(store), s1)
    assert store.slots[s1][NS] == {"view_list": True, "judgment_domain": "algorithms"}
    assert "bogus" not in store.slots[s1][NS]


def test_wrong_type_coerces_to_default():
    state = _facade([])
    state.deserialize({"view_list": "yes", "judgment_domain": 7})
    assert state.as_dict() == {"view_list": False, "judgment_domain": "algorithms"}
    state.deserialize({"view_list": 1})
    assert state.get("view_list") is False  # int is not a bool
    state.set("view_list", "nope")
    assert state.get("view_list") is False


def test_serialize_reads_target_session_slot_not_bound_copy():
    store = _Store()
    s1 = store.add("S1")
    s2 = store.add("S2")
    store.slots[s2][NS] = {"view_list": True, "judgment_domain": "ai"}
    state = _facade([])
    state.apply_from_slot(_Ctx(store), s1)
    assert state.serialize(_Ctx(store), s2) == {"view_list": True, "judgment_domain": "ai"}


def test_unknown_field_access_raises():
    state = _facade([])
    with pytest.raises(KeyError):
        state.get("nope")
    with pytest.raises(KeyError):
        state.set("nope", 1)
