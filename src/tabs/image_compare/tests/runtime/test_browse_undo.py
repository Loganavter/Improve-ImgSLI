"""Browsing undo: the combobox index change goes through the Dispatcher
(SET_CURRENT_INDEX), and the tab re-syncs the displayed image when the
restored document's pixels reference a closed store (path+reload)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

from core.state_management import slot_reducers as _slot_reducers_module
from core.state_management.actions import SetCurrentIndexAction
from core.state_management.dispatcher import Dispatcher
from core.state_management.reducers import RootReducer
from core.store_viewport import ViewportState
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.reducer import DocumentReducer
from tabs.image_compare.use_cases import loading, navigation


@pytest.fixture(autouse=True)
def _document_slot_reducer():
    """The app registers the document reducer via ComparisonPlugin; tests
    register it the same way so Dispatcher.write-back and undo restore run
    the real DocumentReducer. Snapshot/restore the registry around each test."""
    saved = dict(_slot_reducers_module._SLOT_REDUCERS)
    _slot_reducers_module.register_state_slot_reducer(
        "document", DocumentReducer.reduce
    )
    try:
        yield
    finally:
        _slot_reducers_module._SLOT_REDUCERS.clear()
        _slot_reducers_module._SLOT_REDUCERS.update(saved)


class _Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.session_type = "image_compare"
        self.state_slots: dict = {}


class _Store:
    def __init__(self, document: DocumentModel):
        self._sessions = {"a": _Session("a")}
        self.workspace = SimpleNamespace(active_session_id="a")
        self.settings = SimpleNamespace(current_language="en")
        self.viewport = ViewportState(
            session_data=SimpleNamespace(
                render_cache=SimpleNamespace(
                    unification_in_progress=False, pending_unification_paths=None
                )
            )
        )
        self.document = document
        self.events: list[str] = []
        self.recorder = None
        self._dispatcher = None

    def get_workspace_session(self, session_id):
        return self._sessions.get(session_id)

    def get_active_workspace_session(self):
        return self._sessions.get(self.workspace.active_session_id)

    def get_session_state_slot(self, slot, *, session_id=None, default=None):
        if slot == "document":
            return self.document
        return default

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=""):
        if slot == "document":
            self.document = value

    def emit_state_change(self, scope):
        self.events.append(scope)

    def on_change(self, callback):
        self._change_callback = callback

    def get_dispatcher(self):
        return self._dispatcher


class _Signal:
    def emit(self, *_args, **_kwargs):
        pass


class _Controller:
    def __init__(self, store: _Store):
        self.store = store
        self.event_bus = None
        self.update_requested = _Signal()
        self.reloads: list[int] = []

    def set_current_image(self, image_number, force_refresh=False, emit_signal=True):
        self.reloads.append(image_number)


def test_combobox_browse_dispatches_undoable_index_change():
    doc = DocumentModel(
        image_list1=[ImageItem(path="a"), ImageItem(path="b")],
        current_index1=0,
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    navigation.on_combobox_changed(controller, 1, 1)

    assert store.document.current_index1 == 1
    # Went through the reducer, not a direct mutation: the document object
    # was replaced (dataclasses.replace) and the action is undoable.
    assert store.document is not doc
    assert store._dispatcher.can_undo()

    store._dispatcher.undo()
    assert store.document.current_index1 == 0
    assert "document" in store.events
    assert "viewport" in store.events


def test_combobox_same_index_does_not_push_undo():
    doc = DocumentModel(
        image_list1=[ImageItem(path="a"), ImageItem(path="b")],
        current_index1=1,
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    navigation.on_combobox_changed(controller, 1, 1)

    assert not store._dispatcher.can_undo()


class _ClosedStore:
    is_open = False


class _OpenStore:
    is_open = True


def test_resync_reloads_slot_with_closed_store():
    doc = DocumentModel(
        image_list1=[ImageItem(path="a")],
        current_index1=0,
        image1_path="a",
        full_res_image1=_ClosedStore(),
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    loading.resync_current_image_slots(controller)

    assert controller.reloads == [1]


def test_resync_reloads_on_path_mismatch_after_redo():
    doc = DocumentModel(
        image_list1=[ImageItem(path="a"), ImageItem(path="b")],
        current_index1=1,
        image1_path="a",  # snapshot path diverges from the current entry
        full_res_image1=_OpenStore(),
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    loading.resync_current_image_slots(controller)

    assert controller.reloads == [1]


def test_resync_leaves_healthy_slot_untouched():
    doc = DocumentModel(
        image_list1=[ImageItem(path="a")],
        current_index1=0,
        image1_path="a",
        full_res_image1=_OpenStore(),
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    loading.resync_current_image_slots(controller)

    assert controller.reloads == []


def test_set_current_index_action_reducer_updates_document():
    """The wiring target: SET_CURRENT_INDEX is undoable and the reducer
    replaces the document (reference snapshot stays sound)."""
    doc = DocumentModel(
        image_list1=[ImageItem(path="a"), ImageItem(path="b")],
        current_index1=0,
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)

    store._dispatcher.dispatch(SetCurrentIndexAction(slot=1, index=1))
    assert store.document.current_index1 == 1
    assert store.document is not doc

    store._dispatcher.dispatch(SetCurrentIndexAction(slot=2, index=0))
    assert store.document.current_index2 == 0