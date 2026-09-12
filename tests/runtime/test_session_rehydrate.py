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
        self.image_list1 = []
        self.image_list2 = []
        self.image1_path = "/one.png"
        self.image2_path = None


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

    context = TabContext(
        store=store,
        main_window=SimpleNamespace(
            main_controller=SimpleNamespace(sessions=sessions_ctrl)
        ),
    )

    tab.rehydrate_session("ic1", context)

    assert loads == [(["/one.png"], 1)]
    assert store.workspace.active_session_id == "other"


def test_multi_compare_rehydrate_uses_controller_loader(qapp, tmp_path):
    img_path = tmp_path / "slot.png"
    from PIL import Image

    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(img_path)

    state = MultiCompareState(
        slots=[CompareSlot(id=0, path=img_path, label="x", image=None)]
    )
    store = SimpleNamespace(
        get_session_state_slot=lambda slot, session_id=None: state,
    )
    widget = MultiCompareWidget()
    controller = MultiCompareController(widget, store=store)
    tab = MultiCompareTab()
    tab._controller = controller
    tab._active_session_id = None

    read_calls = []
    original_read = controller._read_image

    def _tracking_read(path):
        read_calls.append(path)
        return original_read(path)

    controller._read_image = _tracking_read

    tab.rehydrate_session("mc1", TabContext(store=store))

    assert read_calls == [img_path]
    assert state.slots[0].image is not None
    assert state.slots[0].image.size == (2, 2)
