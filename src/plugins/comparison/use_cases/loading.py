import os

from PIL import Image
from PyQt6.QtCore import QTimer

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from core.store import ImageItem
from resources.translations import tr
from shared_toolkit.workers import GenericWorker

def _invalidate_diff_cache(controller) -> None:
    if getattr(controller, "diff_service", None) is not None:
        controller.diff_service.invalidate()
    else:
        controller.store.viewport.session_data.render_cache.cached_diff_image = None

def initialize_app_display(controller):
    if controller.store.viewport.session_data.image_state.loaded_image1_paths:
        controller.load_images_from_paths(controller.store.viewport.session_data.image_state.loaded_image1_paths, 1)
    if controller.store.viewport.session_data.image_state.loaded_image2_paths:
        controller.load_images_from_paths(controller.store.viewport.session_data.image_state.loaded_image2_paths, 2)

    if (
        controller.store.viewport.session_data.image_state.loaded_current_index1 != -1
        and 0 <= controller.store.viewport.session_data.image_state.loaded_current_index1 < len(controller.store.document.image_list1)
    ):
        controller.store.document.current_index1 = controller.store.viewport.session_data.image_state.loaded_current_index1
    elif controller.store.document.image_list1:
        controller.store.document.current_index1 = 0

    if (
        controller.store.viewport.session_data.image_state.loaded_current_index2 != -1
        and 0 <= controller.store.viewport.session_data.image_state.loaded_current_index2 < len(controller.store.document.image_list2)
    ):
        controller.store.document.current_index2 = controller.store.viewport.session_data.image_state.loaded_current_index2
    elif controller.store.document.image_list2:
        controller.store.document.current_index2 = 0

    controller.set_current_image(1, emit_signal=False)
    controller.set_current_image(2, emit_signal=False)

    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(
            ["combobox", "file_names", "resolution", "ratings"]
        )
        controller.presenter.update_minimum_window_size()

    controller.store.emit_state_change("document")

def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(["file_names", "resolution"])

    source1 = controller.store.document.full_res_image1 or controller.store.document.preview_image1
    source2 = controller.store.document.full_res_image2 or controller.store.document.preview_image2

    if source1 and source2:
        try:
            controller._cancel_pending_unification(
                controller.store.document.image1_path,
                controller.store.document.image2_path,
            )
            if not controller.store.document.image1_path or not controller.store.document.image2_path:
                return

            controller.store.viewport.session_data.render_cache.unification_in_progress = True
            controller.store.viewport.session_data.render_cache.pending_unification_paths = (
                controller.store.document.image1_path,
                controller.store.document.image2_path,
            )

            controller._unification_task_id += 1
            current_task_id = controller._unification_task_id
            worker = GenericWorker(
                controller._unify_images_worker_task,
                source1.copy(),
                source2.copy(),
                controller.store.document.image1_path,
                controller.store.document.image2_path,
                controller.store.viewport.render_config.display_resolution_limit,
                current_task_id,
            )
            worker.signals.result.connect(controller._on_unified_images_ready)
            controller.thread_pool.start(worker, priority=1)
        except Exception:
            controller.store.viewport.session_data.render_cache.unification_in_progress = False
            controller.metrics_service.on_metrics_calculated(None)
    else:
        controller.metrics_service.on_metrics_calculated(None)

    if controller.presenter:
        QTimer.singleShot(10, lambda: controller.store.emit_state_change("viewport"))

def handle_full_image_loaded(controller, full_img, path, image_number, index_in_list):
    if not full_img:
        return

    target_list = (
        controller.store.document.image_list1
        if image_number == 1
        else controller.store.document.image_list2
    )
    if not (0 <= index_in_list < len(target_list)) or target_list[index_in_list].path != path:
        return

    item = target_list[index_in_list]
    item.image = full_img
    controller._update_image_slot(image_number, image=full_img, path=path, is_full_res=True)
    _invalidate_diff_cache(controller)

    current_app_index = (
        controller.store.document.current_index1
        if image_number == 1
        else controller.store.document.current_index2
    )
    if index_in_list != current_app_index:
        return

    def trigger_unification():
        source1 = controller.store.document.full_res_image1 or controller.store.document.preview_image1
        source2 = controller.store.document.full_res_image2 or controller.store.document.preview_image2
        if source1 and source2:
            controller.store.viewport.session_data.render_cache.unification_in_progress = True
            controller.store.viewport.session_data.render_cache.pending_unification_paths = (
                controller.store.document.image1_path,
                controller.store.document.image2_path,
            )
            controller._unification_task_id += 1
            current_task_id = controller._unification_task_id
            worker = GenericWorker(
                controller._unify_images_worker_task,
                source1.copy(),
                source2.copy(),
                controller.store.document.image1_path,
                controller.store.document.image2_path,
                controller.store.viewport.render_config.display_resolution_limit,
                current_task_id,
            )
            worker.signals.result.connect(controller._on_unified_images_ready)
            controller.thread_pool.start(worker, priority=1)
        else:
            controller.metrics_service.on_metrics_calculated(None)

    QTimer.singleShot(50, trigger_unification)

