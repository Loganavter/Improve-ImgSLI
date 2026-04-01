import logging

from PIL import Image
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.events import CoreErrorOccurredEvent
from plugins.analysis.services.cached_diff import CachedDiffService
from resources.translations import tr
from plugins.comparison.use_cases import list_ops, loading, navigation
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class SessionController(QObject):

    error_occurred = pyqtSignal(str)
    image_loaded = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(
        self,
        store,
        thread_pool,
        image_loader,
        playlist_manager,
        metrics_service=None,
        diff_service: CachedDiffService | None = None,
        presenter=None,
        event_bus=None,
    ):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.image_loader = image_loader
        self.playlist_manager = playlist_manager
        self.metrics_service = metrics_service
        self.diff_service = diff_service
        self.presenter = presenter
        self.event_bus = event_bus

        self._unification_task_id = 0

    def _update_image_slot(
        self,
        slot_number: int,
        *,
        image=None,
        path=None,
        emit=True,
        is_preview=False,
        is_full_res=False,
    ):
        doc = self.store.document
        if slot_number == 1:
            if is_full_res:
                doc.full_res_image1 = image
            if is_preview:
                doc.preview_image1 = image
            if path is not None:
                doc.image1_path = path
        else:
            if is_full_res:
                doc.full_res_image2 = image
            if is_preview:
                doc.preview_image2 = image
            if path is not None:
                doc.image2_path = path
        if emit:
            self.store.emit_state_change("document")

    def initialize_app_display(self):
        loading.initialize_app_display(self)

    def _load_image_async(self, path, image_number, index_in_list, target_size=None):
        from shared.image_processing.progressive_loader import (
            load_full_image,
            load_preview_image,
            should_use_progressive_load,
        )
        from shared.image_processing.resize import crop_black_borders

        should_crop = getattr(self.store.settings, "auto_crop_black_borders", True)

        try:
            use_progressive = should_use_progressive_load(path)

            if use_progressive:
                preview = load_preview_image(path, should_crop)
                if preview:
                    return preview, path, image_number, index_in_list, True

                pil_img = load_full_image(path, should_crop)
                return pil_img, path, image_number, index_in_list, False
            else:
                with Image.open(path) as img:
                    img_to_process = img.copy()
                    pil_img = img_to_process.convert("RGBA")

                    if pil_img and should_crop:
                        pil_img = crop_black_borders(pil_img)

                    pil_img.load()
                return pil_img, path, image_number, index_in_list, False
        except Exception as e:
            if self.event_bus:
                self.event_bus.emit(
                    CoreErrorOccurredEvent(
                        f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}"
                    )
                )
            else:
                self.error_occurred.emit(
                    f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}"
                )
            return None, path, image_number, index_in_list, False

    def _cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        if not self.store.viewport.session_data.render_cache.unification_in_progress:
            return False
        pending = self.store.viewport.session_data.render_cache.pending_unification_paths
        if pending and (pending[0] != new_path1 or pending[1] != new_path2):

            self.store.viewport.session_data.render_cache.unification_in_progress = False
            self.store.viewport.session_data.render_cache.pending_unification_paths = None

            self.store.invalidate_geometry_cache()
            return True
        return False

    def _on_image_loaded(self, result):
        if result is None:
            return

        if isinstance(result, tuple) and len(result) == 5:
            pil_img, path, image_number, index_in_list, is_preview = result
        else:
            pil_img, path, image_number, index_in_list = result
            is_preview = False
        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )

        if not pil_img:
            if (
                0 <= index_in_list < len(target_list)
                and target_list[index_in_list].path == path
            ):
                target_list.pop(index_in_list)
                current_app_index = (
                    self.store.document.current_index1
                    if image_number == 1
                    else self.store.document.current_index2
                )
                if index_in_list == current_app_index:
                    self.set_current_image(image_number)
                if self.presenter:
                    self.presenter.ui_batcher.schedule_update("combobox")
            return

        if (
            0 <= index_in_list < len(target_list)
            and target_list[index_in_list].path == path
        ):
            item = target_list[index_in_list]

            if is_preview:
                self._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_preview=True,
                )
                self._load_full_resolution_async(path, image_number, index_in_list)
            else:
                self._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_full_res=True,
                )

            item.image = pil_img

            current_app_index = (
                self.store.document.current_index1
                if image_number == 1
                else self.store.document.current_index2
            )
            if index_in_list == current_app_index:
                if not is_preview:
                    QTimer.singleShot(
                        0,
                        lambda: self.set_current_image(
                            image_number, force_refresh=True
                        ),
                    )
                else:
                    QTimer.singleShot(
                        0,
                        lambda num=image_number: self._trigger_preview_unification(num),
                    )

    def _on_image_loaded_from_worker(self, result):
        self._on_image_loaded(result)

    def _trigger_preview_unification(self, image_number: int):
        loading.trigger_preview_unification(self, image_number)

    def _load_full_resolution_async(self, path, image_number, index_in_list):
        from shared.image_processing.progressive_loader import load_full_image

        should_crop = getattr(self.store.settings, "auto_crop_black_borders", True)

        def load_full_task(path_str, crop_flag):
            img = load_full_image(path_str, crop_flag)
            return img

        worker = GenericWorker(load_full_task, path, should_crop)
        worker.signals.result.connect(
            lambda full_img: self._on_full_image_loaded(
                full_img, path, image_number, index_in_list
            )
        )
        worker.signals.error.connect(
            lambda err: logger.error(f"Failed to load full resolution: {err}")
        )
        self.thread_pool.start(worker)

    def _on_full_image_loaded(self, full_img, path, image_number, index_in_list):
        loading.handle_full_image_loaded(self, full_img, path, image_number, index_in_list)

    def load_images_from_paths(self, file_paths: list[str], image_number: int):
        loading.load_images_from_paths(self, file_paths, image_number)

    def _invalidate_image_canvas_render_state(self, clear_magnifier: bool = False):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "invalidate_canvas_render_state"):
            presenter.invalidate_canvas_render_state(clear_magnifier=clear_magnifier)

    def _schedule_image_canvas_update(self):
        presenter = getattr(self, "presenter", None)
        if presenter and hasattr(presenter, "schedule_canvas_update"):
            QTimer.singleShot(0, presenter.schedule_canvas_update)

    def set_current_image(
        self, image_number: int, force_refresh: bool = False, emit_signal: bool = True
    ):
        loading.set_current_image(self, image_number, force_refresh, emit_signal)

    def _unify_images_worker_task(
        self,
        img1: Image.Image,
        img2: Image.Image,
        path1: str | None,
        path2: str | None,
        display_resolution_limit: int,
        task_id: int,
    ):
        try:
            from shared.image_processing.resize import resize_images_processor

            u1, u2 = resize_images_processor(img1, img2)

            cached_u1, cached_u2 = self._create_display_cache(
                u1, u2, display_resolution_limit
            )

            return u1, u2, cached_u1, cached_u2, path1, path2, task_id
        except Exception as e:
            logger.error(f"Failed to unify images: {e}")
            return None

    def _create_display_cache(self, u1: Image.Image, u2: Image.Image, limit: int):
        try:
            w, h = u1.size
            if limit > 0 and max(w, h) > limit:
                if w > h:
                    new_w, new_h = limit, int(h * limit / w)
                else:
                    new_h, new_w = limit, int(w * limit / h)
                cached_u1 = u1.resize((new_w, new_h), Image.Resampling.LANCZOS)
                cached_u2 = u2.resize((new_w, new_h), Image.Resampling.LANCZOS)
            else:
                cached_u1, cached_u2 = u1, u2
            return cached_u1, cached_u2
        except Exception as e:
            logger.error(f"Failed to create display cache: {e}")
            return u1, u2

    def _on_unified_images_ready(self, result):
        loading.on_unified_images_ready(self, result)

    def _trigger_metrics_calculation_if_needed(self):
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def _trigger_full_diff_generation(self):
        if self.diff_service is not None:
            self.diff_service.request_generation(optimize_ssim=False)

    def swap_current_images(self):
        list_ops.swap_current_images(self)

    def swap_entire_lists(self):
        list_ops.swap_entire_lists(self)

    def remove_current_image_from_list(self, image_number: int):
        list_ops.remove_current_image_from_list(self, image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        list_ops.remove_specific_image_from_list(self, image_number, index_to_remove)

    def clear_image_list(self, image_number: int):
        list_ops.clear_image_list(self, image_number)

    def reorder_item_in_list(
        self, image_number: int, source_index: int, dest_index: int
    ):
        list_ops.reorder_item_in_list(self, image_number, source_index, dest_index)

    def move_item_between_lists(
        self,
        source_list_num: int,
        source_index: int,
        dest_list_num: int,
        dest_index: int,
    ):
        list_ops.move_item_between_lists(
            self, source_list_num, source_index, dest_list_num, dest_index
        )

    def on_edit_name_changed(self, image_number, new_name):
        list_ops.on_edit_name_changed(self, image_number, new_name)

    def activate_single_image_mode(self, image_number: int):
        navigation.activate_single_image_mode(self, image_number)

    def deactivate_single_image_mode(self):
        navigation.deactivate_single_image_mode(self)

    def increment_rating(self, image_number: int, index: int):
        list_ops.increment_rating(self, image_number, index)

    def decrement_rating(self, image_number: int, index: int):
        list_ops.decrement_rating(self, image_number, index)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        list_ops.set_rating(self, image_number, index_to_set, new_score)

    def on_combobox_changed(self, image_number: int, index: int, scroll_delta: int = 0):
        navigation.on_combobox_changed(self, image_number, index, scroll_delta)

    def on_interpolation_changed(self, index: int):
        navigation.on_interpolation_changed(self, index)
