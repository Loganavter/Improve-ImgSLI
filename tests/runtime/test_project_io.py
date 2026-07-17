"""Project file round-trip and workspace replace helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from services.io.project_io import (
    PROJECT_FORMAT,
    PROJECT_VERSION,
    build_project_data,
    clear_workspace_sessions,
    load_project_data,
)


class _FakeSession:
    def __init__(self, session_id: str, session_type: str, title: str = ""):
        self.id = session_id
        self.session_type = session_type
        self.title = title or session_type
        self.state_slots: dict = {}
        self.document = None


class _FakeStore:
    def __init__(self, sessions: list[_FakeSession], active_id: str):
        self._sessions = {s.id: s for s in sessions}
        self.workspace = SimpleNamespace(active_session_id=active_id)

    def list_workspace_sessions(self):
        return tuple(self._sessions.values())

    def get_active_workspace_session(self):
        return self._sessions.get(self.workspace.active_session_id)

    def get_workspace_session(self, session_id: str):
        return self._sessions.get(session_id)


class _FakeWorkspaceActions:
    def __init__(self, store: _FakeStore):
        self.store = store
        self.created: list[tuple[str, bool]] = []
        self.closed: list[str] = []
        self.switched: list[str] = []
        self._counter = 0

    def create_workspace_session(
        self, session_type: str, *, activate: bool = True, title: str | None = None
    ):
        self._counter += 1
        session_id = f"s{self._counter}"
        session = _FakeSession(session_id, session_type, title or session_type)
        self.store._sessions[session_id] = session
        self.created.append((session_type, activate))
        if activate:
            self.store.workspace.active_session_id = session_id
        return session

    def close_workspace_session(self, session_id: str) -> bool:
        if len(self.store._sessions) <= 1:
            return False
        self.closed.append(session_id)
        self.store._sessions.pop(session_id, None)
        if self.store.workspace.active_session_id == session_id:
            self.store.workspace.active_session_id = next(iter(self.store._sessions))
        return True

    def switch_workspace_session(self, session_id: str) -> bool:
        if session_id not in self.store._sessions:
            return False
        self.switched.append(session_id)
        self.store.workspace.active_session_id = session_id
        return True


class _FakeTabRegistry:
    def __init__(self):
        self.serialized: list[tuple[str, str]] = []
        self.deserialized: list[tuple[str, str, dict]] = []
        self.rehydrated: list[tuple[str, str]] = []
        self._snapshots: dict[tuple[str, str], dict] = {}

    def serialize_session(self, session_type: str, session_id: str):
        self.serialized.append((session_type, session_id))
        if session_type == INITIAL_WORKSPACE_SESSION_TYPE:
            return None
        key = (session_type, session_id)
        if key not in self._snapshots:
            return None
        return dict(self._snapshots[key])

    def deserialize_session(self, session_type: str, session_id: str, data: dict):
        self.deserialized.append((session_type, session_id, dict(data)))

    def rehydrate_session(self, session_type: str, session_id: str):
        self.rehydrated.append((session_type, session_id))

    def duplicate_session(self, session_type: str, source_session_id: str):
        return self.serialize_session(session_type, source_session_id)


def test_build_project_data_skips_session_picker():
    picker = _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)
    ic = _FakeSession("ic1", "image_compare")
    store = _FakeStore([picker, ic], "ic1")
    registry = _FakeTabRegistry()
    registry._snapshots[("image_compare", "ic1")] = {"version": 1}

    project = build_project_data(store, registry)

    assert project["format"] == PROJECT_FORMAT
    assert project["version"] == PROJECT_VERSION
    assert len(project["sessions"]) == 1
    assert project["sessions"][0]["session_type"] == "image_compare"
    assert project["active_session_index"] == 0
    assert registry.serialized == [
        (INITIAL_WORKSPACE_SESSION_TYPE, "p1"),
        ("image_compare", "ic1"),
    ]


def test_load_project_data_round_trip_and_rehydrate():
    store = _FakeStore([_FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)], "p1")
    actions = _FakeWorkspaceActions(store)
    registry = _FakeTabRegistry()

    project = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "active_session_index": 1,
        "sessions": [
            {"session_type": "image_compare", "title": "A", "data": {"n": 1}},
            {"session_type": "multi_compare", "title": "B", "data": {"n": 2}},
        ],
    }

    created = load_project_data(project, actions, store, registry)

    assert len(created) == 2
    assert actions.created == [
        ("image_compare", False),
        ("multi_compare", False),
    ]
    assert len(registry.deserialized) == 2
    assert registry.rehydrated == [
        ("image_compare", created[0].id),
        ("multi_compare", created[1].id),
    ]
    assert actions.switched == [created[1].id]
    assert store.workspace.active_session_id == created[1].id


def test_load_project_data_replace_workspace_clears_existing():
    store = _FakeStore(
        [
            _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE),
            _FakeSession("old", "image_compare"),
        ],
        "old",
    )
    actions = _FakeWorkspaceActions(store)
    registry = _FakeTabRegistry()

    project = {
        "format": PROJECT_FORMAT,
        "version": PROJECT_VERSION,
        "active_session_index": 0,
        "sessions": [
            {"session_type": "image_compare", "title": "Fresh", "data": {}},
        ],
    }

    load_project_data(
        project, actions, store, registry, replace_workspace=True
    )

    assert "old" in actions.closed
    remaining_types = {s.session_type for s in store.list_workspace_sessions()}
    assert INITIAL_WORKSPACE_SESSION_TYPE in remaining_types
    assert len(registry.deserialized) == 1


def test_clear_workspace_sessions_keeps_picker():
    store = _FakeStore(
        [
            _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE),
            _FakeSession("ic1", "image_compare"),
            _FakeSession("mc1", "multi_compare"),
        ],
        "ic1",
    )
    actions = _FakeWorkspaceActions(store)

    keeper = clear_workspace_sessions(actions, store, keep_one_picker=True)

    assert keeper == "p1"
    assert list(store._sessions.keys()) == ["p1"]
    assert store.workspace.active_session_id == "p1"


def test_project_version_newer_than_supported_raises():
    store = _FakeStore([_FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)], "p1")
    actions = _FakeWorkspaceActions(store)
    registry = _FakeTabRegistry()

    with pytest.raises(ValueError, match="newer than supported"):
        load_project_data(
            {
                "format": PROJECT_FORMAT,
                "version": PROJECT_VERSION + 1,
                "sessions": [],
            },
            actions,
            store,
            registry,
        )


def test_tab_returning_none_omitted_from_save():
    store = _FakeStore([_FakeSession("x", "unknown_tab")], "x")
    registry = _FakeTabRegistry()

    project = build_project_data(store, registry)

    assert project["sessions"] == []
