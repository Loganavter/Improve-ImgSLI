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

from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.use_cases import loading


class _RenderCache:
    def __init__(self):
        self.unification_in_progress = False
        self.pending_unification_paths = None
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


class _Store:
    def __init__(self, document: DocumentModel):
        self.document = document
        self.viewport = _Viewport()

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document

    def emit_state_change(self, *_args, **_kwargs):
        pass


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append(worker)


class _FakeController:
    def __init__(self, store: _Store):
        self.store = store
        self.thread_pool = _ThreadPool()
        self.presenter = None
        self.metrics_service = type(
            "M", (), {"on_metrics_calculated": lambda self, _v: None}
        )()
        self._unification_task_id = 0
        self.finished_toasts: list = []

    def _cancel_pending_unification(self, *_args, **_kwargs):
        pass

    def _update_image_slot(self, image_number, *, image=None, path=None, is_full_res=False, is_preview=False):
        document = self.store.get_session_state_slot("document")
        if is_full_res and image is not None:
            setattr(document, f"full_res_image{image_number}", image)
        if is_preview and image is not None:
            setattr(document, f"preview_image{image_number}", image)

    def _mark_full_res_ready(self, image_number):
        pass

    def _finish_loading_toast(self, image_number):
        self.finished_toasts.append(image_number)


def _single_slot_document(path: str):
    img = Image.new("RGBA", (4, 4), "red")
    document = DocumentModel(
        image_list1=[ImageItem(image=None, path=path, display_name=path)],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
        image1_path=path,
        image2_path=None,
    )
    document.full_res_image1 = img
    return document


def test_trigger_preview_unification_finishes_toast_for_unpaired_slot():
    document = _single_slot_document("only1.png")
    store = _Store(document)
    controller = _FakeController(store)

    loading.trigger_preview_unification(controller, 1)

    assert controller.finished_toasts == [1], (
        "loading a single slot must close its own loading toast once its "
        "full-res decode is done, since unify (and the pyramid build that "
        "normally closes the toast) will never run without a paired image"
    )
    assert controller.thread_pool.started == []


def test_handle_full_image_loaded_finishes_toast_for_unpaired_slot(monkeypatch):
    document = _single_slot_document("only1.png")
    store = _Store(document)
    controller = _FakeController(store)

    deferred = []
    monkeypatch.setattr(
        loading,
        "QTimer",
        type(
            "QTimer",
            (),
            {"singleShot": staticmethod(lambda _ms, fn: deferred.append(fn))},
        ),
    )

    img = document.full_res_image1
    document.image_list1[0].image = img

    loading.handle_full_image_loaded(controller, img, "only1.png", 1, 0)
    assert len(deferred) == 1
    deferred[0]()

    assert controller.finished_toasts == [1]
    assert controller.thread_pool.started == []


def test_trigger_preview_unification_does_not_finish_toast_while_own_decode_pending():
    """A fresh preview (no full-res yet) in an otherwise-empty pairing must
    not finish the toast prematurely -- the full-res decode for that slot is
    still in flight."""
    path = "only1.png"
    document = DocumentModel(
        image_list1=[ImageItem(image=None, path=path, display_name=path)],
        image_list2=[],
        current_index1=0,
        current_index2=-1,
        image1_path=path,
        image2_path=None,
    )
    document.preview_image1 = Image.new("RGBA", (4, 4), "red")
    store = _Store(document)
    controller = _FakeController(store)

    loading.trigger_preview_unification(controller, 1)

    assert controller.finished_toasts == []
