"""Dispatch-bypass regressions: list mutations must go through dispatch.

Covers three bypasses where use-cases mutated Store state in place instead
of dispatching (single-flight / undo / HUD staleness fallout):

1. decode-failure pop (use_cases/image_decode.py) mutated the live list —
   no history entry and every snapshot aliasing the same list lost the item.
2. duplicate append (use_cases/slot.py) bypassed dispatch — an unrelated
   undo restored a snapshot sharing the mutated list.
3. chrome fallback scan (use_cases/chrome_sync.py) matched cache entries by
   path only — stale dims survived a file overwrite.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest

from core.state_management import slot_reducers as _slot_reducers_module
from core.state_management.dispatcher import Dispatcher
from core.store_viewport import ViewportState
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.reducer import DocumentReducer
from tabs.image_compare.use_cases import chrome_sync, image_decode, slot as slot_uc


@pytest.fixture(autouse=True)
def _document_slot_reducer():
    """Register the real DocumentReducer like ComparisonPlugin does."""
    saved = dict(_slot_reducers_module._SLOT_REDUCERS)
    _slot_reducers_module.register_state_slot_reducer(
        "document", DocumentReducer.reduce
    )
    try:
        yield
    finally:
        _slot_reducers_module._SLOT_REDUCERS.clear()
        _slot_reducers_module._SLOT_REDUCERS.update(saved)


@pytest.fixture(autouse=True)
def _clean_dims_cache():
    saved = dict(chrome_sync._original_dims_cache)
    chrome_sync._original_dims_cache.clear()
    try:
        yield
    finally:
        chrome_sync._original_dims_cache.clear()
        chrome_sync._original_dims_cache.update(saved)


class _Session:
    def __init__(self, session_id: str):
        self.id = session_id
        self.session_type = "image_compare"
        self.state_slots: dict = {}


class _Store:
    """Fake store with a real Dispatcher — transact delegates to dispatch,
    mirroring Store.transact's single-action fast path."""

    def __init__(self, document: DocumentModel):
        from tabs.image_compare.state.models import ImageSessionState, RenderCacheState
        from core.store_viewport import SessionData

        self._sessions = {"a": _Session("a")}
        self.workspace = SimpleNamespace(active_session_id="a")
        self.settings = SimpleNamespace(current_language="en")
        self.viewport = ViewportState(
            session_data=SessionData(
                image_state=ImageSessionState(),
                render_cache=RenderCacheState(),
            )
        )
        self.document = document
        self._extra_slots: dict = {}
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
        return self._extra_slots.get(slot, default)

    def set_session_state_slot(self, slot, value, *, session_id=None, emit_scope=""):
        if slot == "document":
            self.document = value
        else:
            self._extra_slots[slot] = value

    def emit_state_change(self, scope):
        self.events.append(scope)

    def on_change(self, callback):
        self._change_callback = callback

    def get_dispatcher(self):
        return self._dispatcher

    def transact(self, actions, scope="document"):
        for a in actions:
            self._dispatcher.dispatch(a, scope=scope)

    def batch_changes(self):
        from contextlib import nullcontext

        return nullcontext()


class _Controller:
    def __init__(self, store: _Store):
        self.store = store
        self.pipeline = None
        self.presenter = None
        self.event_bus = None
        self.reloads: list[int] = []

    def set_current_image(self, image_number, force_refresh=False, emit_signal=True):
        self.reloads.append(image_number)


def _history_types(store: _Store) -> list[str]:
    return [a.type for a in store._dispatcher.get_action_history()]


def test_decode_failure_removes_item_via_dispatch():
    """Failed decode drops the item through SetImageListAction, not pop().

    Integrity: the pre-dispatch document snapshot is unaliased (still holds
    both items), the store holds a replaced document with only the survivor,
    and the removal is published in dispatcher history.
    """
    doc = DocumentModel(
        image_list1=[ImageItem(path="bad"), ImageItem(path="good")],
        current_index1=0,
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    image_decode.on_image_loaded(controller, (None, "bad", 1, 0, False))

    assert [it.path for it in store.document.image_list1] == ["good"]
    # Copy-on-write: the old snapshot was not mutated in place.
    assert store.document is not doc
    assert [it.path for it in doc.image_list1] == ["bad", "good"]
    assert "SET_IMAGE_LIST" in _history_types(store)
    # Removed index was current → slot re-sync requested.
    assert controller.reloads == [1]


def test_duplicate_appends_via_dispatch_with_clean_undo():
    """duplicate_image_to_slot publishes AppendImageItemsAction.

    The pre-dispatch snapshot stays empty (no in-place leak into undo
    history), the append is recorded, and a later undo of an unrelated
    index change keeps the duplicated item.
    """
    doc = DocumentModel(
        image_list1=[ImageItem(path="a", display_name="a", rating=3)],
        current_index1=0,
        image_list2=[],
        current_index2=-1,
    )
    store = _Store(doc)
    store._dispatcher = Dispatcher(store)
    controller = _Controller(store)

    slot_uc.duplicate_image_to_slot(controller, 1, 2)

    assert [it.path for it in store.document.image_list2] == ["a"]
    assert store.document is not doc
    assert doc.image_list2 == []
    assert "APPEND_IMAGE_ITEMS" in _history_types(store)

    # Unrelated undoable dispatch + undo must keep the duplicated item.
    from core.state_management.actions import SetCurrentIndexAction

    store._dispatcher.dispatch(SetCurrentIndexAction(slot=2, index=0), scope="document")
    store._dispatcher.undo()
    assert [it.path for it in store.document.image_list2] == ["a"]


def test_hud_dims_skip_stale_entry_after_overwrite(tmp_path, monkeypatch):
    """Fallback scan honors the fail-closed (mtime+size) identity.

    After an overwrite, the old cache entry (same path, old mtime+size) is
    skipped instead of serving pre-overwrite dims; a fresh entry serves.
    """
    from tabs.image_compare.pipeline.cache import _pixel_key

    target = tmp_path / "img.bin"
    target.write_bytes(b"x" * 100)
    os.utime(target, (1_000_000_000, 1_000_000_000))
    stale_key = _pixel_key(str(target), None, None)

    target.write_bytes(b"y" * 200)
    os.utime(target, (1_000_000_100, 1_000_000_100))
    fresh_key = _pixel_key(str(target), None, None)
    assert stale_key != fresh_key

    stale_img = SimpleNamespace(width=10, height=20)
    fresh_img = SimpleNamespace(width=30, height=40)
    pipeline_slot = SimpleNamespace(
        pixel={stale_key: stale_img, fresh_key: fresh_img},
        preview={},
    )
    doc = DocumentModel(
        image_list1=[ImageItem(path=str(target))],
        current_index1=0,
    )
    store = _Store(doc)
    store._extra_slots["pipeline"] = pipeline_slot
    # Force the fallback scan: header probe pretends to fail.
    monkeypatch.setattr(chrome_sync, "_probe_original_dimensions", lambda _p: None)

    assert chrome_sync.get_image_dimensions(store, 1) == (30, 40)

    # Stale-only cache fails closed (None) instead of serving old dims.
    store._extra_slots["pipeline"] = SimpleNamespace(
        pixel={stale_key: stale_img}, preview={}
    )
    assert chrome_sync.get_image_dimensions(store, 1) is None
