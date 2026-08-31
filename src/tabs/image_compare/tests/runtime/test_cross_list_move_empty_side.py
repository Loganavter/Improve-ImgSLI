"""Cross-list move onto an empty side must not stall compare rendering.

Repro: list2 empty; list1 has two images with the last one current/loaded;
move the current item to list2. The remaining list1 item is unloaded.
PipelineCache is single source — check image1_path + pipeline peek.
"""

from __future__ import annotations

from PIL import Image

from core.state_management.dispatcher import Dispatcher
from core.state_management.slot_reducers import register_state_slot_reducer
from core.store import Store
from core.store_viewport import ViewportState
from tabs.image_compare.bootstrap_reducers import register_state_slot_reducer as _  # noqa: F401 — ensures reducers registered
import tabs.image_compare.bootstrap_reducers  # noqa: F401
from tabs.image_compare.pipeline.cache import _pixel_key

from tabs.image_compare.services.playlist_components.list_operations import (
    PlaylistListOperations,
)
from tabs.image_compare.state.actions import PutPixelAction
from tabs.image_compare.state.document import DocumentModel, ImageItem
from tabs.image_compare.use_cases import loading


def _make_store(document: DocumentModel) -> Store:
    from core.store_viewport import SessionData
    from tabs.image_compare.state.models import ImageSessionState, RenderCacheState

    store = Store()
    # ensure image_compare session
    store.create_workspace_session(session_type="image_compare", activate=True)
    store.set_session_state_slot("document", document)
    # init session_data for image_compare (Store default is None)
    store.viewport.session_data = SessionData(image_state=ImageSessionState(), render_cache=RenderCacheState())
    # state_changed signal for PlaylistListOperations
    store.state_changed = type("Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)})()
    # ensure dispatcher
    store.set_dispatcher(Dispatcher(store))
    return store


class _ThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker, priority=0):
        self.started.append(worker)


class _PipelineWrapper:
    def __init__(self, store: Store):
        self._store = store
        self._inflight: dict = {}
        self.cache = self

    def peek(self, path: str):
        return _peek_pipeline(self._store, path)

    def peek_preview(self, path: str):
        ps = self._store.get_session_state_slot("pipeline")
        if ps is None or not path:
            return None
        try:
            from tabs.image_compare.pipeline.cache import _preview_key

            k = _preview_key(path, None, None)
            v = ps.preview.get(k)
            if v is not None:
                return v
        except Exception:
            pass
        return None

    def evict(self, path: str):
        try:
            ps = self._store.get_session_state_slot("pipeline")
            if ps is not None:
                import os

                norm = os.path.normpath(path)
                for kk in list(ps.pixel.keys()):
                    if kk[0] == norm:
                        ps.pixel.pop(kk, None)
        except Exception:
            pass


class _FakeController:
    def __init__(self, store: Store):
        self.store = store
        self.thread_pool = _ThreadPool()
        self.pipeline = _PipelineWrapper(store)
        self._pipeline_cache = self.pipeline
        self.presenter = None
        self.event_bus = None
        self.diff_service = None
        self.metrics_service = type(
            "M",
            (),
            {"on_metrics_calculated": lambda self, _v: None},
        )()

    def _invalidate_image_canvas_render_state(self, clear_overlay_state=False):
        pass

    def _schedule_image_canvas_update(self):
        pass

    def _trigger_preview_unification(self, image_number: int):
        loading.trigger_preview_unification(self, image_number)

    def _load_image_async(self, path, image_number, index_in_list, target_size=None):
        return None, path, image_number, index_in_list, False

    def _on_image_loaded_from_worker(self, result):
        pass

    def _cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        return False

    def set_current_image(
        self, image_number: int, force_refresh: bool = False, emit_signal: bool = True
    ):
        loading.set_current_image(self, image_number, force_refresh, emit_signal)


def _peek_pipeline(store: Store, path: str):
    ps = store.get_session_state_slot("pipeline")
    if ps is None or not path:
        return None
    try:
        k = _pixel_key(path, None, None)
        v = ps.pixel.get(k)
        if v is not None:
            return v
    except Exception:
        pass
    try:
        import os

        norm = os.path.normpath(path)
        for kk, vv in ps.pixel.items():
            if kk[0] == norm:
                return vv
    except Exception:
        pass
    return None


def test_move_current_to_empty_list_clears_stale_slot_pixels(tmp_path):
    path_a = str(tmp_path / "a.png")
    path_b = str(tmp_path / "b.png")
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path_a)
    Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(path_b)

    store_b = object()  # stand-in for the live pixel store of B
    document = DocumentModel(
        image_list1=[
            ImageItem(path=path_a, display_name="a.png"),
            ImageItem(path=path_b, display_name="b.png"),
        ],
        image_list2=[],
        current_index1=1,
        current_index2=-1,
    )
    store = _make_store(document)
    # put pipeline cache for B (single source)
    store.transact([PutPixelAction(path=path_b, store=store_b)], scope="pipeline")

    controller = _FakeController(store)

    ops = PlaylistListOperations(
        store,
        set_current_image_callback=controller.set_current_image,
    )
    ops.move_item_between_lists(1, 1, 2, 0)

    doc = store.get_session_state_slot("document")
    assert [item.path for item in doc.image_list1] == [path_a]
    assert [item.path for item in doc.image_list2] == [path_b]
    assert doc.current_index1 == 0
    assert doc.current_index2 == 0

    # Unloaded A became current on slot 1 — pipeline cache for A is miss, B stays on slot 2
    assert doc.image1_path == path_a
    assert _peek_pipeline(store, path_a) is None
    assert doc.image2_path == path_b
    assert _peek_pipeline(store, path_b) is store_b

    # Unify must wait until A loads (both sources present).
    assert store.viewport.session_data.render_cache.unification_in_progress is False
    assert len(controller.thread_pool.started) == 1  # async load for A only


def test_failed_unify_result_clears_unification_in_progress(tmp_path):
    document = DocumentModel()
    store = _make_store(document)
    store.viewport.session_data.render_cache.unification_in_progress = True
    store.viewport.session_data.render_cache.pending_unification_paths = ("a", "b")
    controller = _FakeController(store)

    loading.on_unified_images_ready(controller, None)

    assert store.viewport.session_data.render_cache.unification_in_progress is False
    assert store.viewport.session_data.render_cache.pending_unification_paths is None
