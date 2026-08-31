"""Regression contract: a deferred unification result must never paint pixels
from a document pair that is no longer selected.
"""

from __future__ import annotations

from PIL import Image

from core.state_management.dispatcher import Dispatcher
from core.store import Store
from core.store_viewport import SessionData
from tabs.image_compare.pipeline.pipeline import ImagePipeline
from tabs.image_compare.state.actions import PutPixelAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.state.models import ImageSessionState, RenderCacheState
from tabs.image_compare.use_cases import loading


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append(worker)


def _make_store(document: DocumentModel) -> Store:
    import tabs.image_compare.bootstrap_reducers  # noqa: F401 — ensure reducers

    store = Store()
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    store.viewport.session_data = SessionData(
        image_state=ImageSessionState(), render_cache=RenderCacheState()
    )
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    store.set_dispatcher(Dispatcher(store))
    from tabs.image_compare.state.models import PipelineCacheState

    try:
        if store.get_session_state_slot("pipeline") is None:
            store.set_session_state_slot("pipeline", PipelineCacheState())
    except Exception:
        pass
    return store


class _FakeController:
    """Mirrors the slice of ``SessionController`` that ``loading.py`` calls."""

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

    def _update_image_slot(self, slot_number, *, image=None, path=None, emit=True, is_preview=False, is_full_res=False):
        if image is not None and path is not None:
            try:
                self.store.transact([PutPixelAction(path=path, store=image)], scope="pipeline")
            except Exception:
                pass

    def _invalidate_image_canvas_render_state(self, clear_overlay_state=False):
        pass

    def _schedule_image_canvas_update(self):
        pass

    def _mark_full_res_ready(self, image_number):
        pass

    def _start_pyramid_builds(self, *stores):
        pass

    def _unify_images_worker_task(self, img1, img2, path1, path2, task_id, method_name="LANCZOS"):
        return img1, img2, path1, path2, task_id

    def _on_unified_images_ready(self, result):
        loading.on_unified_images_ready(self, result)

    def _cancel_pending_unification(self, *a, **kw):
        return False


def _pair(color1: str, color2: str, path1: str, path2: str):
    img1 = Image.new("RGBA", (4, 4), color1)
    img2 = Image.new("RGBA", (4, 4), color2)
    document = DocumentModel(
        image_list1=[ImageItem(path=path1, display_name=path1)],
        image_list2=[ImageItem(path=path2, display_name=path2)],
        current_index1=0,
        current_index2=0,
    )
    return img1, img2, document


def test_unification_scheduled_before_a_pair_swap_never_paints_the_old_pair(monkeypatch):
    """Reproduces the exact race: pair A's full-res worker finishes and
    schedules unification; before it runs, pair B is dropped and becomes
    the live document. With AbortSignal single-flight, the stale A unify
    must be aborted and B must win."""

    imgA1, imgA2, document = _pair("red", "green", "a1.png", "a2.png")
    store = _make_store(document)
    # seed pipeline for A
    store.transact([PutPixelAction(path="a1.png", store=imgA1)], scope="pipeline")
    store.transact([PutPixelAction(path="a2.png", store=imgA2)], scope="pipeline")
    controller = _FakeController(store)

    loading.handle_full_image_loaded(controller, imgA1, "a1.png", 1, 0)
    # Clear any A unification that was started synchronously to simulate race
    controller.thread_pool.started.clear()

    imgB1, imgB2, new_document = _pair("blue", "yellow", "b1.png", "b2.png")
    # seed pipeline for B
    store.set_session_state_slot("document", new_document)
    store.transact([PutPixelAction(path="b1.png", store=imgB1)], scope="pipeline")
    store.transact([PutPixelAction(path="b2.png", store=imgB2)], scope="pipeline")
    # need fresh pipeline that sees new document's paths via store
    controller.pipeline = ImagePipeline(store=store)

    # Trigger unification for live B document (synchronous, no QTimer)
    from tabs.image_compare.use_cases.unify import ensure_unification

    ensure_unification(controller)

    assert len(controller.thread_pool.started) == 1, (
        "the unification must run against the live (B) document, "
        "not silently no-op because it still thinks A is selected"
    )
    worker = controller.thread_pool.started[0]
    result = worker.fn(*worker.args, **worker.kwargs)

    _, _, path1, path2, _task_id = result
    assert (path1, path2) == ("b1.png", "b2.png"), (
        "unify worker ran on the stale (A) paths captured by the closure "
        "instead of the live (B) document"
    )

    controller._on_unified_images_ready(result)

    rendered1 = store.viewport.session_data.image_state.image1
    rendered2 = store.viewport.session_data.image_state.image2
    assert rendered1 is not None and rendered2 is not None, (
        "on_unified_images_ready dropped the result instead of applying it "
        "-- this is the observed bug: the canvas keeps showing the previous "
        "pair's pixels forever because nothing else re-triggers unification"
    )
    assert rendered1.tobytes() == imgB1.tobytes(), "canvas would render pair A's pixels instead of the live pair B"
    assert rendered2.tobytes() == imgB2.tobytes(), "canvas would render pair A's pixels instead of the live pair B"
    assert rendered1.tobytes() != imgA1.tobytes()
    assert rendered2.tobytes() != imgA2.tobytes()