def load_images_from_paths(controller, file_paths: list[str], image_number: int):
    target_list_ref = (
        controller.store.document.image_list1
        if image_number == 1
        else controller.store.document.image_list2
    )
    is_new_comparison = len(target_list_ref) == 0
    if is_new_comparison:
        other_image_number = 2 if image_number == 1 else 1
        other_list = (
            controller.store.document.image_list1
            if other_image_number == 1
            else controller.store.document.image_list2
        )
        controller.store.viewport.session_data.render_cache.unification_in_progress = False
        controller.store.viewport.session_data.render_cache.pending_unification_paths = None
        if len(other_list) == 0:
            controller.store.clear_image_slot_data(1)
            controller.store.clear_image_slot_data(2)
            controller.store.viewport.session_data.image_state.image1 = None
            controller.store.viewport.session_data.image_state.image2 = None
            controller.store.viewport.session_data.render_cache.display_cache_image1 = None
            controller.store.viewport.session_data.render_cache.display_cache_image2 = None
            if getattr(controller, "diff_service", None) is not None:
                controller.diff_service.invalidate()
            else:
                controller.store.viewport.session_data.render_cache.cached_diff_image = None
        else:
            controller.store.clear_image_slot_data(image_number)

    load_errors, newly_added_indices = [], []
    current_paths_in_list = {entry.path for entry in target_list_ref if entry.path}

    for file_path in file_paths:
        if not isinstance(file_path, str) or not file_path:
            load_errors.append(
                f"{str(file_path)}: {tr('msg.invalid_item_type_or_empty_path', controller.store.settings.current_language)}"
            )
            continue
        try:
            normalized_path = os.path.normpath(file_path)
            original_path_for_display = os.path.basename(normalized_path) or "-----"
        except Exception:
            load_errors.append(
                f"{file_path}: {tr('msg.error_normalizing_path', controller.store.settings.current_language)}"
            )
            continue

        if normalized_path in current_paths_in_list:
            _reload_existing_path(controller, image_number, normalized_path, target_list_ref)
            continue

        try:
            target_list_ref.append(
                ImageItem(
                    image=None,
                    path=normalized_path,
                    display_name=os.path.splitext(original_path_for_display)[0],
                    rating=0,
                )
            )
            current_paths_in_list.add(normalized_path)
            newly_added_indices.append(len(target_list_ref) - 1)
        except Exception:
            load_errors.append(
                f"{original_path_for_display}: {tr('msg.error_processing_path', controller.store.settings.current_language)}"
            )

    _finalize_loaded_paths(controller, image_number, newly_added_indices, load_errors)

def _reload_existing_path(controller, image_number: int, normalized_path: str, target_list_ref):
    try:
        index = next(i for i, item in enumerate(target_list_ref) if item.path == normalized_path)
        item = target_list_ref[index]
        item.image = None
        doc = controller.store.document
        other_path = doc.image2_path if image_number == 1 else doc.image1_path
        cache_key = (normalized_path, other_path) if image_number == 1 else (other_path, normalized_path)
        cache = controller.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.pop(cache_key)

        if image_number == 1:
            controller.store.document.current_index1 = index
        else:
            controller.store.document.current_index2 = index

        QTimer.singleShot(50, lambda num=image_number: controller.set_current_image(num))
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")
    except (ValueError, IndexError):
        pass

def _finalize_loaded_paths(controller, image_number: int, newly_added_indices: list[int], load_errors: list[str]):
    if newly_added_indices:
        new_index = newly_added_indices[-1]
        if image_number == 1:
            controller.store.document.current_index1 = new_index
        else:
            controller.store.document.current_index2 = new_index

        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")
        QTimer.singleShot(50, lambda: controller.set_current_image(image_number))

        if controller.presenter:
            from shared_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode
            QTimer.singleShot(0, controller.presenter.repopulate_flyouts)
            if controller.presenter.ui_manager.transient.unified_flyout.mode == FlyoutMode.DOUBLE:
                QTimer.singleShot(
                    50,
                    lambda: controller.presenter.ui_manager.transient.unified_flyout.refreshGeometry(immediate=False),
                )

    if load_errors:
        error_message = (
            tr("msg.some_images_could_not_be_loaded", controller.store.settings.current_language)
            + ":\n\n - "
            + "\n - ".join(load_errors)
        )
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(error_message))
        else:
            controller.error_occurred.emit(error_message)

