"""DnD into one slot must not wipe the other slot's live image.

Repro (IC DnD cross-slot wipe): slot 2 holds a fresh preview (its TileStore
worker still in flight) while a DnD load lands in slot 1. The slot-1
``transact(scope="document")`` emits ``document`` → ``_on_store_scoped_change``
→ ``resync_current_image_slots`` force-refreshes BOTH slots. Slot 2's
``set_current_image(force=True)`` sees a pipeline cache-miss (worker not done)
and dispatches the destructive clear (``ClearImageSlotDataAction`` +
``SetImageSessionImageAction(slot=2, image=None)``) even though slot 2's
idx/path never changed.

Contract: preload slot 2, then ``load_images_from_paths`` slot 1, then the
document-emit resync — ``ClearImageSlotDataAction`` for slot 2 is never
dispatched and ``image_state.image2`` keeps the preloaded image.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace

from core.state_management.actions import (
    ClearImageSlotDataAction,
    SetCurrentIndexAction,
    SetImageSessionImageAction,
)
from tabs.image_compare.pipeline.image_load_service import ImageLoadService
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.state.document import DocumentModel
from tabs.image_compare.use_cases import session_bootstrap, slot as slot_uc

PATH1 = "/dnd-cross-slot/a.png"
PATH2 = "/dnd-cross-slot/b.png"


class _RecordingStore:
    """Minimal Store double: applies document/image_state actions, records."""

    def __init__(self, document: DocumentModel):
        self._document = document
        self.viewport = SimpleNamespace(
            session_data=SimpleNamespace(
                image_state=SimpleNamespace(image1=None, image2=None),
                render_cache=SimpleNamespace(
                    unification_in_progress=False,
                    pending_unification_paths=None,
                    cached_diff_image=None,
                ),
            )
        )
        self.settings = SimpleNamespace(current_language="en")
        self.dispatched: list = []
        self.emitted: list[str] = []
        self._dispatcher = _FakeDispatcher(self)

    def get_session_state_slot(self, name, **_kw):
        assert name == "document"
        return self._document

    def get_dispatcher(self):
        return self._dispatcher

    def transact(self, actions, scope="document"):
        for action in actions:
            self._apply(action)
            self.dispatched.append(action)
        self.emit_state_change(scope)

    def batch_changes(self):
        return nullcontext()

    def emit_state_change(self, scope):
        self.emitted.append(scope)

    def invalidate_render_cache(self):
        pass

    def _apply(self, action):
        doc = self._document
        images = self.viewport.session_data.image_state
        render_cache = self.viewport.session_data.render_cache
        try:
            from core.state_management.document_actions import (
                AppendImageItemsAction,
            )
        except Exception:
            AppendImageItemsAction = None  # type: ignore
        try:
            from core.state_management.actions import (
                SetCachedDiffImageAction,
                SetPendingUnificationPathsAction,
                SetUnificationInProgressAction,
            )
        except Exception:
            SetCachedDiffImageAction = SetPendingUnificationPathsAction = (  # type: ignore
                SetUnificationInProgressAction
            ) = None
        if AppendImageItemsAction is not None and isinstance(
            action, AppendImageItemsAction
        ):
            if action.slot == 1:
                self._document = replace(
                    doc, image_list1=list(doc.image_list1) + list(action.items)
                )
            else:
                self._document = replace(
                    doc, image_list2=list(doc.image_list2) + list(action.items)
                )
        elif isinstance(action, SetCurrentIndexAction):
            if action.slot == 1:
                self._document = replace(doc, current_index1=action.index)
            else:
                self._document = replace(doc, current_index2=action.index)
        elif isinstance(action, ClearImageSlotDataAction):
            if action.slot == 1:
                self._document = replace(doc, _last_display_name1="")
                images.image1 = None
            else:
                self._document = replace(doc, _last_display_name2="")
                images.image2 = None
        elif isinstance(action, SetImageSessionImageAction):
            if action.slot == 1:
                images.image1 = action.image
            else:
                images.image2 = action.image
        elif (
            SetUnificationInProgressAction is not None
            and isinstance(action, SetUnificationInProgressAction)
        ):
            render_cache.unification_in_progress = action.enabled
        elif (
            SetPendingUnificationPathsAction is not None
            and isinstance(action, SetPendingUnificationPathsAction)
        ):
            render_cache.pending_unification_paths = action.paths
        elif (
            SetCachedDiffImageAction is not None
            and isinstance(action, SetCachedDiffImageAction)
        ):
            render_cache.cached_diff_image = action.image


class _FakeDispatcher:
    def __init__(self, store: _RecordingStore):
        self._store = store

    def dispatch(self, action, scope="viewport"):
        self._store._apply(action)
        self._store.dispatched.append(action)
        self._store.emit_state_change(scope)


class _FakeSignal:
    def emit(self, *_args, **_kwargs):
        pass


class _FakeController:
    """Thin-owner double: real slot/bootstrap logic, stubbed side effects."""

    def __init__(self, store: _RecordingStore):
        self.store = store
        self.pipeline = ImagePipeline(store=None)
        self.thread_pool = None
        self.presenter = None
        self.event_bus = None
        self.diff_service = None
        self.metrics_service = None
        self.error_occurred = _FakeSignal()
        self.update_requested = _FakeSignal()
        self._resyncing = False
        self._last_resync_slot_sig: dict = {}
        self._session = SimpleNamespace(
            cache=self.pipeline.cache,
            load_service=ImageLoadService(
                cache=self.pipeline.cache,
                get_crop_service=lambda: None,
                get_store=lambda: store,
                get_thread_pool=lambda: None,
            ),
        )

    def _get_image_session(self, _session_id=None):
        return self._session

    def _get_crop_service(self):
        return None

    def set_current_image(
        self, image_number: int, force_refresh: bool = False, emit_signal: bool = True
    ):
        slot_uc.set_current_image(
            self,
            image_number,
            force_refresh=force_refresh,
            emit_signal=emit_signal,
        )

    def _update_image_slot(self, *_args, **_kwargs):
        pass

    def _invalidate_image_canvas_render_state(self, *_args, **_kwargs):
        pass

    def _schedule_image_canvas_update(self):
        pass

    def _trigger_preview_unification(self, _image_number: int):
        pass

    def _on_image_loaded(self, _result):
        raise AssertionError("no worker result expected (inline pool)")


def _cleared_slots(store: _RecordingStore) -> list[int]:
    return [
        a.slot for a in store.dispatched if isinstance(a, ClearImageSlotDataAction)
    ]


def test_dnd_into_slot1_keeps_slot2_live_image():
    store = _RecordingStore(DocumentModel())
    controller = _FakeController(store)

    # Preload slot 2 (DnD onto empty side), then run the document-emit resync
    # so the resync signature cache observes slot 2's (idx, path).
    slot_uc.load_images_from_paths(controller, [PATH2], 2)
    session_bootstrap.resync_current_image_slots(controller)

    # Slot 2 preview is fresh but its TileStore worker is still in flight.
    live_image = object()
    store.viewport.session_data.image_state.image2 = live_image
    acquired = controller._session.load_service.try_acquire_load(PATH2)
    assert acquired is not None
    assert controller._session.load_service.is_loading(PATH2) is True

    # Only actions from here on count: the bug wipes slot 2 during the
    # slot-1 load + its document-emit resync.
    store.dispatched.clear()

    # DnD load into slot 1, then the document-emit resync
    # (transact scope=document -> _on_store_scoped_change -> resync both).
    slot_uc.load_images_from_paths(controller, [PATH1], 1)
    assert "document" in store.emitted
    session_bootstrap.resync_current_image_slots(controller)

    assert 2 not in _cleared_slots(store)
    assert store.viewport.session_data.image_state.image2 is live_image
