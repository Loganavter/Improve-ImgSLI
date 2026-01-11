

import logging
import os
from collections import OrderedDict
from typing import Optional, Tuple

from PIL import Image
from PyQt6.QtCore import QTimer

from shared.image_processing.progressive_loader import (
    should_use_progressive_load,
    load_preview_image,
    load_full_image,
)
from shared.image_processing.resize import resize_images_processor, crop_black_borders
from shared_toolkit.workers import GenericWorker
from core.store import ImageItem

logger = logging.getLogger("ImproveImgSLI")

class ImageLoaderService:

    def __init__(self, store, main_controller):
        self.store = store
        self.main_controller = main_controller

    def load_image_async(self, path: str, image_number: int, index_in_list: int, target_size=None):
        try:
            use_progressive = should_use_progressive_load(path)

            if use_progressive:
                preview = load_preview_image(path, self.store.settings.auto_crop_black_borders)
                if preview:
                    return preview, path, image_number, index_in_list, True

                pil_img = load_full_image(path, self.store.settings.auto_crop_black_borders)
                return pil_img, path, image_number, index_in_list, False
            else:
                with Image.open(path) as img:
                    img_to_process = img.copy()
                    pil_img = img_to_process.convert("RGBA")

                    if self.store.settings.auto_crop_black_borders:
                        try:
                            pil_img = crop_black_borders(pil_img)
                        except Exception as e:
                            logger.error(f"Auto-crop failed for {path}: {e}")

                    pil_img.load()
                return pil_img, path, image_number, index_in_list, False
        except Exception as e:

            if self.main_controller:
                from resources.translations import tr
                self.main_controller.error_occurred.emit(f"{tr('msg.failed_to_load_image', self.main_controller.store.settings.current_language)}:\n{path}\n\n{e}")
            return None, path, image_number, index_in_list, False

    def load_full_resolution_async(self, path: str, image_number: int, index_in_list: int):
        def load_full_task(path_str):
            return load_full_image(path_str, self.store.settings.auto_crop_black_borders)

        worker = GenericWorker(load_full_task, path)
        worker.signals.result.connect(
            lambda full_img: self.on_full_image_loaded(full_img, path, image_number, index_in_list)
        )
        worker.signals.error.connect(
            lambda err: logger.error(f"Failed to load full resolution: {err}")
        )
        if self.main_controller:
            self.main_controller.thread_pool.start(worker)

    def on_full_image_loaded(self, full_img: Optional[Image.Image], path: str, image_number: int, index_in_list: int):
        if not full_img:
            return

        target_list = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )

        if (
            0 <= index_in_list < len(target_list)
            and target_list[index_in_list].path == path
        ):
            item = target_list[index_in_list]
            item.image = full_img

            if image_number == 1:

                self.store.document.original_image1 = full_img
                self.store.document.full_res_image1 = full_img
                self.store.document.full_res_ready1 = True
                self.store.document.preview_image1 = None
                self.store.document.preview_ready1 = False
            else:

                self.store.document.original_image2 = full_img
                self.store.document.full_res_image2 = full_img
                self.store.document.full_res_ready2 = True
                self.store.document.preview_image2 = None
                self.store.document.preview_ready2 = False

            current_app_index = (
                self.store.document.current_index1
                if image_number == 1
                else self.store.document.current_index2
            )
            if index_in_list == current_app_index:
                self.store.set_current_image_data(image_number, full_img, path, item.display_name)

                def trigger_unification():
                    source1 = self.store.document.full_res_image1 or self.store.document.original_image1
                    source2 = self.store.document.full_res_image2 or self.store.document.original_image2
                    if source1 and source2:
                        self.store.viewport.unification_in_progress = True
                        self.store.viewport.pending_unification_paths = (
                            self.store.document.image1_path,
                            self.store.document.image2_path
                        )

                        worker = GenericWorker(
                            self.unify_images_worker_task,
                            source1.copy(),
                            source2.copy(),
                            self.store.document.image1_path,
                            self.store.document.image2_path,
                            self.store.viewport.display_resolution_limit,
                        )
                        worker.signals.result.connect(self.on_unified_images_ready)
                        if self.main_controller:
                            self.main_controller.thread_pool.start(worker, priority=1)
                    else:

                        if hasattr(self.store, '_on_metrics_calculated'):
                            self.store._on_metrics_calculated(None)

                QTimer.singleShot(50, trigger_unification)

    def unify_images_worker_task(self, img1: Image.Image, img2: Image.Image,
                                 path1: Optional[str], path2: Optional[str],
                                 display_resolution_limit: int):
        """Worker task to unify two images to the same size."""
        try:
            u1, u2 = resize_images_processor(img1, img2)
            cached_u1, cached_u2 = self.create_display_cache(u1, u2, display_resolution_limit)
            return u1, u2, cached_u1, cached_u2, path1, path2
        except Exception as e:
            logger.error(f"Failed to unify images: {e}")
            return None

    def create_display_cache(self, u1: Image.Image, u2: Image.Image, limit: int):
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

    def on_unified_images_ready(self, result):
        if not result:
            self._trigger_metrics_calculation_if_needed()
            return
        try:
            if isinstance(result, tuple) and len(result) == 6:
                u1, u2, cached_u1, cached_u2, path1, path2 = result
            elif isinstance(result, tuple) and len(result) == 4:
                u1, u2, path1, path2 = result
                cached_u1, cached_u2 = None, None
            else:
                self._trigger_metrics_calculation_if_needed()
                return

            try:
                current_paths_now = (self.store.document.image1_path, self.store.document.image2_path)
                if (path1 != current_paths_now[0]) or (path2 != current_paths_now[1]):
                    self.store.viewport.unification_in_progress = False

                    self.store.invalidate_geometry_cache()
                    return
            except Exception:
                pass
            if u1 and u2:
                self.store.viewport.image1 = u1
                self.store.viewport.image2 = u2

                if cached_u1 is not None and cached_u2 is not None:

                    self.store.viewport.display_cache_image1 = cached_u1
                    self.store.viewport.display_cache_image2 = cached_u2

                    current_cache_params = (
                        id(u1),
                        id(u2),
                        self.store.viewport.display_resolution_limit,
                    )
                    self.store.viewport.last_display_cache_params = current_cache_params

                try:
                    cache_key = (path1, path2)
                    cache = self.store.viewport.session_data.unified_image_cache

                    if not isinstance(cache, OrderedDict):
                        cache = OrderedDict(cache)
                        self.store.viewport.session_data.unified_image_cache = cache

                    if cache_key in cache:
                        cache.move_to_end(cache_key)

                    cache[cache_key] = (u1, u2)

                    MAX_UNIFIED_CACHE_SIZE = 20
                    while len(cache) > MAX_UNIFIED_CACHE_SIZE:
                        cache.popitem(last=False)
                except Exception:
                    pass

                self.store.viewport.unification_in_progress = False

                self._trigger_metrics_calculation_if_needed()
                try:
                    if self.main_controller:
                        self.main_controller.update_requested.emit()
                except Exception:
                    pass
            else:
                self.store.viewport.unification_in_progress = False
                self._trigger_metrics_calculation_if_needed()
        except Exception as e:
            logger.error(f"Error in unified images ready handler: {e}")
            self.store.viewport.unification_in_progress = False
            self._trigger_metrics_calculation_if_needed()

    def _trigger_metrics_calculation_if_needed(self):

        if hasattr(self.store, '_trigger_metrics_calculation_if_needed'):
            self.store._trigger_metrics_calculation_if_needed()
        else:

            self.store.state_changed.emit()

    def cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        if not self.store.viewport.unification_in_progress:
            return False
        pending = self.store.viewport.pending_unification_paths
        if pending and (pending[0] != new_path1 or pending[1] != new_path2):
            return True
        return False

    def trigger_preview_unification(self, image_number: int):
        if hasattr(self.store, 'presenter') and self.store.presenter:
            self.store.presenter.ui_batcher.schedule_batch_update(['file_names', 'resolution'])

        source1 = self.store.document.full_res_image1 or self.store.document.original_image1
        source2 = self.store.document.full_res_image2 or self.store.document.original_image2

        if source1 and source2:
            try:
                if self.cancel_pending_unification(self.store.document.image1_path, self.store.document.image2_path):
                    pass

                self.store.viewport.unification_in_progress = True
                self.store.viewport.pending_unification_paths = (self.store.document.image1_path, self.store.document.image2_path)

                worker = GenericWorker(
                    self.unify_images_worker_task,
                    source1.copy(),
                    source2.copy(),
                    self.store.document.image1_path,
                    self.store.document.image2_path,
                    self.store.viewport.display_resolution_limit,
                )
                worker.signals.result.connect(self.on_unified_images_ready)

                if self.main_controller:
                    self.main_controller.thread_pool.start(worker, priority=1)
            except Exception:
                self.store.viewport.unification_in_progress = False
                self._trigger_metrics_calculation_if_needed()
        else:
            self._trigger_metrics_calculation_if_needed()

        if hasattr(self.store, 'presenter') and self.store.presenter:
            QTimer.singleShot(10, lambda: self.store.state_changed.emit())
