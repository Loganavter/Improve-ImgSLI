import io
import logging
import os
import tempfile
import time
import urllib.request

from PIL import Image
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.app_state import AppState
from core.constants import AppConstants
from core.settings import SettingsManager
from image_processing.resize import resize_images_processor
from resources.translations import tr
from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

class MainController:
    def __init__(
        self, app_state: AppState, app_instance_ref, settings_manager: SettingsManager
    ):
        self.app_state = app_state
        self.app = app_instance_ref
        self.settings_manager = settings_manager
        self.presenter = None
        self._paste_dialog = None

    def set_presenter(self, presenter_ref):
        self.presenter = presenter_ref

    def initialize_app_display(self):
        if self.app_state.loaded_image1_paths:
            self.load_images_from_paths(self.app_state.loaded_image1_paths, 1)
        if self.app_state.loaded_image2_paths:
            self.load_images_from_paths(self.app_state.loaded_image2_paths, 2)

        if (
            self.app_state.loaded_current_index1 != -1
            and 0
            <= self.app_state.loaded_current_index1
            < len(self.app_state.image_list1)
        ):
            self.app_state.current_index1 = self.app_state.loaded_current_index1
        elif self.app_state.image_list1:
            self.app_state.current_index1 = 0

        if (
            self.app_state.loaded_current_index2 != -1
            and 0
            <= self.app_state.loaded_current_index2
            < len(self.app_state.image_list2)
        ):
            self.app_state.current_index2 = self.app_state.loaded_current_index2
        elif self.app_state.image_list2:
            self.app_state.current_index2 = 0

        self.set_current_image(1, emit_signal=False)
        self.set_current_image(2, emit_signal=False)

        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution', 'ratings'])
            self.presenter.update_minimum_window_size()

        self.app_state.stateChanged.emit()

    def _load_image_async(self, path, image_number, index_in_list, target_size=None):
        """
        Загружает изображение. Если используется прогрессивная загрузка, сначала возвращает preview.
        """
        from image_processing.progressive_loader import (
            should_use_progressive_load,
            load_preview_image,
            load_full_image
        )

        try:

            use_progressive = should_use_progressive_load(path)

            if use_progressive:

                preview = load_preview_image(path)
                if preview:
                    return preview, path, image_number, index_in_list, True

                pil_img = load_full_image(path)
                return pil_img, path, image_number, index_in_list, False
            else:

                with Image.open(path) as img:
                    img_to_process = img.copy()
                    pil_img = img_to_process.convert("RGBA")
                    pil_img.load()
                return pil_img, path, image_number, index_in_list, False
        except Exception as e:
            self.app._worker_error_signal.emit(f"Failed to load image:\n{path}\n\n{e}")
            return None, path, image_number, index_in_list, False

    def _cancel_pending_unification(self, new_path1: str, new_path2: str) -> bool:
        """Проверяет, нужно ли отменить текущую унификацию"""
        if not self.app_state._unification_in_progress:
            return False
        pending = self.app_state._pending_unification_paths
        if pending and (pending[0] != new_path1 or pending[1] != new_path2):
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
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )

        if not pil_img:
            if (
                0 <= index_in_list < len(target_list)
                and target_list[index_in_list][1] == path
            ):
                target_list.pop(index_in_list)
                current_app_index = (
                    self.app_state.current_index1
                    if image_number == 1
                    else self.app_state.current_index2
                )
                if index_in_list == current_app_index:
                    self.set_current_image(image_number)
                if self.presenter:
                    self.presenter.ui_batcher.schedule_update('combobox')
            return

        if (
            0 <= index_in_list < len(target_list)
            and target_list[index_in_list][1] == path
        ):
            _, _, name, score = target_list[index_in_list]

            if is_preview:

                if image_number == 1:
                    self.app_state._preview_image1 = pil_img
                    self.app_state._preview_ready1 = True

                    self.app_state._original_image1 = pil_img
                else:
                    self.app_state._preview_image2 = pil_img
                    self.app_state._preview_ready2 = True
                    self.app_state._original_image2 = pil_img

                self._load_full_resolution_async(path, image_number, index_in_list)
            else:

                if image_number == 1:
                    self.app_state._original_image1 = pil_img
                    self.app_state._preview_image1 = None
                    self.app_state._preview_ready1 = False
                    self.app_state._full_res_ready1 = True
                else:
                    self.app_state._original_image2 = pil_img
                    self.app_state._preview_image2 = None
                    self.app_state._preview_ready2 = False
                    self.app_state._full_res_ready2 = True

            target_list[index_in_list] = (pil_img, path, name, score)

            current_app_index = (
                self.app_state.current_index1
                if image_number == 1
                else self.app_state.current_index2
            )
            if index_in_list == current_app_index:
                if not is_preview:

                    QTimer.singleShot(0, lambda: self.set_current_image(image_number, force_refresh=True))
                else:

                    if image_number == 1:
                        self.app_state.set_current_image_data(image_number, pil_img, path, name)
                    else:
                        self.app_state.set_current_image_data(image_number, pil_img, path, name)

                    QTimer.singleShot(0, lambda num=image_number: self._trigger_preview_unification(num))

    def _trigger_preview_unification(self, image_number: int):
        """Легкая унификация для preview изображений без блокировки UI."""

        if self.presenter:
            self.presenter.ui_batcher.schedule_batch_update(['file_names', 'resolution'])

        source1 = self.app_state.full_res_image1 or self.app_state.original_image1
        source2 = self.app_state.full_res_image2 or self.app_state.original_image2

        if source1 and source2:
            try:

                if self._cancel_pending_unification(self.app_state.image1_path, self.app_state.image2_path):
                    pass

                self.app_state._unification_in_progress = True
                self.app_state._pending_unification_paths = (self.app_state.image1_path, self.app_state.image2_path)

                worker = GenericWorker(
                    self._unify_images_worker_task,
                    source1.copy(),
                    source2.copy(),
                    self.app_state.image1_path,
                    self.app_state.image2_path,
                    self.app_state.display_resolution_limit,
                )
                worker.signals.result.connect(self._on_unified_images_ready)

                self.app.thread_pool.start(worker, priority=1)
            except Exception:
                self.app_state._unification_in_progress = False
                self._on_metrics_calculated(None)
        else:
            self._on_metrics_calculated(None)

        if self.presenter:
            QTimer.singleShot(10, lambda: self.app_state.stateChanged.emit())

    def _load_full_resolution_async(self, path, image_number, index_in_list):
        """Загружает полное разрешение изображения в фоне."""
        from image_processing.progressive_loader import load_full_image
        from shared_toolkit.workers import GenericWorker

        def load_full_task(path_str):
            return load_full_image(path_str)

        worker = GenericWorker(load_full_task, path)
        worker.signals.result.connect(
            lambda full_img: self._on_full_image_loaded(full_img, path, image_number, index_in_list)
        )
        worker.signals.error.connect(
            lambda err: logger.error(f"Failed to load full resolution: {err}")
        )
        self.app.thread_pool.start(worker)

    def _on_full_image_loaded(self, full_img, path, image_number, index_in_list):
        """Обработчик загрузки полного разрешения."""
        if not full_img:
            return

        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )

        if (
            0 <= index_in_list < len(target_list)
            and target_list[index_in_list][1] == path
        ):
            _, _, name, score = target_list[index_in_list]
            target_list[index_in_list] = (full_img, path, name, score)

            if image_number == 1:
                self.app_state._original_image1 = full_img
                self.app_state._full_res_image1 = full_img
                self.app_state._full_res_ready1 = True
                self.app_state._preview_image1 = None
                self.app_state._preview_ready1 = False
            else:
                self.app_state._original_image2 = full_img
                self.app_state._full_res_image2 = full_img
                self.app_state._full_res_ready2 = True
                self.app_state._preview_image2 = None
                self.app_state._preview_ready2 = False

            current_app_index = (
                self.app_state.current_index1
                if image_number == 1
                else self.app_state.current_index2
            )
            if index_in_list == current_app_index:

                self.app_state.set_current_image_data(image_number, full_img, path, name)

                def trigger_unification():
                    source1 = self.app_state.full_res_image1 or self.app_state.original_image1
                    source2 = self.app_state.full_res_image2 or self.app_state.original_image2
                    if source1 and source2:
                        self.app_state._unification_in_progress = True
                        self.app_state._pending_unification_paths = (
                            self.app_state.image1_path,
                            self.app_state.image2_path
                        )

                        worker = GenericWorker(
                            self._unify_images_worker_task,
                            source1.copy(),
                            source2.copy(),
                            self.app_state.image1_path,
                            self.app_state.image2_path,
                            self.app_state.display_resolution_limit,
                        )
                        worker.signals.result.connect(self._on_unified_images_ready)
                        self.app.thread_pool.start(worker, priority=1)
                    else:
                        self._on_metrics_calculated(None)

                QTimer.singleShot(50, trigger_unification)

    def load_images_from_paths(self, file_paths: list[str], image_number: int):
        target_list_ref = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        load_errors, newly_added_indices = [], []
        current_paths_in_list = {
            entry[1] for entry in target_list_ref if len(entry) > 1 and entry[1]
        }

        for file_path in file_paths:
            if not isinstance(file_path, str) or not file_path:
                load_errors.append(
                    f"{str(file_path)}: {tr('Invalid item type or empty path', self.app_state.current_language)}"
                )
                continue
            try:
                normalized_path = os.path.normpath(file_path)
                original_path_for_display = os.path.basename(normalized_path) or "-----"
            except Exception:
                load_errors.append(f"{file_path}: {tr('Error normalizing path', self.app_state.current_language)}")
                continue

            if normalized_path in current_paths_in_list:
                continue

            try:
                target_list_ref.append((None, normalized_path, os.path.splitext(original_path_for_display)[0], 0))
                current_paths_in_list.add(normalized_path)
                newly_added_indices.append(len(target_list_ref) - 1)
            except Exception:
                load_errors.append(
                    f"{original_path_for_display}: {tr('Error processing path', self.app_state.current_language)}"
                )

        if newly_added_indices:
            new_index = newly_added_indices[-1]
            if image_number == 1:
                self.app_state.current_index1 = new_index
            else:
                self.app_state.current_index2 = new_index

            if self.presenter:
                self.presenter.ui_batcher.schedule_update('combobox')

            self.set_current_image(image_number)

            if self.presenter:
                from ui.widgets.composite.unified_flyout import FlyoutMode
                QTimer.singleShot(0, self.presenter.repopulate_flyouts)
                if self.presenter.ui_manager.unified_flyout.mode == FlyoutMode.DOUBLE:
                    QTimer.singleShot(50, self.presenter.ui_manager.unified_flyout.updateGeometryInDoubleMode)

        if load_errors:
            QMessageBox.warning(
                self.app,
                tr("Error Loading Images", self.app_state.current_language),
                tr("Some images could not be loaded:", self.app_state.current_language)
                + "\n\n - "
                + "\n - ".join(load_errors),
            )

    def on_interpolation_changed(self, index: int):
        try:
            from image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False
        try:
            all_keys = list(AppConstants.INTERPOLATION_METHODS_MAP.keys())
            visible_keys = [k for k in all_keys if k != "EWA_LANCZOS" or WAND_AVAILABLE]
            if 0 <= index < len(visible_keys):
                selected_method_key = visible_keys[index]
                self.app_state.interpolation_method = selected_method_key
                if self.presenter:
                    self.presenter._update_interpolation_combo_box_ui()
        except Exception:
            pass

    def update_magnifier_size_relative(self, relative_size: float):
        self.app_state.magnifier_size_relative = relative_size

    def update_capture_size_relative(self, relative_size: float):
        self.app_state.capture_size_relative = relative_size

        current_pos = self.app_state.capture_position_relative
        if not self.app_state.image1:
            return

        unified_w, unified_h = self.app_state.image1.size
        if unified_w <= 0 or unified_h <= 0:
            return

        unified_ref_dim = min(unified_w, unified_h)
        capture_size_px = self.app_state.capture_size_relative * unified_ref_dim
        radius_rel_x = (capture_size_px / 2.0) / unified_w if unified_w > 0 else 0
        radius_rel_y = (capture_size_px / 2.0) / unified_h if unified_h > 0 else 0
        clamped_rel_x = max(radius_rel_x, min(current_pos.x(), 1.0 - radius_rel_x))
        clamped_rel_y = max(radius_rel_y, min(current_pos.y(), 1.0 - radius_rel_y))
        new_clamped_pos = QPointF(clamped_rel_x, clamped_rel_y)
        if new_clamped_pos != current_pos:
            self.app_state.capture_position_relative = new_clamped_pos

    def update_movement_speed(self, speed: float):
        self.app_state.movement_speed_per_sec = speed

    def set_current_image(self, image_number: int, force_refresh: bool = False, emit_signal: bool = True):
        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        current_index = (
            self.app_state.current_index1
            if image_number == 1
            else self.app_state.current_index2
        )
        edit_name_widget = (
            self.app.ui.edit_name1 if image_number == 1 else self.app.ui.edit_name2
        )

        new_pil_img, new_path, new_display_name = None, None, None

        if 0 <= current_index < len(target_list):
            pil_img_from_list, path_from_list, display_name_from_list, _ = target_list[
                current_index
            ]
            new_path = path_from_list
            new_display_name = display_name_from_list

            if pil_img_from_list is None and new_path:

                self.app_state.set_current_image_data(image_number, None, new_path, new_display_name)
                if edit_name_widget:
                    edit_name_widget.blockSignals(True)
                    edit_name_widget.setText(new_display_name or "")
                    edit_name_widget.blockSignals(False)
                worker = GenericWorker(
                    self._load_image_async, new_path, image_number, current_index, None
                )
                worker.signals.result.connect(self.app._on_image_loaded_from_worker)
                self.app.thread_pool.start(worker)
                if emit_signal:
                    self.app_state.stateChanged.emit()
                return
            else:
                new_pil_img = pil_img_from_list
        else:

            self.app_state.set_current_image_data(image_number, None, None, None)
            if edit_name_widget:
                edit_name_widget.blockSignals(True)
                edit_name_widget.setText("")
                edit_name_widget.blockSignals(False)
            if emit_signal:
                self.app_state.stateChanged.emit()
            return

        self.app_state.set_current_image_data(
            image_number, new_pil_img, new_path, new_display_name
        )

        if edit_name_widget:
            edit_name_widget.blockSignals(True)
            edit_name_widget.setText(new_display_name or "")
            edit_name_widget.blockSignals(False)

        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['file_names', 'resolution', 'ratings', 'combobox'])

        self.app_state.clear_interactive_caches()

        self.app_state._scaled_image1_for_display = None
        self.app_state._scaled_image2_for_display = None
        self.app_state._cached_scaled_image_dims = None
        self.app_state._display_cache_image1 = None
        self.app_state._display_cache_image2 = None
        self.app_state._last_display_cache_params = None

        setattr(self.app_state, '_last_source1_id', 0)
        setattr(self.app_state, '_last_source2_id', 0)

        source1 = self.app_state.full_res_image1 or self.app_state.original_image1
        source2 = self.app_state.full_res_image2 or self.app_state.original_image2
        if source1 and source2:
            try:

                if self._cancel_pending_unification(self.app_state.image1_path, self.app_state.image2_path):

                    pass

                self.app_state._unification_in_progress = True
                self.app_state._pending_unification_paths = (self.app_state.image1_path, self.app_state.image2_path)

                worker = GenericWorker(
                    self._unify_images_worker_task,
                    source1.copy(),
                    source2.copy(),
                    self.app_state.image1_path,
                    self.app_state.image2_path,
                    self.app_state.display_resolution_limit,
                )
                worker.signals.result.connect(self._on_unified_images_ready)

                self.app.thread_pool.start(worker, priority=1)
            except Exception:
                self.app_state._unification_in_progress = False
                self._on_metrics_calculated(None)
        else:
            self._on_metrics_calculated(None)

        if emit_signal:
            self.app_state.stateChanged.emit()

    def _unify_images_worker_task(self, img1: Image.Image, img2: Image.Image, path1: str | None, path2: str | None, display_resolution_limit: int):
        try:
            from image_processing.resize import resize_images_processor
            u1, u2 = resize_images_processor(img1, img2)

            cached_u1, cached_u2 = self._create_display_cache(u1, u2, display_resolution_limit)

            return u1, u2, cached_u1, cached_u2, path1, path2
        except Exception as e:
            logger.error(f"Failed to unify images: {e}")
            return None

    def _create_display_cache(self, u1: Image.Image, u2: Image.Image, limit: int):
        """Создает уменьшенные версии изображений для кэша предпросмотра"""
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
            self._on_metrics_calculated(None)
            return
        try:

            if isinstance(result, tuple) and len(result) == 6:
                u1, u2, cached_u1, cached_u2, path1, path2 = result

            elif isinstance(result, tuple) and len(result) == 4:
                u1, u2, path1, path2 = result
                cached_u1, cached_u2 = None, None
            else:
                self._on_metrics_calculated(None)
                return

            try:
                current_paths_now = (self.app_state.image1_path, self.app_state.image2_path)
                if (path1 != current_paths_now[0]) or (path2 != current_paths_now[1]):

                    self.app_state._unification_in_progress = False
                    self.app_state.clear_interactive_caches()
                    return
            except Exception:
                pass
            if u1 and u2:

                self.app_state.image1 = u1
                self.app_state.image2 = u2

                if cached_u1 is not None and cached_u2 is not None:
                    self.app_state._display_cache_image1 = cached_u1
                    self.app_state._display_cache_image2 = cached_u2

                    current_cache_params = (
                        id(u1),
                        id(u2),
                        self.app_state.display_resolution_limit,
                    )
                    self.app_state._last_display_cache_params = current_cache_params

                try:
                    cache_key = (path1, path2)
                    if not hasattr(self.app_state, "_unified_image_cache"):
                        self.app_state._unified_image_cache = {}
                        self.app_state._unified_image_cache_keys = []
                    self.app_state._unified_image_cache[cache_key] = (u1, u2)
                    self.app_state._unified_image_cache_keys.append(cache_key)
                    MAX_UNIFIED_CACHE_SIZE = 20
                    if len(self.app_state._unified_image_cache_keys) > MAX_UNIFIED_CACHE_SIZE:
                        key_to_remove = self.app_state._unified_image_cache_keys.pop(0)
                        self.app_state._unified_image_cache.pop(key_to_remove, None)
                except Exception:
                    pass

                self.app_state._unification_in_progress = False

                self._trigger_metrics_calculation_if_needed()
                try:
                    self.app.schedule_update()
                except Exception:
                    pass
            else:
                self.app_state._unification_in_progress = False
                self._on_metrics_calculated(None)
        except Exception as e:
            logger.error(f"Error in unified images ready handler: {e}")
            self.app_state._unification_in_progress = False
            self._on_metrics_calculated(None)

    def _download_images_from_urls(self, urls: list[str], timeout: int = 10):
        downloaded_paths: list[str] = []
        try:
            for url_str in urls:
                try:
                    with urllib.request.urlopen(url_str, timeout=timeout) as response:
                        content_type = response.headers.get_content_type()
                        if content_type and content_type.startswith('image/'):
                            temp_dir = tempfile.gettempdir()
                            timestamp = int(time.time() * 1000)
                            ext = (content_type.split('/')[-1] or 'png').lower()
                            if ext == 'jpeg':
                                ext = 'jpg'
                            temp_filename = f"url_image_{os.getpid()}_{timestamp}.{ext}"
                            image_path = os.path.join(temp_dir, temp_filename)
                            with open(image_path, 'wb') as f:
                                f.write(response.read())
                            downloaded_paths.append(image_path)
                except Exception as e:
                    logger.warning(f"Failed to download image from URL {url_str}: {e}")
            return downloaded_paths
        except Exception as e:
            logger.error(f"Unexpected error during URL downloads: {e}")
            return downloaded_paths

    def _on_urls_downloaded(self, downloaded_paths: list[str], local_paths: list[str]):
        try:
            final_paths = list(local_paths or []) + list(downloaded_paths or [])
            if not final_paths:
                if self.app and hasattr(self.app, 'toast_manager'):
                    self.app.toast_manager.show_toast(
                        tr("Не удалось получить изображения из буфера обмена", self.app_state.current_language),
                        duration=2500
                    )
                return
            self._show_paste_direction_dialog(final_paths)
        except Exception as e:
            logger.error(f"Error handling downloaded URLs: {e}", exc_info=True)
            if self.app and hasattr(self.app, 'toast_manager'):
                self.app.toast_manager.show_toast(
                    tr("Ошибка при обработке загруженных изображений", self.app_state.current_language),
                    duration=2500
                )

    def _calculate_metrics_async(self, calc_psnr: bool, calc_ssim: bool):
        img1 = self.app_state.image1
        img2 = self.app_state.image2
        if not img1 or not img2 or img1.size != img2.size:
            self._on_metrics_calculated(None)
            return

        worker = GenericWorker(self._metrics_worker_task, img1.copy(), img2.copy(), calc_psnr, calc_ssim)
        worker.signals.result.connect(self._on_metrics_calculated)
        self.app.thread_pool.start(worker)

    def _metrics_worker_task(self, img1: Image.Image, img2: Image.Image, calc_psnr: bool, calc_ssim: bool):
        try:
            from image_processing.analysis import calculate_psnr, calculate_ssim
            psnr_val, ssim_val = None, None
            if calc_psnr:
                psnr_val = calculate_psnr(img1, img2)
            if calc_ssim:
                ssim_val = calculate_ssim(img1, img2)
            return psnr_val, ssim_val
        except Exception as e:
            logger.error(f"Failed to calculate metrics: {e}")
            return None

    def _trigger_metrics_calculation_if_needed(self):
        calc_psnr = self.app_state.auto_calculate_psnr
        calc_ssim = self.app_state.auto_calculate_ssim

        if self.app_state.diff_mode == 'ssim':
            calc_ssim = True

        if calc_psnr or calc_ssim:
            self._calculate_metrics_async(calc_psnr=calc_psnr, calc_ssim=calc_ssim)
        else:

            self._on_metrics_calculated(None)

    def swap_current_images(self):
        idx1, idx2 = self.app_state.current_index1, self.app_state.current_index2
        list1, list2 = self.app_state.image_list1, self.app_state.image_list2

        if not (0 <= idx1 < len(list1) and 0 <= idx2 < len(list2)):
            return

        list1[idx1], list2[idx2] = list2[idx2], list1[idx1]

        self.app_state._image1, self.app_state._image2 = self.app_state._image2, self.app_state._image1

        self.app_state._full_res_image1, self.app_state._full_res_image2 = (
            self.app_state._full_res_image2,
            self.app_state._full_res_image1
        )
        self.app_state._preview_image1, self.app_state._preview_image2 = (
            self.app_state._preview_image2,
            self.app_state._preview_image1
        )
        self.app_state._original_image1, self.app_state._original_image2 = (
            self.app_state._original_image2,
            self.app_state._original_image1
        )

        self.app_state._image1_path, self.app_state._image2_path = (
            self.app_state._image2_path,
            self.app_state._image1_path
        )

        self.app_state._display_cache_image1, self.app_state._display_cache_image2 = (
            self.app_state._display_cache_image2,
            self.app_state._display_cache_image1
        )

        self.app_state._scaled_image1_for_display, self.app_state._scaled_image2_for_display = (
            self.app_state._scaled_image2_for_display,
            self.app_state._scaled_image1_for_display
        )

        self.app_state.clear_interactive_caches()

        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution'])

        self._trigger_metrics_calculation_if_needed()
        self.app_state.stateChanged.emit()

    def swap_entire_lists(self):
        self.app_state.swap_all_image_data()
        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution'])

    def remove_current_image_from_list(self, image_number: int):
        target_list, current_index = (
            (self.app_state.image_list1, self.app_state.current_index1)
            if image_number == 1
            else (self.app_state.image_list2, self.app_state.current_index2)
        )
        if not (0 <= current_index < len(target_list)):
            return

        target_list.pop(current_index)

        new_list_len = len(target_list)
        new_index = min(current_index, new_list_len - 1) if new_list_len > 0 else -1

        if image_number == 1:
            self.app_state.current_index1 = new_index
        else:
            self.app_state.current_index2 = new_index

        self.app_state.clear_interactive_caches()

        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution'])
        self._trigger_metrics_calculation_if_needed()

        self.set_current_image(image_number)

    def remove_specific_image_from_list(self, image_number: int, index_to_remove: int):
        target_list, current_index = (
            (self.app_state.image_list1, self.app_state.current_index1)
            if image_number == 1
            else (self.app_state.image_list2, self.app_state.current_index2)
        )

        if not (0 <= index_to_remove < len(target_list)):
            return

        target_list.pop(index_to_remove)

        new_list_len = len(target_list)
        new_current_index = current_index

        if new_list_len == 0:
            new_current_index = -1
        elif index_to_remove < current_index:
            new_current_index = current_index - 1
        elif index_to_remove == current_index:
            new_current_index = min(index_to_remove, new_list_len - 1)

        if image_number == 1:
            self.app_state.current_index1 = new_current_index
        else:
            self.app_state.current_index2 = new_current_index

        self.app_state.clear_interactive_caches()

        if self.presenter:

            self.presenter.ui_batcher.schedule_update('combobox')

        self.set_current_image(image_number)

    def clear_image_list(self, image_number: int):

        self.app_state.clear_interactive_caches()

        self.app_state.clear_image_slot_data(image_number)
        if self.presenter:

            self.presenter.ui_batcher.schedule_batch_update(['combobox', 'file_names', 'resolution'])
        self.app_state.stateChanged.emit()

    def reorder_item_in_list(self, image_number: int, source_index: int, dest_index: int):
        target_list = self.app_state.image_list1 if image_number == 1 else self.app_state.image_list2

        if not (0 <= source_index < len(target_list)):
            return

        if source_index < dest_index:
            dest_index -= 1

        item_to_move = target_list.pop(source_index)
        target_list.insert(dest_index, item_to_move)

        current_index = self.app_state.current_index1 if image_number == 1 else self.app_state.current_index2

        new_current_index = -1
        if current_index == source_index:
            new_current_index = dest_index
        elif source_index < current_index and dest_index >= current_index:
            new_current_index = current_index - 1
        elif source_index > current_index and dest_index <= current_index:
            new_current_index = current_index + 1
        else:
            new_current_index = current_index

        if image_number == 1:
            self.app_state.current_index1 = new_current_index
        else:
            self.app_state.current_index2 = new_current_index

        if self.presenter:
            self.presenter.ui_batcher.schedule_update('combobox')
            from ui.widgets.composite.unified_flyout import FlyoutMode
            if self.presenter.ui_manager.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(50, self.presenter.ui_manager.unified_flyout.updateGeometryInDoubleMode)
            QTimer.singleShot(0, self.presenter.repopulate_flyouts)

    def move_item_between_lists(self, source_list_num: int, source_index: int, dest_list_num: int, dest_index: int):
        source_list = self.app_state.image_list1 if source_list_num == 1 else self.app_state.image_list2
        dest_list = self.app_state.image_list1 if dest_list_num == 1 else self.app_state.image_list2

        if not (0 <= source_index < len(source_list)):
            return

        path1_before = self.app_state.image_list1[self.app_state.current_index1][1] if 0 <= self.app_state.current_index1 < len(self.app_state.image_list1) else None
        path2_before = self.app_state.image_list2[self.app_state.current_index2][1] if 0 <= self.app_state.current_index2 < len(self.app_state.image_list2) else None

        item_to_move = source_list.pop(source_index)
        src_path_moved = item_to_move[1] if len(item_to_move) > 1 else None

        existing_dest_idx = -1
        if src_path_moved:
            for i, it in enumerate(dest_list):
                if it[1] == src_path_moved:
                    existing_dest_idx = i
                    break

        if existing_dest_idx != -1:
            dest_list.pop(existing_dest_idx)
            if existing_dest_idx < dest_index:
                dest_index -= 1

        dest_index = max(0, min(dest_index, len(dest_list)))
        dest_list.insert(dest_index, item_to_move)

        new_idx1 = -1
        if path1_before:
            try: new_idx1 = [item[1] for item in self.app_state.image_list1].index(path1_before)
            except ValueError: pass
        if new_idx1 == -1 and len(self.app_state.image_list1) > 0:
            new_idx1 = 0
            if source_list_num == 1 and source_index == self.app_state.current_index1:
                 new_idx1 = min(source_index, len(self.app_state.image_list1) - 1)

        new_idx2 = -1
        if path2_before:
            try: new_idx2 = [item[1] for item in self.app_state.image_list2].index(path2_before)
            except ValueError: pass
        if new_idx2 == -1 and len(self.app_state.image_list2) > 0:
            new_idx2 = 0
            if source_list_num == 2 and source_index == self.app_state.current_index2:
                 new_idx2 = min(source_index, len(self.app_state.image_list2) - 1)

        self.app_state.current_index1 = new_idx1
        self.app_state.current_index2 = new_idx2

        if self.presenter:
            self.presenter.ui_batcher.schedule_update('combobox')
            self.set_current_image(1, emit_signal=False)
            self.set_current_image(2, emit_signal=False)

            self.app_state.stateChanged.emit()

            try:
                from ui.widgets.composite.unified_flyout import FlyoutMode
                if self.presenter.ui_manager.unified_flyout.mode == FlyoutMode.DOUBLE:
                    QTimer.singleShot(50, self.presenter.ui_manager.unified_flyout.updateGeometryInDoubleMode)
            except Exception:
                pass
            QTimer.singleShot(0, self.presenter.repopulate_flyouts)

    def toggle_orientation(self, is_horizontal_checked: bool):
        if is_horizontal_checked != self.app_state.is_horizontal:
            self.app_state.is_horizontal = is_horizontal_checked
            self.app_state.magnifier_is_horizontal = is_horizontal_checked
            if self.presenter:
                self.presenter.ui.btn_magnifier_orientation.setChecked(is_horizontal_checked, emit_signal=False)
            self.settings_manager._save_setting("is_horizontal", is_horizontal_checked)
            self.settings_manager._save_setting("magnifier_is_horizontal", is_horizontal_checked)
            self.app_state.stateChanged.emit()

    def toggle_magnifier(self, use_magnifier_checked: bool):
        if use_magnifier_checked != self.app_state.use_magnifier:
            self.app_state.use_magnifier = use_magnifier_checked
            self.settings_manager._save_setting("use_magnifier", use_magnifier_checked)
        if self.presenter:
            self.presenter.ui.toggle_magnifier_panel_visibility(use_magnifier_checked)

    def toggle_magnifier_orientation(self, is_horizontal_checked: bool):
        """Переключает ориентацию только для лупы."""
        if is_horizontal_checked != self.app_state.magnifier_is_horizontal:
            self.app_state.magnifier_is_horizontal = is_horizontal_checked
            self.settings_manager._save_setting("magnifier_is_horizontal", is_horizontal_checked)
            self.app_state.stateChanged.emit()

    def toggle_freeze_magnifier(self, freeze_checked: bool):
        if freeze_checked:

            self.app_state.frozen_capture_point_relative = QPointF(self.app_state.capture_position_relative)
            self.app_state.freeze_magnifier = True
        else:

            if self.app_state.frozen_capture_point_relative:
                drawing_width, drawing_height = (
                    self.app_state.pixmap_width,
                    self.app_state.pixmap_height,
                )

                if drawing_width > 0 and drawing_height > 0:
                    target_max_dim = float(max(drawing_width, drawing_height))

                    frozen_capture_pixels = QPointF(
                        self.app_state.frozen_capture_point_relative.x() * drawing_width,
                        self.app_state.frozen_capture_point_relative.y() * drawing_height,
                    )
                    current_offset_pixels = QPointF(
                        self.app_state.magnifier_offset_relative.x() * target_max_dim,
                        self.app_state.magnifier_offset_relative.y() * target_max_dim,
                    )
                    target_magnifier_pos_pixels = frozen_capture_pixels + current_offset_pixels

                    new_capture_pos_pixels = QPointF(
                        self.app_state.capture_position_relative.x() * drawing_width,
                        self.app_state.capture_position_relative.y() * drawing_height,
                    )

                    new_offset_pixels = target_magnifier_pos_pixels - new_capture_pos_pixels

                    new_offset_relative = QPointF(
                        new_offset_pixels.x() / target_max_dim if target_max_dim > 0 else 0,
                        new_offset_pixels.y() / target_max_dim if target_max_dim > 0 else 0,
                    )

                    self.app_state.magnifier_offset_relative = new_offset_relative
                    self.app_state.magnifier_offset_relative_visual = new_offset_relative

            self.app_state.freeze_magnifier = False
            self.app_state.frozen_capture_point_relative = None

        self.settings_manager._save_setting("freeze_magnifier", freeze_checked)
        self.app_state.stateChanged.emit()

    def on_slider_pressed(self, slider_name: str):
        self.app_state.is_dragging_any_slider = True
        self.app_state.fixed_label_width = self.app.ui.image_label.size().width()
        self.app_state.fixed_label_height = self.app.ui.image_label.size().height()
        self.app.event_handler.start_interactive_movement()

    def on_slider_released(self, setting_name: str, value_to_save_provider):
        self.app_state.is_dragging_any_slider = False
        self.app_state.fixed_label_width = None
        self.app_state.fixed_label_height = None
        self.app.event_handler.stop_interactive_movement()
        if hasattr(self, "settings_manager") and self.settings_manager:
            value = value_to_save_provider()
            self.settings_manager._save_setting(setting_name, value)

    def on_edit_name_changed(self, image_number, new_name):
        new_name = new_name.strip()
        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        current_index = (
            self.app_state.current_index1
            if image_number == 1
            else self.app_state.current_index2
        )
        if 0 <= current_index < len(target_list):
            img, path, old_name, score = target_list[current_index]
            if new_name != old_name:
                target_list[current_index] = (img, path, new_name, score)
                if self.presenter:
                    self.presenter.update_combobox_displays()
                    if self.app_state.include_file_names_in_saved:
                        self.app_state.stateChanged.emit()

    def activate_single_image_mode(self, image_number: int):
        if (
            self.app_state.original_image1
            if image_number == 1
            else self.app_state.original_image2
        ):
            self.app_state.showing_single_image_mode = image_number
        else:
            self.app_state.showing_single_image_mode = 0

    def deactivate_single_image_mode(self):
        self.app_state.showing_single_image_mode = 0

    def change_language(self, lang_code: str):
        self.app_state.current_language = lang_code
        if self.presenter:
            self.presenter.on_language_changed()
        self.settings_manager._save_setting("language", lang_code)

    def toggle_include_filenames_in_saved(self, checked: bool):
        self.app_state.include_file_names_in_saved = checked
        self.settings_manager._save_setting("include_file_names_in_saved", checked)

    def apply_font_settings(self, size: int, font_weight: int, color: QColor, bg_color: QColor, draw_background: bool, placement_mode: str, text_alpha_percent: int):
        changed = False
        if self.app_state.font_size_percent != size:
            self.app_state.font_size_percent = size
            self.settings_manager._save_setting("font_size_percent", size)
            changed = True
        if self.app_state.font_weight != font_weight:
            self.app_state.font_weight = font_weight
            self.settings_manager._save_setting("font_weight", font_weight)
            changed = True
        if self.app_state.file_name_color != color:
            self.app_state.file_name_color = color
            self.settings_manager._save_setting("filename_color", color.name(QColor.NameFormat.HexArgb))
            changed = True
        if self.app_state.file_name_bg_color != bg_color:
            self.app_state.file_name_bg_color = bg_color
            self.settings_manager._save_setting("filename_bg_color", bg_color.name(QColor.NameFormat.HexArgb))
            changed = True
        if self.app_state.draw_text_background != draw_background:
            self.app_state.draw_text_background = draw_background
            self.settings_manager._save_setting("draw_text_background", draw_background)
            changed = True
        if self.app_state.text_placement_mode != placement_mode:
            self.app_state.text_placement_mode = placement_mode
            self.settings_manager._save_setting("text_placement_mode", placement_mode)
            changed = True
        text_alpha_percent = max(0, min(100, int(text_alpha_percent)))
        if getattr(self.app_state, 'text_alpha_percent', 100) != text_alpha_percent:
            self.app_state.text_alpha_percent = text_alpha_percent
            self.settings_manager._save_setting("text_alpha_percent", text_alpha_percent)
            changed = True
        if changed:
            self.app_state.stateChanged.emit()

    def increment_rating(self, image_number: int, index: int):
        self._change_rating(image_number, index, 1)

    def decrement_rating(self, image_number: int, index: int):
        self._change_rating(image_number, index, -1)

    def set_rating(self, image_number: int, index_to_set: int, new_score: int):
        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        current_index = (
            self.app_state.current_index1
            if image_number == 1
            else self.app_state.current_index2
        )
        if not (0 <= index_to_set < len(target_list)):
            return
        img, path, name, _old_score = target_list[index_to_set]
        target_list[index_to_set] = (img, path, name, new_score)

        if index_to_set == current_index:
            if self.presenter:
                self.presenter.update_rating_displays()

        try:
            uf = self.presenter.ui_manager.unified_flyout if self.presenter else None
            if uf and uf.isVisible():
                uf.update_item_rating(image_number, index_to_set, new_score)
        except Exception:
            pass

    def _change_rating(self, image_number: int, index_to_change: int, delta: int):
        target_list = (
            self.app_state.image_list1
            if image_number == 1
            else self.app_state.image_list2
        )
        current_index = (
            self.app_state.current_index1
            if image_number == 1
            else self.app_state.current_index2
        )
        if not (0 <= index_to_change < len(target_list)):
            return
        img, path, name, score = target_list[index_to_change]
        new_score = score + delta
        target_list[index_to_change] = (img, path, name, new_score)
        if index_to_change == current_index:
            if self.presenter:
                self.presenter.update_rating_displays()

        try:
            uf = self.presenter.ui_manager.unified_flyout if self.presenter else None
            if uf and uf.isVisible():
                uf.update_item_rating(image_number, index_to_change, new_score)
        except Exception:
            pass

    def toggle_divider_line_visibility(self, checked: bool):
        """Переключает видимость линии разделения"""
        is_visible = not checked
        if self.app_state.divider_line_visible != is_visible:
            self.app_state.divider_line_visible = is_visible
            self.settings_manager._save_setting("divider_line_visible", is_visible)

    def set_divider_line_color(self, color: QColor):
        """Устанавливает цвет линии разделения"""
        if self.app_state.divider_line_color != color:
            self.app_state.divider_line_color = color
            self.settings_manager._save_setting("divider_line_color", color.name(QColor.NameFormat.HexArgb))

    def set_divider_line_thickness(self, thickness: int):
        """Устанавливает толщину линии разделения"""
        thickness = max(1, min(20, thickness))
        if self.app_state.divider_line_thickness != thickness:
            self.app_state.divider_line_thickness = thickness
            self.settings_manager._save_setting("divider_line_thickness", thickness)

            if self.presenter and hasattr(self.presenter.ui, 'btn_divider_width'):
                if self.presenter.ui.btn_divider_width.get_value() != thickness:
                    self.presenter.ui.btn_divider_width.set_value(thickness)

    def toggle_magnifier_divider_visibility(self, visible: bool):
        """Переключает видимость внутренней линии разделения в лупе"""
        is_visible = not visible
        if self.app_state.magnifier_divider_visible != is_visible:
            self.app_state.magnifier_divider_visible = is_visible
            self.settings_manager._save_setting("magnifier_divider_visible", is_visible)

    def set_magnifier_divider_color(self, color: QColor):
        """Устанавливает цвет внутренней линии разделения в лупе"""
        if self.app_state.magnifier_divider_color != color:
            self.app_state.magnifier_divider_color = color
            self.settings_manager._save_setting("magnifier_divider_color", color.name(QColor.NameFormat.HexArgb))

    def set_magnifier_divider_thickness(self, thickness: int):
        """Устанавливает толщину внутренней линии разделения в лупе"""
        thickness = max(1, min(10, thickness))
        if self.app_state.magnifier_divider_thickness != thickness:
            self.app_state.magnifier_divider_thickness = thickness
            self.settings_manager._save_setting("magnifier_divider_thickness", thickness)

            if self.presenter and hasattr(self.presenter.ui, 'btn_magnifier_divider_width'):
                if self.presenter.ui.btn_magnifier_divider_width.get_value() != thickness:
                    self.presenter.ui.btn_magnifier_divider_width.set_value(thickness)

    def set_magnifier_visibility(self, left: bool | None = None, center: bool | None = None, right: bool | None = None):
        """Устанавливает видимость отдельных частей лупы (левая/центральная/правая). Настройка не сохраняется между сессиями."""
        changed = False
        if left is not None and getattr(self.app_state, "magnifier_visible_left", True) != bool(left):
            self.app_state.magnifier_visible_left = bool(left)
            changed = True
        if center is not None and getattr(self.app_state, "magnifier_visible_center", True) != bool(center):
            self.app_state.magnifier_visible_center = bool(center)
            changed = True
        if right is not None and getattr(self.app_state, "magnifier_visible_right", True) != bool(right):
            self.app_state.magnifier_visible_right = bool(right)
            changed = True
        if changed:

            try:
                self.app_state.clear_interactive_caches()
            except Exception:
                pass
            self.app_state.stateChanged.emit()

    def toggle_magnifier_part(self, part: str, visible: bool):
        """Обертка для смены одного флага видимости по строковому ключу: 'left'|'center'|'right'."""
        part = (part or "").strip().lower()
        if part == "left":
            self.set_magnifier_visibility(left=visible)
        elif part == "center":
            self.set_magnifier_visibility(center=visible)
        elif part == "right":
            self.set_magnifier_visibility(right=visible)
        else:

            return

    def toggle_magnifier_orientation(self):
        """Переключает ориентацию лупы независимо от основной линии."""
        self.app_state.magnifier_is_horizontal = not self.app_state.magnifier_is_horizontal
        self.settings_manager._save_setting("magnifier_is_horizontal", self.app_state.magnifier_is_horizontal)
        if self.presenter:
            self.presenter.update_magnifier_orientation_button_state()

    def toggle_diff_mode(self, checked: bool):
        self.app_state.show_diff = checked

        self.app_state.clear_interactive_caches()
        self.app_state.stateChanged.emit()

    def set_diff_mode(self, mode: str):
        self.app_state.diff_mode = mode
        self._trigger_metrics_calculation_if_needed()
        self.app_state.clear_interactive_caches()
        self.app_state.stateChanged.emit()

    def set_channel_view_mode(self, mode: str):
        self.app_state.channel_view_mode = mode
        self.app_state.clear_all_caches()
        self.app_state.stateChanged.emit()

    def _on_metrics_calculated(self, result):
        if result:
            psnr_val, ssim_val = result

            if self.app_state.auto_calculate_psnr or self.app_state.diff_mode == 'ssim':
                self.app_state.psnr_value = psnr_val
            if self.app_state.auto_calculate_ssim or self.app_state.diff_mode == 'ssim':
                self.app_state.ssim_value = ssim_val
        else:

            if not self.app_state.auto_calculate_psnr:
                self.app_state.psnr_value = None
            if not self.app_state.auto_calculate_ssim:
                self.app_state.ssim_value = None
        self.presenter.ui_batcher.schedule_update('resolution')

    def paste_image_from_clipboard(self):
        """Вставляет изображение(я) из буфера обмена без блокировок UI: HTTP(S) скачивается в фоне"""
        try:

            if self._paste_dialog is not None:
                try:
                    if self._paste_dialog.isVisible():
                        return False
                except (RuntimeError, AttributeError):
                    self._paste_dialog = None

            clipboard = QApplication.clipboard()
            mime_data = clipboard.mimeData()

            local_image_paths: list[str] = []
            urls_to_download: list[str] = []

            text_content = mime_data.text()
            if text_content:
                lines = text_content.strip().split('\n')
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith('2025-'):
                        if os.path.exists(line):
                            ext = os.path.splitext(line)[1].lower()
                            if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif']:
                                local_image_paths.append(line)
                        elif line.startswith('file://'):
                            file_path = line[7:]
                            if os.path.exists(file_path):
                                ext = os.path.splitext(file_path)[1].lower()
                                if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif']:
                                    local_image_paths.append(file_path)

            if mime_data.hasUrls():
                urls = mime_data.urls()
                for url in urls:
                    url_str = url.toString()
                    if url.isLocalFile():
                        file_path = url.toLocalFile()
                        if os.path.exists(file_path):
                            ext = os.path.splitext(file_path)[1].lower()
                            if ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif']:
                                local_image_paths.append(file_path)
                    elif url_str.startswith(('http://', 'https://')):
                        urls_to_download.append(url_str)

            if not local_image_paths and not urls_to_download and mime_data.hasImage():
                qimage = clipboard.image()
                if qimage.isNull():
                    if self.app and hasattr(self.app, 'toast_manager'):
                        self.app.toast_manager.show_toast(
                            tr("Не удалось получить изображение из буфера обмена", self.app_state.current_language),
                            duration=2500
                        )
                    return False
                else:
                    temp_dir = tempfile.gettempdir()
                    timestamp = int(time.time() * 1000)
                    temp_filename = f"clipboard_image_{os.getpid()}_{timestamp}.png"
                    image_path = os.path.join(temp_dir, temp_filename)
                    qimage.save(image_path, "PNG")
                    local_image_paths = [image_path]

            if not local_image_paths and not urls_to_download:
                if self.app and hasattr(self.app, 'toast_manager'):
                    self.app.toast_manager.show_toast(
                        tr("В буфере обмена нет изображения", self.app_state.current_language),
                        duration=2500
                    )
                return False

            if urls_to_download:
                if self.app and hasattr(self.app, 'toast_manager'):
                    self.app.toast_manager.show_toast(
                        tr("Загрузка изображений из буфера обмена...", self.app_state.current_language),
                        duration=1500
                    )
                worker = GenericWorker(self._download_images_from_urls, urls_to_download, 10)

                worker.signals.result.connect(lambda dl, _locals=local_image_paths.copy(): self._on_urls_downloaded(dl, _locals))

                worker.signals.error.connect(lambda err: getattr(self.app, "_worker_error_signal", None) and self.app._worker_error_signal.emit(
                    tr("Не удалось загрузить изображения по ссылкам", self.app_state.current_language)
                ))
                self.app.thread_pool.start(worker)
                return True

            self._show_paste_direction_dialog(local_image_paths)
            return True

        except Exception as e:
            logger.error(f"Error pasting image from clipboard: {e}", exc_info=True)
            if self.app and hasattr(self.app, 'toast_manager'):
                self.app.toast_manager.show_toast(
                    tr("Ошибка при вставке изображения", self.app_state.current_language),
                    duration=2500
                )
            return False

    def _show_paste_direction_dialog(self, image_paths: list):
        """Показывает overlay выбора направления для вставки изображения"""
        try:
            from ui.widgets.paste_direction_overlay import PasteDirectionOverlay

            if not hasattr(self.app, 'ui') or not hasattr(self.app.ui, 'image_label'):
                self.load_images_from_paths(image_paths, 1)
                return

            overlay = PasteDirectionOverlay(
                self.app,
                self.app.ui.image_label,
                is_horizontal=self.app_state.is_horizontal
            )
            overlay.set_language(self.app_state.current_language)
            self._paste_dialog = overlay

            def on_direction_selected(direction: str):
                """Обрабатывает выбор направления"""
                self._paste_dialog = None

                if direction in ("up", "left"):
                    slot_number = 1
                    toast_message = tr("Изображение добавлено в первый список", self.app_state.current_language) if len(image_paths) == 1 else tr("Изображения вставлены в первый список", self.app_state.current_language)
                else:
                    slot_number = 2
                    toast_message = tr("Изображение добавлено во второй список", self.app_state.current_language) if len(image_paths) == 1 else tr("Изображения вставлены во второй список", self.app_state.current_language)

                self.load_images_from_paths(image_paths, slot_number)

                if self.app and hasattr(self.app, 'toast_manager'):
                    self.app.toast_manager.show_toast(toast_message, duration=2000)

            def on_cancelled():
                """Обрабатывает отмену"""
                self._paste_dialog = None

            def on_destroyed():
                """Очищает ссылку на overlay при уничтожении"""
                self._paste_dialog = None

            overlay.direction_selected.connect(on_direction_selected)
            overlay.cancelled.connect(on_cancelled)
            overlay.destroyed.connect(on_destroyed)

            from PyQt6.QtCore import QTimer
            QTimer.singleShot(10, lambda: self._delayed_overlay_focus(overlay))
            overlay.show()
            overlay.raise_()

        except Exception as e:
            logger.error(f"Error showing paste direction overlay: {e}", exc_info=True)
            self._paste_dialog = None

    def _delayed_overlay_focus(self, overlay):
        """Delayed overlay focus setting for Wayland compatibility."""
        try:
            if overlay and not overlay.isActiveWindow():
                overlay.setFocus()
        except Exception as e:
            logger.error(f"Error setting overlay focus: {e}", exc_info=True)

            self.load_images_from_paths(image_paths, 1)
            if self.app and hasattr(self.app, 'toast_manager'):
                self.app.toast_manager.show_toast(
                    tr("Изображение добавлено в первый список", self.app_state.current_language) if len(image_paths) == 1 else tr("Изображения вставлены в первый список", self.app_state.current_language),
                    duration=2000
                )

    def quick_save_comparison(self):
        """
        Быстрое сохранение: переводим на фоновый пайплайн презентера, чтобы не блокировать UI.
        Возвращаем True, если задача инициирована, иначе False.
        """
        try:
            if not self.app_state.original_image1 or not self.app_state.original_image2:
                return False
            if not getattr(self.app_state, 'export_default_dir', None):
                return False
            presenter = getattr(self, "presenter", None)
            if presenter and hasattr(presenter, "_quick_save_with_error_handling"):
                presenter._quick_save_with_error_handling()
                return True
            return False
        except Exception as e:
            logger.error(f"Error during quick save delegation: {e}", exc_info=True)
            return False

    def on_combobox_changed(self, image_number: int, index: int):
        """Обрабатывает смену изображения из выпадающего списка или другого источника."""
        if image_number == 1:
            if 0 <= index < len(self.app_state.image_list1):
                self.app_state.current_index1 = index
                self.set_current_image(1)
        elif image_number == 2:
            if 0 <= index < len(self.app_state.image_list2):
                self.app_state.current_index2 = index
                self.set_current_image(2)
            return False
