"""Project file round-trip and workspace replace helpers."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from core.store import INITIAL_WORKSPACE_SESSION_TYPE
from core.store_viewport import RenderConfig, ViewState, ViewportState
from services.io.project_io import (
    PROJECT_FORMAT,
    PROJECT_VERSION,
    build_project_data,
    clear_workspace_sessions,
    load_project_data,
    load_project_file,
    save_project_file,
)
from services.io.project_package import (
    embed_media,
    extract_media,
    is_zip_project,
    iter_session_media_paths,
    read_project_json_from_zip,
    rewrite_session_paths,
)
from tabs.image_compare.session_persistence import (
    restore_viewport_block,
    serialize_viewport_block,
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


def _write_png(path: Path, color=(20, 40, 60)) -> Path:
    Image.new("RGB", (8, 8), color=color).save(path)
    return path


def test_zip_project_embeds_media_and_rewrites_paths(tmp_path):
    img_a = _write_png(tmp_path / "a.png", color=(20, 40, 60))
    img_b = _write_png(tmp_path / "b.png", color=(200, 10, 5))
    # Same bytes as a.png → should dedupe to one media member
    img_a_copy = tmp_path / "a_copy.png"
    img_a_copy.write_bytes(img_a.read_bytes())

    picker = _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)
    ic = _FakeSession("ic1", "image_compare")
    store = _FakeStore([picker, ic], "ic1")
    registry = _FakeTabRegistry()
    registry._snapshots[("image_compare", "ic1")] = {
        "version": 2,
        "image_list1": [{"path": str(img_a), "display_name": "a", "rating": 0}],
        "image_list2": [{"path": str(img_b), "display_name": "b", "rating": 1}],
        "image1_path": str(img_a_copy),
        "image2_path": str(img_b),
        "current_index1": 0,
        "current_index2": 0,
        "show_file_names": True,
        "edit_name_1": "Left",
        "edit_name_2": "Right",
    }

    out = tmp_path / "demo.imgsli"
    missing = save_project_file(out, store, registry)

    assert missing == []
    assert is_zip_project(out)
    with zipfile.ZipFile(out, "r") as zf:
        names = zf.namelist()
        assert "project.json" in names
        media_members = [n for n in names if n.startswith("media/")]
        assert len(media_members) == 2  # a.png + b.png (deduped copy)

    data = read_project_json_from_zip(out)
    assert data["version"] == PROJECT_VERSION
    assert data["media"]
    session_data = data["sessions"][0]["data"]
    assert session_data["image_list1"][0]["path"].startswith("media/")
    assert session_data["image1_path"].startswith("media/")
    assert session_data["image_list1"][0]["path"] == session_data["image1_path"]


def test_load_zip_project_extracts_and_replaces(tmp_path, monkeypatch):
    monkeypatch.setenv("IMGSLI_PROJECT_CACHE", str(tmp_path / "proj-cache"))
    img = _write_png(tmp_path / "shot.png")
    picker = _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)
    ic = _FakeSession("ic1", "image_compare")
    old = _FakeSession("old", "image_compare")
    store = _FakeStore([picker, ic, old], "ic1")
    registry = _FakeTabRegistry()
    registry._snapshots[("image_compare", "ic1")] = {
        "version": 2,
        "image_list1": [{"path": str(img), "display_name": "shot", "rating": 0}],
        "image_list2": [],
        "image1_path": str(img),
        "image2_path": None,
        "current_index1": 0,
        "current_index2": -1,
    }

    project_path = tmp_path / "pack.imgsli"
    save_project_file(project_path, store, registry)

    # Simulate a dirty workspace, then open with replace.
    store2 = _FakeStore(
        [
            _FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE),
            _FakeSession("stale", "multi_compare"),
        ],
        "stale",
    )
    actions = _FakeWorkspaceActions(store2)
    registry2 = _FakeTabRegistry()

    created = load_project_file(
        project_path,
        actions,
        store2,
        registry2,
        replace_workspace=True,
    )

    assert "stale" in actions.closed
    assert len(created) == 1
    assert len(registry2.deserialized) == 1
    restored_path = registry2.deserialized[0][2]["image_list1"][0]["path"]
    assert Path(restored_path).is_file()
    assert restored_path != str(img)
    assert registry2.rehydrated == [("image_compare", created[0].id)]


def test_v1_plain_json_still_loads(tmp_path):
    project_path = tmp_path / "legacy.imgsli"
    project_path.write_text(
        json.dumps(
            {
                "format": "imgsli-project",  # legacy format id
                "version": 1,
                "active_session_index": 0,
                "sessions": [
                    {
                        "session_type": "image_compare",
                        "title": "Old",
                        "data": {"version": 1, "image_list1": []},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = _FakeStore([_FakeSession("p1", INITIAL_WORKSPACE_SESSION_TYPE)], "p1")
    actions = _FakeWorkspaceActions(store)
    registry = _FakeTabRegistry()

    created = load_project_file(
        project_path, actions, store, registry, replace_workspace=True
    )

    assert len(created) == 1
    assert registry.deserialized[0][2]["version"] == 1
    assert not is_zip_project(project_path)


def test_rewrite_and_embed_helpers(tmp_path):
    img = _write_png(tmp_path / "x.png")
    project = {
        "sessions": [
            {
                "session_type": "image_compare",
                "title": "T",
                "data": {
                    "image_list1": [{"path": str(img), "display_name": "x", "rating": 0}],
                    "slots": [{"id": "s1", "path": str(img), "label": "A"}],
                },
            }
        ]
    }
    paths = iter_session_media_paths(project)
    assert paths == [str(img), str(img)]
    mapping, catalog, missing = embed_media(paths)
    assert missing == []
    assert len(catalog) == 1
    rewritten = rewrite_session_paths(project, mapping)
    member = mapping[str(img)]
    assert rewritten["sessions"][0]["data"]["image_list1"][0]["path"] == member
    assert rewritten["sessions"][0]["data"]["slots"][0]["path"] == member

    # extract_media needs a zip — create one via save path helpers
    from services.io.project_package import write_project_zip

    zip_path = tmp_path / "m.imgsli"
    write_project_zip(zip_path, {"format": PROJECT_FORMAT, "version": 2}, mapping)
    cache = tmp_path / "cache"
    extracted = extract_media(zip_path, cache)
    assert member in extracted
    assert Path(extracted[member]).is_file()


def test_render_config_and_viewport_block_roundtrip():
    from tabs.image_compare.state.models import ImageSessionState
    from core.store_viewport import SessionData

    vp = ViewportState(
        render_config=RenderConfig(font_size_percent=140, jpeg_quality=88),
        view_state=ViewState(
            split_position=0.33,
            is_horizontal=True,
            diff_mode="highlight",
            channel_view_mode="R",
            overlay_enabled=True,
            showing_single_image_mode=1,
            movement_speed_per_sec=3.5,
        ),
        session_data=SessionData(
            image_state=ImageSessionState(
                auto_calculate_psnr=True, auto_calculate_ssim=True
            )
        ),
    )
    blob = serialize_viewport_block(vp)
    assert blob["view_state"]["diff_mode"] == "highlight"
    assert blob["render_config"]["font_size_percent"] == 140
    assert blob["image_state"]["auto_calculate_psnr"] is True

    other = ViewportState(
        session_data=SessionData(image_state=ImageSessionState())
    )
    restore_viewport_block(other, blob)
    assert other.view_state.split_position == pytest.approx(0.33)
    assert other.view_state.is_horizontal is True
    assert other.view_state.diff_mode == "highlight"
    assert other.render_config.font_size_percent == 140
    assert other.session_data.image_state.auto_calculate_ssim is True


def test_magnifier_models_roundtrip_in_viewport_block():
    from tabs.image_compare.canvas.features.magnifier.state.feature_state import (
        get_magnifier_widget_state,
    )
    from tabs.image_compare.canvas.features.magnifier.state.models import MagnifierModel
    from tabs.image_compare.canvas.features.magnifier.persistence import (
        restore_magnifier_from_project,
        serialize_magnifier_for_project,
    )
    from domain.types import Color, Point

    vp = ViewportState()
    state = get_magnifier_widget_state(vp.view_state)
    state.enabled = True
    model = MagnifierModel(
        id="mag-1",
        position=Point(0.25, 0.75),
        size_relative=0.3,
        border_color=Color(1, 2, 3, 4),
        is_horizontal=True,
    )
    state.models[model.id] = model
    state.active_id = model.id

    blob = serialize_magnifier_for_project(vp.view_state)
    assert blob["enabled"] is True
    assert blob["models"][0]["id"] == "mag-1"
    json.dumps(blob)

    other = ViewportState()
    restore_magnifier_from_project(other.view_state, blob)
    restored = get_magnifier_widget_state(other.view_state)
    assert restored.enabled is True
    assert restored.active_id == "mag-1"
    assert "mag-1" in restored.models
    assert restored.models["mag-1"].position.x == pytest.approx(0.25)
    assert restored.models["mag-1"].border_color.r == 1