def set_current_image(controller, image_number: int, force_refresh: bool = False, emit_signal: bool = True):
    target_list = (
        controller.store.document.image_list1
        if image_number == 1
        else controller.store.document.image_list2
    )
    current_index = (
        controller.store.document.current_index1
        if image_number == 1
        else controller.store.document.current_index2
    )

    if not (0 <= current_index < len(target_list)):
        controller.store.clear_image_slot_data(image_number)
        if controller.store.viewport.session_data.render_cache.unification_in_progress:
            pending = controller.store.viewport.session_data.render_cache.pending_unification_paths
            if pending:
                current_path = (
                    controller.store.document.image1_path
                    if image_number == 1
                    else controller.store.document.image2_path
                )
                if current_path and current_path not in pending:
                    controller.store.viewport.session_data.render_cache.unification_in_progress = False
                    controller.store.viewport.session_data.render_cache.pending_unification_paths = None
        controller.store.emit_state_change("document")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        return

    item = target_list[current_index]
    pil_img = item.image
    path = item.path
    controller._update_image_slot(
        image_number, image=pil_img, path=path, is_full_res=bool(pil_img), emit=False
    )
    _invalidate_diff_cache(controller)
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_magnifier=False)
    controller._schedule_image_canvas_update()

    path1 = controller.store.document.image1_path
    path2 = controller.store.document.image2_path
    if path1 and path2:
        cache_key = (path1, path2)
        cache = controller.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.move_to_end(cache_key)
            u1, u2 = cache[cache_key]
            controller.store.viewport.session_data.image_state.image1 = u1
            controller.store.viewport.session_data.image_state.image2 = u2
            controller.store.viewport.session_data.render_cache.display_cache_image1 = u1
            controller.store.viewport.session_data.render_cache.display_cache_image2 = u2
            controller.store.viewport.session_data.render_cache.unification_in_progress = False
            controller.store.viewport.session_data.render_cache.scaled_image1_for_display = None
            controller.store.viewport.session_data.render_cache.scaled_image2_for_display = None
            controller.store.invalidate_render_cache()
            controller._invalidate_image_canvas_render_state(clear_magnifier=False)
            controller._schedule_image_canvas_update()
            if emit_signal:
                controller.store.emit_state_change("document")
                if controller.event_bus:
                    controller.event_bus.emit(CoreUpdateRequestedEvent())
                else:
                    controller.update_requested.emit()
            return

    if pil_img is None and path:
        worker = GenericWorker(controller._load_image_async, path, image_number, current_index, None)
        worker.signals.result.connect(controller._on_image_loaded_from_worker)
        controller.thread_pool.start(worker)
    else:
        controller._trigger_preview_unification(image_number)

    if emit_signal:
        controller.store.emit_state_change("document")

def on_unified_images_ready(controller, result):
    if not result:
        controller.metrics_service.on_metrics_calculated(None)
        return
    try:
        if isinstance(result, tuple) and len(result) == 7:
            u1, u2, cached_u1, cached_u2, path1, path2, task_id = result
        elif isinstance(result, tuple) and len(result) == 5:
            u1, u2, path1, path2, task_id = result
            cached_u1, cached_u2 = None, None
        else:
            controller.metrics_service.on_metrics_calculated(None)
            return

        if task_id != controller._unification_task_id:
            return
        current_paths_now = (controller.store.document.image1_path, controller.store.document.image2_path)
        if (path1 != current_paths_now[0]) or (path2 != current_paths_now[1]):
            controller.store.viewport.session_data.render_cache.unification_in_progress = False
            controller.store.invalidate_geometry_cache()
            controller.store.emit_state_change("viewport")
            return
        if not (u1 and u2):
            controller.store.viewport.session_data.render_cache.unification_in_progress = False
            controller.metrics_service.on_metrics_calculated(None)
            return

        controller.store.viewport.session_data.image_state.image1 = u1
        controller.store.viewport.session_data.image_state.image2 = u2
        _invalidate_diff_cache(controller)
        controller.store.viewport.session_data.render_cache.scaled_image1_for_display = None
        controller.store.viewport.session_data.render_cache.scaled_image2_for_display = None
        controller.store.invalidate_render_cache()
        controller._invalidate_image_canvas_render_state(clear_magnifier=False)
        controller._schedule_image_canvas_update()

        if cached_u1 is not None and cached_u2 is not None:
            controller.store.viewport.session_data.render_cache.display_cache_image1 = cached_u1
            controller.store.viewport.session_data.render_cache.display_cache_image2 = cached_u2
            controller.store.viewport.session_data.render_cache.last_display_cache_params = (
                id(u1), id(u2), controller.store.viewport.render_config.display_resolution_limit
            )
        try:
            cache_key = (path1, path2)
            cache = controller.store.viewport.session_data.render_cache.unified_image_cache
            if cache_key in cache:
                cache.move_to_end(cache_key)
            cache[cache_key] = (u1, u2)
            while len(cache) > 20:
                cache.popitem(last=False)
        except Exception:
            pass

        controller.store.viewport.session_data.render_cache.unification_in_progress = False
        controller._trigger_metrics_calculation_if_needed()
        try:
            if controller.event_bus:
                controller.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                controller.update_requested.emit()
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_batch_update(["resolution", "file_names"])
        except Exception:
            pass
    except Exception:
        controller.store.viewport.session_data.render_cache.unification_in_progress = False
        controller.metrics_service.on_metrics_calculated(None)
