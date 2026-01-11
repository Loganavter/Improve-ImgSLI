

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PIL import Image
from shared_toolkit.workers import GenericWorker
from resources.translations import tr
from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from core.store import ImageItem
import os
import logging

logger = logging.getLogger("ImproveImgSLI")

class SessionController(QObject):

    error_occurred = pyqtSignal(str)
    image_loaded = pyqtSignal()
    update_requested = pyqtSignal()

    def __init__(self, store, thread_pool, image_loader, playlist_manager, metrics_service=None, presenter=None, event_bus=None):
        super().__init__()
        self.store = store
        self.thread_pool = thread_pool
        self.image_loader = image_loader
        self.playlist_manager = playlist_manager
        self.metrics_service = metrics_service
        self.presenter = presenter
        self.event_bus = event_bus

        self._unification_task_id = 0

    def _update_image_slot(self, slot_number: int, *, image=None, path=None, emit=True, is_preview=False, is_full_res=False):
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
        if self.store.viewport.loaded_image1_paths:
            self.load_images_from_paths(self.store.viewport.loaded_image1_paths, 1)
        if self.store.viewport.loaded_image2_paths:
            self.load_images_from_paths(self.store.viewport.loaded_image2_paths, 2)

        if (
            self.store.viewport.loaded_current_index1 != -1
            and 0
            <= self.store.viewport.loaded_current_index1
            < len(self.store.document.image_list1)
        ):
            self.store.document.current_index1 = self.store.viewport.loaded_current_index1
        elif self.store.document.image_list1:
            self.store.document.current_index1 = 0

        if (
            self.store.viewport.loaded_current_index2 != -1
            and 0
            <= self.store.viewport.loaded_current_index2
            < len(self.store.document.image_list2)
        ):
            self.store.document.current_index2 = self.store.viewport.loaded_current_index2
        elif self.store.document.image_list2:
            self.store.document.current_index2 = 0

        self.set_current_image(1, emit_signal=False)
        self.set_current_image(2, emit_signal=False)

        if self.presenter:
            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution', 'ratings'])
            self.presenter.update_minimum_window_size()

        self.store.state_changed.emit("document")

    def _load_image_async(self, path, image_number, index_in_list, target_size=None):
        from shared.image_processing.progressive_loader import (
            should_use_progressive_load,
            load_preview_image,
            load_full_image
        )
        from shared.image_processing.resize import crop_black_borders

        should_crop = getattr(self.store.settings, 'auto_crop_black_borders', True)

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
                self.event_bus.emit(CoreErrorOccurredEvent(f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}"))
            else:
                self.error_occurred.emit(f"{tr('msg.failed_to_load_image', self.store.settings.current_language)}:\n{path}\n\n{e}")
            return None, path, image_number, index_in_list, False

    def _cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        if not self.store.viewport.unification_in_progress:
            return False
        pending = self.store.viewport.pending_unification_paths
        if pending and (pending[0] != new_path1 or pending[1] != new_path2):

            self.store.viewport.unification_in_progress = False
            self.store.viewport.pending_unification_paths = None

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
                    self.presenter.ui_batcher.schedule_update('combobox')
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
                    QTimer.singleShot(0, lambda: self.set_current_image(image_number, force_refresh=True))
                else:
                    QTimer.singleShot(0, lambda num=image_number: self._trigger_preview_unification(num))

    def _on_image_loaded_from_worker(self, result):
        self._on_image_loaded(result)

    def _trigger_preview_unification(self, image_number: int):
        if self.presenter:
            self.presenter.ui_batcher.schedule_batch_update(['file_names', 'resolution'])

        source1 = self.store.document.full_res_image1 or self.store.document.preview_image1
        source2 = self.store.document.full_res_image2 or self.store.document.preview_image2

        if source1 and source2:
            try:

                self._cancel_pending_unification(self.store.document.image1_path, self.store.document.image2_path)

                if not self.store.document.image1_path or not self.store.document.image2_path:
                    return

                self.store.viewport.unification_in_progress = True
                self.store.viewport.pending_unification_paths = (self.store.document.image1_path, self.store.document.image2_path)

                self._unification_task_id += 1
                current_task_id = self._unification_task_id

                worker = GenericWorker(
                    self._unify_images_worker_task,
                    source1.copy(),
                    source2.copy(),
                    self.store.document.image1_path,
                    self.store.document.image2_path,
                    self.store.viewport.display_resolution_limit,
                    current_task_id
                )
                worker.signals.result.connect(self._on_unified_images_ready)

                self.thread_pool.start(worker, priority=1)
            except Exception:
                self.store.viewport.unification_in_progress = False
                self.metrics_service.on_metrics_calculated(None)
        else:
            self.metrics_service.on_metrics_calculated(None)

        if self.presenter:
            QTimer.singleShot(10, lambda: self.store.state_changed.emit("viewport"))

    def _load_full_resolution_async(self, path, image_number, index_in_list):
        from shared.image_processing.progressive_loader import load_full_image

        should_crop = getattr(self.store.settings, 'auto_crop_black_borders', True)

        def load_full_task(path_str, crop_flag):
            img = load_full_image(path_str, crop_flag)
            return img

        worker = GenericWorker(load_full_task, path, should_crop)
        worker.signals.result.connect(
            lambda full_img: self._on_full_image_loaded(full_img, path, image_number, index_in_list)
        )
        worker.signals.error.connect(
            lambda err: logger.error(f"Failed to load full resolution: {err}")
        )
        self.thread_pool.start(worker)

    def _on_full_image_loaded(self, full_img, path, image_number, index_in_list):
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

            self._update_image_slot(
                image_number,
                image=full_img,
                path=path,
                is_full_res=True,
            )

            current_app_index = (
                self.store.document.current_index1
                if image_number == 1
                else self.store.document.current_index2
            )
            if index_in_list == current_app_index:
                def trigger_unification():
                    source1 = self.store.document.full_res_image1 or self.store.document.preview_image1
                    source2 = self.store.document.full_res_image2 or self.store.document.preview_image2
                    if source1 and source2:
                        self.store.viewport.unification_in_progress = True
                        self.store.viewport.pending_unification_paths = (
                            self.store.document.image1_path,
                            self.store.document.image2_path
                        )

                        self._unification_task_id += 1
                        current_task_id = self._unification_task_id

                        worker = GenericWorker(
                            self._unify_images_worker_task,
                            source1.copy(),
                            source2.copy(),
                            self.store.document.image1_path,
                            self.store.document.image2_path,
                            self.store.viewport.display_resolution_limit,
                            current_task_id
                        )
                        worker.signals.result.connect(self._on_unified_images_ready)
                        self.thread_pool.start(worker, priority=1)
                    else:
                        self.metrics_service.on_metrics_calculated(None)

                QTimer.singleShot(50, trigger_unification)

    def load_images_from_paths(self, file_paths: list[str], image_number: int):
        target_list_ref = (
            self.store.document.image_list1
            if image_number == 1
            else self.store.document.image_list2
        )

        is_new_comparison = len(target_list_ref) == 0

        if is_new_comparison:

            other_image_number = 2 if image_number == 1 else 1
            other_list = (
                self.store.document.image_list1
                if other_image_number == 1
                else self.store.document.image_list2
            )

            if len(other_list) == 0:

                self.store.viewport.unification_in_progress = False
                self.store.viewport.pending_unification_paths = None

                self.store.clear_image_slot_data(1)
                self.store.clear_image_slot_data(2)
                self.store.viewport.image1 = None
                self.store.viewport.image2 = None
                self.store.viewport.display_cache_image1 = None
                self.store.viewport.display_cache_image2 = None
                self.store.viewport.cached_diff_image = None
            else:

                self.store.viewport.unification_in_progress = False
                self.store.viewport.pending_unification_paths = None

                self.store.clear_image_slot_data(image_number)

        load_errors, newly_added_indices = [], []
        current_paths_in_list = {
            entry.path for entry in target_list_ref if entry.path
        }

        for file_path in file_paths:
            if not isinstance(file_path, str) or not file_path:
                load_errors.append(
                    f"{str(file_path)}: {tr('msg.invalid_item_type_or_empty_path', self.store.settings.current_language)}"
                )
                continue
            try:
                normalized_path = os.path.normpath(file_path)
                original_path_for_display = os.path.basename(normalized_path) or "-----"
            except Exception:
                load_errors.append(f"{file_path}: {tr('msg.error_normalizing_path', self.store.settings.current_language)}")
                continue

            if normalized_path in current_paths_in_list:

                try:

                    index = next(i for i, item in enumerate(target_list_ref) if item.path == normalized_path)

                    item = target_list_ref[index]
                    item.image = None

                    doc = self.store.document
                    if image_number == 1:
                        other_path = doc.image2_path
                        cache_key = (normalized_path, other_path)
                    else:
                        other_path = doc.image1_path
                        cache_key = (other_path, normalized_path)

                    cache = self.store.viewport.session_data.unified_image_cache
                    if cache_key in cache:
                        cache.pop(cache_key)
                        logger.info(f"Cache invalidated for key: {cache_key}")

                    if image_number == 1:
                        self.store.document.current_index1 = index
                    else:
                        self.store.document.current_index2 = index

                    QTimer.singleShot(50, lambda num=image_number: self.set_current_image(num))

                    if self.presenter:
                        self.presenter.ui_batcher.schedule_update('combobox')

                except (ValueError, IndexError) as e:
                    logger.error(f"Error handling reload for {normalized_path}: {e}")

            else:

                try:
                    target_list_ref.append(ImageItem(
                        image=None,
                        path=normalized_path,
                        display_name=os.path.splitext(original_path_for_display)[0],
                        rating=0
                    ))
                    current_paths_in_list.add(normalized_path)
                    newly_added_indices.append(len(target_list_ref) - 1)
                except Exception:
                    load_errors.append(
                        f"{original_path_for_display}: {tr('msg.error_processing_path', self.store.settings.current_language)}"
                    )

        if newly_added_indices:
            new_index = newly_added_indices[-1]
            if image_number == 1:
                self.store.document.current_index1 = new_index
            else:
                self.store.document.current_index2 = new_index

            if self.presenter:
                self.presenter.ui_batcher.schedule_update('combobox')

            QTimer.singleShot(50, lambda: self.set_current_image(image_number))

            if self.presenter:
                from toolkit.widgets.composite.unified_flyout import FlyoutMode
                QTimer.singleShot(0, self.presenter.repopulate_flyouts)

                if self.presenter.ui_manager.unified_flyout.mode == FlyoutMode.DOUBLE:
                    QTimer.singleShot(50, lambda: self.presenter.ui_manager.unified_flyout.refreshGeometry(immediate=False))

        if load_errors:
            error_message = tr("msg.some_images_could_not_be_loaded", self.store.settings.current_language) + ":\n\n - " + "\n - ".join(load_errors)
            if self.event_bus:
                self.event_bus.emit(CoreErrorOccurredEvent(error_message))
            else:
                self.error_occurred.emit(error_message)

    def set_current_image(self, image_number: int, force_refresh: bool = False, emit_signal: bool = True):
        target_list = self.store.document.image_list1 if image_number == 1 else self.store.document.image_list2
        current_index = self.store.document.current_index1 if image_number == 1 else self.store.document.current_index2

        if not (0 <= current_index < len(target_list)):

            self.store.clear_image_slot_data(image_number)

            if self.store.viewport.unification_in_progress:

                pending = self.store.viewport.pending_unification_paths
                if pending:
                    current_path = self.store.document.image1_path if image_number == 1 else self.store.document.image2_path
                    if current_path and current_path not in pending:

                        self.store.viewport.unification_in_progress = False
                        self.store.viewport.pending_unification_paths = None

            self.store.emit_state_change("document")
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()
            return

        item = target_list[current_index]
        pil_img = item.image
        path = item.path
        name = item.display_name

        self._update_image_slot(
            image_number,
            image=pil_img,
            path=path,
            is_full_res=bool(pil_img),
            emit=False,
        )

        path1 = self.store.document.image1_path
        path2 = self.store.document.image2_path

        if path1 and path2:
            cache_key = (path1, path2)
            cache = self.store.viewport.session_data.unified_image_cache
            if cache_key in cache:

                cache.move_to_end(cache_key)
                u1, u2 = cache[cache_key]

                self.store.viewport.image1 = u1
                self.store.viewport.image2 = u2
                self.store.viewport.display_cache_image1 = u1
                self.store.viewport.display_cache_image2 = u2
                self.store.viewport.unification_in_progress = False

                self.store.viewport.scaled_image1_for_display = None
                self.store.viewport.scaled_image2_for_display = None

                if emit_signal:
                    self.store.state_changed.emit("document")
                    if self.event_bus:
                        self.event_bus.emit(CoreUpdateRequestedEvent())
                    else:
                        self.update_requested.emit()
                return

        if pil_img is None and path:
            worker = GenericWorker(self._load_image_async, path, image_number, current_index, None)
            worker.signals.result.connect(self._on_image_loaded_from_worker)
            self.thread_pool.start(worker)
        else:
            self._trigger_preview_unification(image_number)

        if emit_signal:
            self.store.state_changed.emit("document")

    def _unify_images_worker_task(self, img1: Image.Image, img2: Image.Image, path1: str | None, path2: str | None, display_resolution_limit: int, task_id: int):
        try:
            from shared.image_processing.resize import resize_images_processor
            u1, u2 = resize_images_processor(img1, img2)

            cached_u1, cached_u2 = self._create_display_cache(u1, u2, display_resolution_limit)

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
        if not result:
            self.metrics_service.on_metrics_calculated(None)
            return
        try:

            if isinstance(result, tuple) and len(result) == 7:
                u1, u2, cached_u1, cached_u2, path1, path2, task_id = result
            elif isinstance(result, tuple) and len(result) == 5:

                u1, u2, path1, path2, task_id = result
                cached_u1, cached_u2 = None, None
            else:

                self.metrics_service.on_metrics_calculated(None)
                return

            if task_id != self._unification_task_id:

                return

            current_paths_now = (self.store.document.image1_path, self.store.document.image2_path)
            if (path1 != current_paths_now[0]) or (path2 != current_paths_now[1]):
                self.store.viewport.unification_in_progress = False

                self.store.invalidate_geometry_cache()
                self.store.emit_state_change("viewport")
                return
            if u1 and u2:

                self.store.viewport.image1 = u1
                self.store.viewport.image2 = u2

                self.store.document.original_image1 = u1
                self.store.document.original_image2 = u2

                self.store.viewport.scaled_image1_for_display = None
                self.store.viewport.scaled_image2_for_display = None

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

                if self.store.viewport.diff_mode != 'off':
                    self._trigger_full_diff_generation()

                try:
                    if self.event_bus:
                        self.event_bus.emit(CoreUpdateRequestedEvent())
                    else:
                        self.update_requested.emit()

                    if self.presenter:
                        self.presenter.ui_batcher.schedule_batch_update(['resolution', 'file_names'])
                except Exception:
                    pass
            else:
                self.store.viewport.unification_in_progress = False
                self.metrics_service.on_metrics_calculated(None)
        except Exception as e:
            logger.error(f"Error in unified images ready handler: {e}")
            self.store.viewport.unification_in_progress = False
            self.metrics_service.on_metrics_calculated(None)

    def _trigger_metrics_calculation_if_needed(self):
        self.metrics_service.trigger_metrics_calculation_if_needed()

    def _trigger_full_diff_generation(self):
        img1 = self.store.document.full_res_image1 or self.store.document.original_image1
        img2 = self.store.document.full_res_image2 or self.store.document.original_image2
        mode = self.store.viewport.diff_mode

        if not img1 or (not img2 and mode != 'edges'):
            return

        worker = GenericWorker(self._generate_diff_map_task, img1, img2, mode)
        worker.signals.result.connect(self._on_diff_map_ready)

        self.thread_pool.start(worker, priority=1)

    def _generate_diff_map_task(self, img1, img2, mode):
        try:
            from plugins.analysis.processing import (
                create_highlight_diff, create_grayscale_diff,
                create_ssim_map, create_edge_map
            )
            from PIL import Image

            target_size = img1.size

            prepared_img2 = img2
            if img2 and img2.size != target_size:
                prepared_img2 = img2.resize(target_size, Image.Resampling.LANCZOS)

            diff_mode_handlers = {
                'edges': lambda: create_edge_map(img1),
                'highlight': lambda: create_highlight_diff(img1, prepared_img2, threshold=10),
                'grayscale': lambda: create_grayscale_diff(img1, prepared_img2),
                'ssim': lambda: create_ssim_map(img1, prepared_img2),
            }

            handler = diff_mode_handlers.get(mode)
            return handler() if handler else None
        except Exception as e:
            return None

    def _on_diff_map_ready(self, diff_image):
        if diff_image:
            self.store.viewport.cached_diff_image = diff_image
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def swap_current_images(self):
        self.playlist_manager.swap_current_images()

    def swap_entire_lists(self):
        self.playlist_manager.swap_entire_lists()

    def remove_current_image_from_list(self, image_number: int):
        self.playlist_manager.remove_current_image_from_list(image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        self.playlist_manager.remove_specific_image_from_list(image_number, index_to_remove)

    def clear_image_list(self, image_number: int):
        self.playlist_manager.clear_image_list(image_number)

    def reorder_item_in_list(self, image_number: int, source_index: int, dest_index: int):
        self.playlist_manager.reorder_item_in_list(image_number, source_index, dest_index)

    def move_item_between_lists(self, source_list_num: int, source_index: int, dest_list_num: int, dest_index: int):
        self.playlist_manager.move_item_between_lists(source_list_num, source_index, dest_list_num, dest_index)

    def on_edit_name_changed(self, image_number, new_name):
        self.playlist_manager.on_edit_name_changed(image_number, new_name)

    def activate_single_image_mode(self, image_number: int):
        if (
            self.store.document.preview_image1
            if image_number == 1
            else self.store.document.preview_image2
        ):
            self.store.viewport.showing_single_image_mode = image_number
        else:
            self.store.viewport.showing_single_image_mode = 0
        self.store.emit_state_change("viewport")

    def deactivate_single_image_mode(self):
        self.store.viewport.showing_single_image_mode = 0
        self.store.emit_state_change("viewport")

    def increment_rating(self, image_number: int, index: int):
        self.playlist_manager.increment_rating(image_number, index)

    def decrement_rating(self, image_number: int, index: int):
        self.playlist_manager.decrement_rating(image_number, index)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        self.playlist_manager.set_rating(image_number, index_to_set, new_score)

    def on_combobox_changed(self, image_number: int, index: int, scroll_delta: int = 0):
        doc = self.store.document
        target_list = doc.image_list1 if image_number == 1 else doc.image_list2
        if not target_list: return

        current_idx = doc.current_index1 if image_number == 1 else doc.current_index2

        if index == -1 and scroll_delta != 0:
            step = -1 if scroll_delta > 0 else 1
            new_index = (current_idx + step) % len(target_list)
        else:
            new_index = index

        if 0 <= new_index < len(target_list):
            if image_number == 1:
                self.store.document.current_index1 = new_index
            else:
                self.store.document.current_index2 = new_index

            self.set_current_image(image_number)
            if self.event_bus:
                self.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                self.update_requested.emit()

    def on_interpolation_changed(self, index: int):
        try:
            from shared.image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False
        try:
            from core.constants import AppConstants
            all_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
            visible_keys = [k for k in all_keys if k != "EWA_LANCZOS" or WAND_AVAILABLE]
            if 0 <= index < len(visible_keys):
                selected_method_key = visible_keys[index]
                if self.store.viewport.interpolation_method != selected_method_key:
                    self.store.viewport.interpolation_method = selected_method_key
                    self.store.emit_state_change("viewport")
                    if self.presenter:
                        self.presenter._update_interpolation_combo_box_ui()

                    if self.presenter and hasattr(self.presenter, 'ui_manager'):
                        ui_manager = self.presenter.ui_manager
                        if hasattr(ui_manager, '_settings_dialog') and ui_manager._settings_dialog:
                            ui_manager._settings_dialog.update_main_interpolation(selected_method_key)
        except Exception:
            pass
