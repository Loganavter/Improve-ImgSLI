"""Cross-list move onto an empty side must not stall compare rendering.

Repro: list2 empty; list1 has two images with the last one current/loaded;
move the current item to list2. The remaining list1 item is unloaded
(``item.image is None``). Path-only ``set_current_image`` used to keep the
moved item's pixel store on slot 1, so unify/close could kill slot 2's store
and leave ``unification_in_progress`` stuck with a blank canvas.
"""

from __future__ import annotations

from PIL import Image

from tabs.image_compare.services.playlist_components.list_operations import (
    PlaylistListOperations,
)
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
    def __init__(self):
        self.image1 = None
        self.image2 = None


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
        self.state_changed = type(
            "Sig", (), {"emit": staticmethod(lambda *_a, **_k: None)}
        )()

    def get_session_state_slot(self, name):
        assert name == "document"
        return self.document

    def get_dispatcher(self):
        return None

    def invalidate_geometry_cache(self):
        pass

    def invalidate_render_cache(self):
        pass

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
        self.event_bus = None
        self.diff_service = None
        self.metrics_service = type(
            "M",
            (),
            {"on_metrics_calculated": lambda self, _v: None},
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


def test_move_current_to_empty_list_clears_stale_slot_pixels(tmp_path):
    path_a = str(tmp_path / "a.png")
    path_b = str(tmp_path / "b.png")
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path_a)
    Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(path_b)

    store_b = object()  # stand-in for the live pixel store of B
    document = DocumentModel(
        image_list1=[
            ImageItem(image=None, path=path_a, display_name="a.png"),
            ImageItem(image=store_b, path=path_b, display_name="b.png"),
        ],
        image_list2=[],
        current_index1=1,
        current_index2=-1,
        full_res_image1=store_b,
        image1_path=path_b,
    )
    store = _Store(document)
    controller = _FakeController(store)

    ops = PlaylistListOperations(
        store,
        set_current_image_callback=controller.set_current_image,
    )
    ops.move_item_between_lists(1, 1, 2, 0)

    assert [item.path for item in document.image_list1] == [path_a]
    assert [item.path for item in document.image_list2] == [path_b]
    assert document.current_index1 == 0
    assert document.current_index2 == 0

    # Unloaded A became current on slot 1 — stale B pixels must be gone.
    assert document.image1_path == path_a
    assert document.full_res_image1 is None
    assert document.preview_image1 is None

    # Moved B keeps its store on slot 2; do not close/share it onto slot 1.
    assert document.image2_path == path_b
    assert document.full_res_image2 is store_b

    # Unify must wait until A loads (both sources present).
    assert store.viewport.session_data.render_cache.unification_in_progress is False
    assert len(controller.thread_pool.started) == 1  # async load for A only


def test_failed_unify_result_clears_unification_in_progress():
    document = DocumentModel()
    store = _Store(document)
    store.viewport.session_data.render_cache.unification_in_progress = True
    store.viewport.session_data.render_cache.pending_unification_paths = ("a", "b")
    controller = _FakeController(store)

    loading.on_unified_images_ready(controller, None)

    assert store.viewport.session_data.render_cache.unification_in_progress is False
    assert store.viewport.session_data.render_cache.pending_unification_paths is None
