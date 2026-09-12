"""Regression contract: a deferred unification result must never paint pixels
from a document pair that is no longer selected.

Real bug this guards against: dropping a full-resolution image pair schedules
``trigger_unification`` on a 50ms ``QTimer``. If a *second* pair is dropped
and becomes the live document before that timer fires, the deferred closure
used to keep a reference to the first (now-replaced) ``document`` object.
The unify worker then ran on stale image data, and by the time its result
came back, ``on_unified_images_ready`` correctly detected the path mismatch
and *dropped* it -- but nothing re-triggered unification for the pair that
actually is selected. The user-visible symptom was the canvas "sticking" on
the first pair's pixels indefinitely, even though every path/index in the
document already pointed at the second pair.

Checking only that internal flags (``unification_in_progress``,
``_unification_task_id``) end up in the "right" state is exactly what let
this bug slip through before: the branch that drops a stale result is
"correct" in isolation. The only way to actually catch the freeze is to
render both pairs through the unify path and compare the final pixel buffer
that would reach the GPU (``session_data.image_state.image1/2``) against the
real pixel content of the pair that is live when the dust settles.
"""

from __future__ import annotations

from PIL import Image

from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.use_cases import loading


class _RenderCache:
    def __init__(self):
        self.unification_in_progress = False
        self.pending_unification_paths = None
        self.display_cache_image1 = None
        self.display_cache_image2 = None
        self.scaled_image1_for_display = None
        self.scaled_image2_for_display = None
        self.unified_image_cache = {}
        self.last_display_cache_params = None
        self.cached_diff_image = None


class _ImageState:
    image1 = None
    image2 = None


class _SessionData:
    def __init__(self):
        self.image_state = _ImageState()
        self.render_cache = _RenderCache()


class _Viewport:
    def __init__(self):
        self.session_data = _SessionData()
        self.render_config = type("Cfg", (), {"display_resolution_limit": 0})()


class _Store:
    def __init__(self, document: DocumentModel):
        self.document = document
        self.viewport = _Viewport()
        self.geometry_invalidations = 0
        self.render_cache_invalidations = 0

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document

    def invalidate_geometry_cache(self):
        self.geometry_invalidations += 1

    def invalidate_render_cache(self):
        self.render_cache_invalidations += 1

    def emit_state_change(self, *_args, **_kwargs):
        pass


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append(worker)


class _FakeController:
    """Mirrors the slice of ``SessionController`` that ``loading.py`` calls."""

    def __init__(self, store: _Store):
        self.store = store
        self.thread_pool = _ThreadPool()
        self.presenter = None
        self.event_bus = None
        self.diff_service = None
        self.metrics_service = type(
            "M", (), {"on_metrics_calculated": lambda self, _v: None}
        )()
        self._unification_task_id = 0

    def _update_image_slot(
        self,
        slot_number,
        *,
        image=None,
        path=None,
        emit=True,
        is_preview=False,
        is_full_res=False,
    ):
        document = self.store.get_session_state_slot("document")
        if is_full_res and image is not None:
            if slot_number == 1:
                document.full_res_image1 = image
            else:
                document.full_res_image2 = image
        if is_preview and image is not None:
            if slot_number == 1:
                document.preview_image1 = image
            else:
                document.preview_image2 = image
        if path is not None:
            if slot_number == 1:
                document.image1_path = path
            else:
                document.image2_path = path

    def _invalidate_image_canvas_render_state(self, clear_magnifier=False):
        pass

    def _schedule_image_canvas_update(self):
        pass

    def _unify_images_worker_task(self, img1, img2, path1, path2, task_id, method_name="LANCZOS"):
        return img1, img2, path1, path2, task_id

    def _on_unified_images_ready(self, result):
        loading.on_unified_images_ready(self, result)


def _pair(color1: str, color2: str, path1: str, path2: str):
    img1 = Image.new("RGBA", (4, 4), color1)
    img2 = Image.new("RGBA", (4, 4), color2)
    document = DocumentModel(
        image_list1=[ImageItem(image=None, path=path1, display_name=path1)],
        image_list2=[ImageItem(image=None, path=path2, display_name=path2)],
        current_index1=0,
        current_index2=0,
        image1_path=path1,
        image2_path=path2,
    )
    return img1, img2, document


def test_unification_scheduled_before_a_pair_swap_never_paints_the_old_pair(monkeypatch):
    """Reproduces the exact race: pair A's full-res worker finishes and
    schedules unification 50ms out; before that timer fires, pair B is
    dropped and becomes the live document. When the timer finally runs, it
    must resolve against the *live* (B) document, not the one captured at
    schedule time -- and the pixels that would reach the GPU must be B's,
    never A's stale content."""

    imgA1, imgA2, document = _pair("red", "green", "a1.png", "a2.png")
    store = _Store(document)
    controller = _FakeController(store)

    deferred = []
    monkeypatch.setattr(
        loading, "QTimer", type("QTimer", (), {"singleShot": staticmethod(
            lambda _ms, fn: deferred.append(fn)
        )})
    )

    document.full_res_image1 = imgA1
    document.full_res_image2 = imgA2
    document.image_list1[0].image = imgA1
    document.image_list2[0].image = imgA2

    loading.handle_full_image_loaded(controller, imgA1, "a1.png", 1, 0)
    assert len(deferred) == 1, "expected trigger_unification to be scheduled"

    imgB1, imgB2, new_document = _pair("blue", "yellow", "b1.png", "b2.png")
    new_document.full_res_image1 = imgB1
    new_document.full_res_image2 = imgB2
    new_document.image_list1[0].image = imgB1
    new_document.image_list2[0].image = imgB2
    store.document = new_document

    trigger_unification = deferred.pop()
    trigger_unification()

    assert len(controller.thread_pool.started) == 1, (
        "the deferred unification must run against the live (B) document, "
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
