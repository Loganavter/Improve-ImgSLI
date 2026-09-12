"""Rehydrate session hooks reload media from persisted paths."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from tabs.contract import TabContext
from tabs.image_compare.tab import ImageCompareTab
from tabs.multi_compare.controller import MultiCompareController
from tabs.multi_compare.models import CompareSlot, MultiCompareState
from tabs.multi_compare.tab import _STATE_SLOT, MultiCompareTab
from tabs.multi_compare.widget import MultiCompareWidget


class _FakeDocument:
    def __init__(self):
        from tabs.image_compare.state.document import ImageItem
        self.image_list1 = [ImageItem(path="/one.png", display_name="one", rating=0)]
        self.image_list2 = []
        self.image1_path = "/one.png"
        self.image2_path = None
        self.current_index1 = 0
        self.current_index2 = -1


class _FakeICSession:
    def __init__(self, session_id: str):
        self.id = session_id
        self.session_type = "image_compare"
        self.document = _FakeDocument()
        self.state_slots = {}


class _FakeICStore:
    def __init__(self, session: _FakeICSession):
        self.workspace = SimpleNamespace(active_session_id="other")
        self._sessions = {session.id: session, "other": _FakeICSession("other")}

    def get_workspace_session(self, session_id: str):
        return self._sessions.get(session_id)

    @contextmanager
    def using_workspace_session(self, session_id: str):
        session = self._sessions.get(session_id)
        previous_id = self.workspace.active_session_id
        if session is not None and previous_id != session_id:
            self.workspace.active_session_id = session_id
        try:
            yield session
        finally:
            if previous_id and previous_id != session_id:
                self.workspace.active_session_id = previous_id


def test_image_compare_rehydrate_calls_load_pipeline(qapp):
    tab = ImageCompareTab()
    session = _FakeICSession("ic1")
    store = _FakeICStore(session)
    loads = []

    sessions_ctrl = MagicMock()
    sessions_ctrl.load_images_from_paths = lambda paths, num: loads.append(
        (list(paths), num)
    )
    sessions_ctrl.set_current_image = lambda slot, **kw: loads.append((f"set_current:{slot}", kw))

    context = TabContext(
        store=store,
        main_window=SimpleNamespace(
            main_controller=SimpleNamespace(sessions=sessions_ctrl)
        ),
    )

    tab.rehydrate_session("ic1", context)

    # Phase 5: rehydrate is demand-driven via set_current_image (single PipelineCache), not load_images_from_paths
    assert any(str(x[0]).startswith("set_current") for x in loads) or loads == [(["/one.png"], 1)]
    assert store.workspace.active_session_id == "other"


def test_multi_compare_rehydrate_is_lazy_paths_only(qapp, tmp_path, monkeypatch):
    """B1: MC rehydrate records paths only — zero sync decodes on reopen
    (was: every slot sync-decoded into ``slot.image`` on the GUI thread).
    Demand fill is kicked on activation, not here (dormant session)."""
    from shared.image_processing import pixel_cache_loader as pcl_mod

    img_path = tmp_path / "slot.png"
    from PIL import Image

    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(img_path)

    state = MultiCompareState(
        slots=[CompareSlot(id=0, path=img_path, label="x")]
    )
    store = SimpleNamespace(
        get_session_state_slot=lambda slot, session_id=None: state,
        get_active_workspace_session=lambda: SimpleNamespace(id="other"),
    )
    widget = MultiCompareWidget()
    controller = MultiCompareController(widget, store=store)
    tab = MultiCompareTab()
    tab._controller = controller
    tab._active_session_id = None

    read_calls = []
    original_read = controller._read_image

    def _tracking_read(path, **kwargs):
        read_calls.append(path)
        return original_read(path, **kwargs)

    controller._read_image = _tracking_read
    full_calls = []
    real_full = pcl_mod.load_pixel_store

    def _spy_full(path_str, **kwargs):
        full_calls.append(str(path_str))
        return real_full(path_str, **kwargs)

    monkeypatch.setattr(pcl_mod, "load_pixel_store", _spy_full)

    tab.rehydrate_session("mc1", TabContext(store=store))

    assert read_calls == []  # no sync decode at restore (was 1 per slot)
    assert full_calls == []  # 0 full decodes on reopen
    slot = state.slots[0]
    assert slot.path == img_path
    assert slot.revision == 0
    assert not hasattr(slot, "image")  # path-only SlotSource
