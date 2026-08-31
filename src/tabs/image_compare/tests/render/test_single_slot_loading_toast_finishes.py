"""Regression contract: loading a single slot must not leave the "loading
full image" toast stuck forever.

Real bug: the toast is shown per-slot as soon as a preview lands
(``_session_controller._on_image_loaded`` -> ``_show_loading_toast``), but it
used to be closed only via ``_start_pyramid_builds``, which is reachable only
through a successful unification -- and unification requires *both* slots to
hold an image (``source1 and source2`` in ``loading.trigger_preview_unification``
/ ``trigger_unification``). Loading a picture into just one slot means that
condition never becomes true, so the toast for that slot never finished.
"""

from __future__ import annotations

from PIL import Image

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.pipeline.cache import _pixel_key
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.state.actions import PutPixelAction, PutPreviewAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState
from tabs.image_compare.use_cases import loading


def _make_store(document: DocumentModel) -> Store:
    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    return store


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append(worker)


class _FakeController:
    def __init__(self, store: Store):
        self.store = store
        self.pipeline = ImagePipeline(store=store)
        self.thread_pool = _ThreadPool()
        self.presenter = None
        self.event_bus = None
        self.diff_service = None
        self.metrics_service = type(
            "M", (), {"on_metrics_calculated": lambda self, _v: None}
        )()
        self.finished_toasts: list = []

    def _cancel_pending_unification(self, *_args, **_kwargs):
        pass

    def _invalidate_image_canvas_render_state(self, *_a, **_kw):
        pass

    def _schedule_image_canvas_update(self, *_a, **_kw):
        pass

    def _trigger_preview_unification(self, n):  # for slot.set_current fallback
        pass

    def set_current_image(self, *a, **kw):
        pass

    def _update_image_slot(self, image_number, *, image=None, path=None, is_full_res=False, is_preview=False):
        # legacy path no longer used — pipeline is single source; keep no-op for compat
        if image is not None and path:
            try:
                self.store.transact([PutPixelAction(path=path, store=image)], scope="pipeline")
            except Exception:
                pass

    def _mark_full_res_ready(self, image_number):
        pass

    def _finish_loading_toast(self, image_number):
        self.finished_toasts.append(image_number)

    def _start_pyramid_builds(self, *_a, **_kw):
        pass

    def _trigger_metrics_calculation_if_needed(self, *_a, **_kw):
        pass


def _single_slot_document(path: str):
    img = Image.new("RGBA", (4, 4), "red")
    document = DocumentModel(
        image_list1=[ImageItem(path=path, display_name=path)],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )
    return document, img


def test_trigger_preview_unification_finishes_toast_for_unpaired_slot():
    document, img = _single_slot_document("only1.png")
    store = _make_store(document)
    # seed pipeline pixel for this path — single source
    store.transact([PutPixelAction(path="only1.png", store=img)], scope="pipeline")
    controller = _FakeController(store)

    loading.trigger_preview_unification(controller, 1)

    assert controller.finished_toasts == [1], (
        "loading a single slot must close its own loading toast once its "
        "full-res decode is done, since unify (and the pyramid build that "
        "normally closes the toast) will never run without a paired image"
    )
    assert controller.thread_pool.started == []


def test_handle_full_image_loaded_finishes_toast_for_unpaired_slot(monkeypatch):
    document, img = _single_slot_document("only1.png")
    store = _make_store(document)
    # need pipeline linked before call
    controller = _FakeController(store)

    loading.handle_full_image_loaded(controller, img, "only1.png", 1, 0)

    assert controller.finished_toasts == [1]
    assert controller.thread_pool.started == []


def test_trigger_preview_unification_does_not_finish_toast_while_own_decode_pending():
    """A fresh preview (no full-res yet) in an otherwise-empty pairing must
    not finish the toast prematurely -- the full-res decode for that slot is
    still in flight."""
    path = "only1.png"
    document = DocumentModel(
        image_list1=[ImageItem(path=path, display_name=path)],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
    )
    store = _make_store(document)
    preview = Image.new("RGBA", (4, 4), "red")
    store.transact([PutPreviewAction(path=path, qimage=preview)], scope="pipeline")
    controller = _FakeController(store)
    # mark that full pixel still inflight — pipeline._inflight key for slot 1
    from tabs.image_compare.pipeline.abort import AbortSignal

    sig = AbortSignal()
    controller.pipeline._inflight[(1, path)] = sig  # type: ignore[index]

    loading.trigger_preview_unification(controller, 1)

    assert controller.finished_toasts == []
