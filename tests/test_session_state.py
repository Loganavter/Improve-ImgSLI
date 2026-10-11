"""SessionState facade: slot + QSettings last-used + project I/O (fake store)."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
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


STRUCT_FIELDS = {"tags": (list, ["a"]), "opts": (dict, {"x": 1})}


def test_structured_fields_round_trip_qsettings_and_slot(_memory_qsettings):
    store = _Store()
    s1 = store.add("S1")
    state = SessionState.bind(SimpleNamespace(), namespace=NS, fields=STRUCT_FIELDS, apply=lambda d: None)
    state.apply_from_slot(_Ctx(store), s1)
    state.set("tags", ["b", "c"])
    state.set("opts", {"x": 2, "y": [3]})

    assert store.slots[s1][NS] == {"tags": ["b", "c"], "opts": {"x": 2, "y": [3]}}
    assert _qs_value(_memory_qsettings) == {"tags": ["b", "c"], "opts": {"x": 2, "y": [3]}}

    log: list = []
    fresh = SessionState.bind(SimpleNamespace(), namespace=NS, fields=STRUCT_FIELDS, apply=log.append)
    s2 = store.add("S2")
    fresh.apply_from_slot(_Ctx(store), s2)  # empty slot -> QSettings fallback
    assert log[-1] == {"tags": ["b", "c"], "opts": {"x": 2, "y": [3]}}


def test_structured_wrong_type_coerces_to_copied_default():
    state = SessionState.bind(SimpleNamespace(), namespace=NS, fields=STRUCT_FIELDS, apply=lambda d: None)
    state.deserialize({"tags": "nope", "opts": None})
    assert state.as_dict() == {"tags": ["a"], "opts": {"x": 1}}
    state.get("tags").append("mutated")  # returned copy must not alias the mirror
    assert state.get("tags") == ["a"]
    other = SessionState.bind(SimpleNamespace(), namespace=NS, fields=STRUCT_FIELDS, apply=lambda d: None)
    assert other.get("tags") == ["a"]  # default never shared between instances


TYPED_SLOT = "test_typed_box"
TYPED_FIELDS = {"count": (int, 0), "meta": (dict, {"k": 1})}


@dataclass(frozen=True)
class _Box:
    value: int = 0
    meta: tuple = ()


def _box_merge(state, values):
    changes = {}
    if "count" in values:
        changes["value"] = int(values["count"])
    if "meta" in values:
        changes["meta"] = tuple(sorted(values["meta"].items()))
    return replace(state, **changes) if changes else state


def _box_extract(state):
    return {"count": state.value, "meta": dict(state.meta) or {"k": 1}}


@pytest.fixture
def typed_slot_reducer():
    from core.state_management.session_state_slots import reduce_typed_session_slot
    from core.state_management.slot_reducers import (
        register_state_slot_reducer,
        unregister_state_slot_reducer,
    )

    register_state_slot_reducer(
        TYPED_SLOT,
        lambda state, action: reduce_typed_session_slot(TYPED_SLOT, _Box() if state is None else state, action),
    )
    yield
    unregister_state_slot_reducer(TYPED_SLOT)


def _typed_facade(log: list):
    return SessionState.bind(
        SimpleNamespace(),
        namespace=NS,
        fields=TYPED_FIELDS,
        apply=lambda d: log.append(dict(d)),
        slot=TYPED_SLOT,
        merge=_box_merge,
        extract=_box_extract,
        last_used_key=f"{NS}/typed",
    )


def test_typed_slot_reads_and_writes_through_extract_merge(_memory_qsettings, typed_slot_reducer):
    store = _Store()
    s1 = store.add("S1")
    store.slots[s1][TYPED_SLOT] = _Box(value=5)
    log: list = []
    facade = _typed_facade(log)
    facade.apply_from_slot(_Ctx(store), s1)
    assert log[-1] == {"count": 5, "meta": {"k": 1}}

    facade.set("count", 7)
    assert store.slots[s1][TYPED_SLOT] == _Box(value=7)
    assert facade.serialize(_Ctx(store), s1) == {"count": 7, "meta": {"k": 1}}
    assert _memory_qsettings[f"{NS}/typed"] is not None


def test_typed_slot_deserialize_and_remember_roundtrip(_memory_qsettings, typed_slot_reducer):
    store = _Store()
    s1 = store.add("S1")
    store.slots[s1][TYPED_SLOT] = _Box()
    facade = _typed_facade([])
    facade.deserialize({"count": 3, "meta": {"z": 9}}, _Ctx(store), s1)
    assert store.slots[s1][TYPED_SLOT] == _Box(value=3, meta=(("z", 9),))

    facade.remember({"count": 4})  # no slot write, mirror + last-used only
    assert store.slots[s1][TYPED_SLOT] == _Box(value=3, meta=(("z", 9),))
    assert facade.get("count") == 4
    assert json.loads(_memory_qsettings[f"{NS}/typed"])["count"] == 4


def test_typed_bind_requires_merge_and_extract_together():
    with pytest.raises(TypeError):
        SessionState.bind(SimpleNamespace(), namespace=NS, fields=TYPED_FIELDS, apply=lambda d: None, slot=TYPED_SLOT)
    with pytest.raises(TypeError):
        SessionState.bind(SimpleNamespace(), namespace=NS, fields=TYPED_FIELDS, apply=lambda d: None, merge=_box_merge)
