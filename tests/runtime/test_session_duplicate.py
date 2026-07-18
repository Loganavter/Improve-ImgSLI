"""duplicate_workspace_session API and independent document copies."""

from __future__ import annotations

import copy
from types import SimpleNamespace

from core.main_controller_parts.sessions import WorkspaceSessionActions
from tabs.contract import TabContext
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.tab import ImageCompareTab


class _FakeSessionManager:
    def __init__(self, store: _FakeStore):
        self._store = store
        self._sessions = {}
        self._active = None
        self._counter = 0

    def get_active_session(self):
        return self._sessions.get(self._active)

    def get_session(self, session_id: str):
        return self._sessions.get(session_id)

    def create_session(self, session_type, *, activate=True, title=None, metadata=None):
        self._counter += 1
        sid = f"dup{self._counter}"
        session = SimpleNamespace(
            id=sid,
            session_type=session_type,
            title=title or session_type,
            document=DocumentModel(),
            state_slots={},
        )
        self._sessions[sid] = session
        self._store._sessions[sid] = session
        if activate or self._active is None:
            self._active = sid
            self._store.workspace.active_session_id = sid
        return session

    def switch_to_session(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        self._active = session_id
        return True

    def get_session_blueprint(self, session_type: str):
        return SimpleNamespace(session_type=session_type)


class _FakeStore:
    def __init__(self, sessions: dict[str, SimpleNamespace]):
        self._sessions = sessions
        self.workspace = SimpleNamespace(
            active_session_id=next(iter(sessions)) if sessions else None
        )

    def get_workspace_session(self, session_id: str):
        return self._sessions.get(session_id)

    def set_session_state_slot(self, slot_name, value, *, session_id=None, emit_scope=None):
        session = self._sessions[session_id]
        session.state_slots[slot_name] = value


class _FakeTabRegistry:
    def __init__(self, tab: ImageCompareTab, store: _FakeStore):
        self._tab = tab
        self._store = store
        self._context = TabContext(store=store)
        self.deserialized: list[tuple[str, str, dict]] = []
        self.rehydrated: list[str] = []

    def duplicate_session(self, session_type, source_session_id):
        return self._tab.duplicate_session(source_session_id, self._context)

    def deserialize_session(self, session_type, session_id, data):
        self.deserialized.append((session_type, session_id, copy.deepcopy(data)))
        self._tab.deserialize_session(session_id, data, self._context)

    def rehydrate_session(self, session_type, session_id):
        self.rehydrated.append(session_id)


class _FakeController:
    def __init__(self, store: _FakeStore):
        self.session_manager = _FakeSessionManager(store)
        self.event_bus = SimpleNamespace(emit=lambda e: None)


def _snapshot() -> dict:
    return {
        "version": 1,
        "image_list1": [{"path": "/a.png", "display_name": "a", "rating": 0}],
        "image_list2": [{"path": "/b.png", "display_name": "b", "rating": 1}],
        "current_index1": 0,
        "current_index2": 0,
        "image1_path": "/a.png",
        "image2_path": "/b.png",
        "show_file_names": True,
        "edit_name_1": "left",
        "edit_name_2": "right",
    }


def test_duplicate_workspace_session_clones_independently():
    store = _FakeStore({})
    sm = _FakeSessionManager(store)
    source = sm.create_session("image_compare", activate=True, title="Original")
    tab = ImageCompareTab()
    registry = _FakeTabRegistry(tab, store)

    tab.deserialize_session(source.id, _snapshot(), TabContext(store=store))

    controller = _FakeController(store)
    controller.session_manager = sm
    actions = WorkspaceSessionActions(controller)

    clone = actions.duplicate_workspace_session(
        source.id, activate=True, tab_registry=registry
    )

    assert clone.id != source.id
    assert len(registry.deserialized) == 1
    _, new_id, data = registry.deserialized[0]
    assert new_id == clone.id
    assert data["image_list1"][0]["path"] == "/a.png"
    assert registry.rehydrated == [clone.id]
    assert sm.get_active_session().id == clone.id

    source_doc = store.get_workspace_session(source.id).document
    clone_doc = store.get_workspace_session(clone.id).document

    assert source_doc is not clone_doc
    assert source_doc.image_list1 is not clone_doc.image_list1
    assert source_doc.image_list1[0] is not clone_doc.image_list1[0]
    assert source_doc.image_list1[0].path == "/a.png"
    assert clone_doc.image_list1[0].path == "/a.png"

    clone_doc.image_list1[0].path = "/mutated-on-clone"
    assert source_doc.image_list1[0].path == "/a.png"
    assert clone_doc.image_list2[0].path == "/b.png"


def test_duplicate_session_returns_independent_snapshot_dict():
    tab = ImageCompareTab()
    session = SimpleNamespace(
        id="src",
        session_type="image_compare",
        document=DocumentModel(
            image_list1=[ImageItem(path="/a.png", display_name="a")],
            image_list2=[],
            current_index1=0,
            image1_path="/a.png",
        ),
        state_slots={},
    )
    store = _FakeStore({"src": session})
    context = TabContext(store=store)

    snapshot = tab.duplicate_session("src", context)
    assert snapshot is not None
    assert snapshot["image_list1"][0]["path"] == "/a.png"

    snapshot["image_list1"][0]["path"] = "/mutated-snapshot"
    again = tab.duplicate_session("src", context)
    assert again["image_list1"][0]["path"] == "/a.png"
