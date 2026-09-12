"""Double-list display_name backfill (PLAN 1A — data).

Rows render only ``item.display_name`` with no path/basename fallback, so any
``ImageItem(display_name="")`` from old projects draws as an empty row.
"""

from __future__ import annotations

from types import SimpleNamespace

from tabs.contract import TabContext
from tabs.image_compare.state.document import (
    DocumentModel,
    ImageItem,
    display_name_or_fallback,
)
from tabs.image_compare.use_cases import persistence as persistence_uc


class _FakeStore:
    def __init__(self, session):
        self._sessions = {session.id: session}

    def get_workspace_session(self, session_id: str):
        return self._sessions.get(session_id)

    def get_dispatcher(self):
        return None

    def set_session_state_slot(self, slot_name, value, *, session_id=None, emit_scope=None):
        self._sessions[session_id].state_slots[slot_name] = value


def _old_project_data():
    return {
        "version": 1,
        "image_list1": [{"path": "/a/b.png", "rating": 0}],
        "image_list2": [
            {"path": "/a/c.jpg", "display_name": "", "rating": 0},
            {"path": "", "display_name": "", "rating": 0},
        ],
        "current_index1": 0,
        "current_index2": 0,
    }


def test_deserialize_old_project_without_display_name_backfills(qapp):
    session = SimpleNamespace(
        id="s1",
        session_type="image_compare",
        document=DocumentModel(),
        state_slots={},
        viewport=None,
    )
    store = _FakeStore(session)
    tab = SimpleNamespace(_active_session_id="s1", _widget=None)

    persistence_uc.deserialize_session(tab, "s1", _old_project_data(), TabContext(store=store))
    qapp.processEvents()

    doc = session.state_slots["document"]
    assert doc.image_list1[0].display_name == "b"
    assert doc.image_list2[0].display_name == "c"
    assert doc.image_list2[1].display_name == "-----"
    assert all(it.display_name for it in doc.image_list1 + doc.image_list2)


def test_repopulate_passes_current_index(qapp):
    from unittest.mock import MagicMock

    from tabs.image_compare.ui.transient_flyouts import FlyoutController
    from ui.widgets.unified_list_picker import FlyoutMode

    document = DocumentModel(
        image_list1=[ImageItem(path="/a/b.png", display_name="b")],
        image_list2=[ImageItem(path="/a/c.png", display_name="c")],
        current_index1=0,
        current_index2=0,
    )
    flyout = MagicMock()
    flyout.isVisible.return_value = True
    flyout.mode = FlyoutMode.HIDDEN
    host = SimpleNamespace(
        unified_flyout=flyout,
        store=SimpleNamespace(get_session_state_slot=lambda _name: document),
    )
    controller = FlyoutController.__new__(FlyoutController)
    controller.manager = SimpleNamespace(host=host)
    controller.widget = SimpleNamespace()

    controller.repopulate_flyouts()

    calls = {c.args[0]: c for c in flyout.populate.call_args_list}
    assert calls[1].kwargs.get("current_index", calls[1].args[2] if len(calls[1].args) > 2 else None) == 0
    assert calls[2].kwargs.get("current_index", calls[2].args[2] if len(calls[2].args) > 2 else None) == 0
    qapp.processEvents()


def test_display_name_or_fallback():
    assert display_name_or_fallback(ImageItem(path="/a/b.png", display_name="")) == "b"
    assert display_name_or_fallback(ImageItem(path="/a/b.png", display_name="keep")) == "keep"
    assert display_name_or_fallback(ImageItem(path="", display_name="")) == "-----"

    doc = DocumentModel(
        image_list1=[ImageItem(path="/a/b.png", display_name="")],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )
    assert doc.get_active_display_name(1) == "b"
    assert doc.get_current_display_name(1) == "b"
    assert doc._last_display_name1 == "b"
