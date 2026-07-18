import os

from PySide6.QtCore import QTimer
from sli_ui_toolkit.workers import GenericWorker

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from tabs.image_compare.services import document_store_ops
from tabs.image_compare.state.document import ImageItem
from sli_ui_toolkit.i18n import tr


def _invalidate_diff_cache(controller) -> None:
    if getattr(controller, "diff_service", None) is not None:
        controller.diff_service.invalidate()
    else:
        render_cache = _session_render_cache(controller)
        if render_cache is not None:
            render_cache.cached_diff_image = None


def _session_render_cache(controller):
    session_data = getattr(controller.store.viewport, "session_data", None)
    if session_data is None:
        return None
    return getattr(session_data, "render_cache", None)


def _clear_unification_flags(controller) -> None:
    """Clear in-progress flags; no-op if the active session has no render_cache.

    Unification workers can finish after a workspace switch (e.g. Move to
    another tab). The new session's ``SessionData`` may have ``render_cache
    is None`` — never assign attributes onto that.
    """
    render_cache = _session_render_cache(controller)
    if render_cache is None:
        return
    render_cache.unification_in_progress = False
    render_cache.pending_unification_paths = None


def initialize_app_display(controller):
    if controller.store.get_session_state_slot("document") is None:
        return
    if controller.store.viewport.session_data.image_state.loaded_image1_paths:
        controller.load_images_from_paths(
            controller.store.viewport.session_data.image_state.loaded_image1_paths, 1
        )
    if controller.store.viewport.session_data.image_state.loaded_image2_paths:
        controller.load_images_from_paths(
            controller.store.viewport.session_data.image_state.loaded_image2_paths, 2
        )

    document = controller.store.get_session_state_slot("document")
    if (
        controller.store.viewport.session_data.image_state.loaded_current_index1 != -1
        and 0
        <= controller.store.viewport.session_data.image_state.loaded_current_index1
        < len(document.image_list1)
    ):
        document.current_index1 = (
            controller.store.viewport.session_data.image_state.loaded_current_index1
        )
    elif document.image_list1:
        document.current_index1 = 0

    if (
        controller.store.viewport.session_data.image_state.loaded_current_index2 != -1
        and 0
        <= controller.store.viewport.session_data.image_state.loaded_current_index2
        < len(document.image_list2)
    ):
        document.current_index2 = (
            controller.store.viewport.session_data.image_state.loaded_current_index2
        )
    elif document.image_list2:
        document.current_index2 = 0

    controller.set_current_image(1, emit_signal=False)
    controller.set_current_image(2, emit_signal=False)

    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(
            ["combobox", "file_names", "resolution", "ratings"]
        )
        controller.presenter.update_minimum_window_size()

    controller.store.emit_state_change("document")


def _unify_resize_method(controller) -> str:
    from shared.rendering.interpolation import get_effective_main_interpolation_method

    return get_effective_main_interpolation_method(controller.store.viewport)


def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(
            ["file_names", "resolution"]
        )

    document = controller.store.get_session_state_slot("document")
    source1 = document.full_res_image1 or document.preview_image1
    source2 = document.full_res_image2 or document.preview_image2

    if source1 and source2:
        try:
            controller._cancel_pending_unification(
                document.image1_path,
                document.image2_path,
            )
            if not document.image1_path or not document.image2_path:
                return

            controller.store.viewport.session_data.render_cache.unification_in_progress = (
                True
            )
            controller.store.viewport.session_data.render_cache.pending_unification_paths = (
                document.image1_path,
                document.image2_path,
            )

            controller._unification_task_id += 1
            current_task_id = controller._unification_task_id

            worker = GenericWorker(
                controller._unify_images_worker_task,
                source1,
                source2,
                document.image1_path,
                document.image2_path,
                current_task_id,
                _unify_resize_method(controller),
            )
            worker.signals.result.connect(controller._on_unified_images_ready)
            controller.thread_pool.start(worker, priority=1)
        except Exception:
            controller.store.viewport.session_data.render_cache.unification_in_progress = (
                False
            )
            controller.metrics_service.on_metrics_calculated(None)
    else:
        controller.metrics_service.on_metrics_calculated(None)

    if controller.presenter:
        QTimer.singleShot(10, lambda: controller.store.emit_state_change("viewport"))


def handle_full_image_loaded(controller, full_img, path, image_number, index_in_list):
    if not full_img:
        return

    document = controller.store.get_session_state_slot("document")
    target_list = document.image_list1 if image_number == 1 else document.image_list2
    if (
        not (0 <= index_in_list < len(target_list))
        or target_list[index_in_list].path != path
    ):
        return

    from shared.image_processing.tiled_pixel_store import (
        TiledPixelStore,
        close_pixel_store,
        maybe_wrap_pixel_store,
    )

    outgoing = getattr(document, f"full_res_image{image_number}", None)
    other = 2 if image_number == 1 else 1
    other_full = getattr(document, f"full_res_image{other}", None)
    if outgoing is not None and outgoing is not other_full:
        close_pixel_store(outgoing)
    if not isinstance(full_img, TiledPixelStore):
        full_img = maybe_wrap_pixel_store(full_img)
    item = target_list[index_in_list]
    item.image = full_img
    controller._update_image_slot(
        image_number, image=full_img, path=path, is_full_res=True
    )
    _invalidate_diff_cache(controller)

    current_app_index = (
        document.current_index1 if image_number == 1 else document.current_index2
    )
    if index_in_list != current_app_index:
        return

    def trigger_unification():
        live_document = controller.store.get_session_state_slot("document")
        source1 = live_document.full_res_image1 or live_document.preview_image1
        source2 = live_document.full_res_image2 or live_document.preview_image2
        if source1 and source2:
            controller.store.viewport.session_data.render_cache.unification_in_progress = (
                True
            )
            controller.store.viewport.session_data.render_cache.pending_unification_paths = (
                live_document.image1_path,
                live_document.image2_path,
            )
            controller._unification_task_id += 1
            current_task_id = controller._unification_task_id
            worker = GenericWorker(
                controller._unify_images_worker_task,
                source1,
                source2,
                live_document.image1_path,
                live_document.image2_path,
                current_task_id,
                _unify_resize_method(controller),
            )
            worker.signals.result.connect(controller._on_unified_images_ready)
            controller.thread_pool.start(worker, priority=1)
        else:
            controller.metrics_service.on_metrics_calculated(None)

    QTimer.singleShot(50, trigger_unification)


def load_images_from_paths(controller, file_paths: list[str], image_number: int):
    document = controller.store.get_session_state_slot("document")
    target_list_ref = (
        document.image_list1 if image_number == 1 else document.image_list2
    )
    is_new_comparison = len(target_list_ref) == 0
    if is_new_comparison:
        other_image_number = 2 if image_number == 1 else 1
        other_list = (
            document.image_list1 if other_image_number == 1 else document.image_list2
        )
        controller.store.viewport.session_data.render_cache.unification_in_progress = (
            False
        )
        controller.store.viewport.session_data.render_cache.pending_unification_paths = (
            None
        )
        if len(other_list) == 0:
            document_store_ops.clear_image_slot_data(controller.store, 1)
            document_store_ops.clear_image_slot_data(controller.store, 2)
            controller.store.viewport.session_data.image_state.image1 = None
            controller.store.viewport.session_data.image_state.image2 = None
            controller.store.viewport.session_data.render_cache.display_cache_image1 = (
                None
            )
            controller.store.viewport.session_data.render_cache.display_cache_image2 = (
                None
            )
            if getattr(controller, "diff_service", None) is not None:
                controller.diff_service.invalidate()
            else:
                controller.store.viewport.session_data.render_cache.cached_diff_image = (
                    None
                )
        else:
            # First item on an empty list while the other side already has
            # content. Only clear if this slot still holds stale document
            # pixels/path — a no-op clear would thrash the live side's
            # display caches for Duplicate / DnD onto an empty half.
            stale = (
                document.full_res_image1 is not None or document.image1_path
                if image_number == 1
                else document.full_res_image2 is not None or document.image2_path
            )
            if stale:
                document_store_ops.clear_image_slot_data(
                    controller.store, image_number
                )

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
            _reload_existing_path(
                controller, image_number, normalized_path, target_list_ref
            )
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


def duplicate_image_to_slot(controller, source_slot: int, target_slot: int) -> None:
    """Copy the current image on ``source_slot`` onto ``target_slot``.

    Unlike ``load_images_from_paths``, this does not treat an empty target
    list as a brand-new comparison and therefore does not clear the live
    half's display caches. The target list entry is path-only (no shared
    ``TiledPixelStore``); ``set_current_image`` loads/opens a fresh store.
    """
    if source_slot not in (1, 2) or target_slot not in (1, 2):
        return
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    source_list = document.image_list1 if source_slot == 1 else document.image_list2
    source_index = (
        document.current_index1 if source_slot == 1 else document.current_index2
    )
    if not (0 <= source_index < len(source_list)):
        return
    source_item = source_list[source_index]
    path = source_item.path or ""
    if not path:
        return

    target_list = document.image_list1 if target_slot == 1 else document.image_list2
    for index, existing in enumerate(target_list):
        if existing.path == path:
            if target_slot == 1:
                document.current_index1 = index
            else:
                document.current_index2 = index
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
            QTimer.singleShot(
                0, lambda slot=target_slot: controller.set_current_image(slot)
            )
            return

    target_list.append(
        ImageItem(
            image=None,
            path=path,
            display_name=source_item.display_name,
            rating=int(getattr(source_item, "rating", 0) or 0),
        )
    )
    new_index = len(target_list) - 1
    if target_slot == 1:
        document.current_index1 = new_index
    else:
        document.current_index2 = new_index

    if controller.presenter:
        controller.presenter.ui_batcher.schedule_update("combobox")
        from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

        QTimer.singleShot(0, controller.presenter.repopulate_flyouts)
        if (
            controller.presenter.ui_manager.transient.unified_flyout.mode
            == FlyoutMode.DOUBLE
        ):
            QTimer.singleShot(
                50,
                lambda: controller.presenter.ui_manager.transient.unified_flyout.refreshGeometry(
                    immediate=False
                ),
            )

    QTimer.singleShot(0, lambda slot=target_slot: controller.set_current_image(slot))


def _reload_existing_path(
    controller, image_number: int, normalized_path: str, target_list_ref
):
    try:
        index = next(
            i for i, item in enumerate(target_list_ref) if item.path == normalized_path
        )
        item = target_list_ref[index]
        item.image = None
        doc = controller.store.get_session_state_slot("document")
        other_path = doc.image2_path if image_number == 1 else doc.image1_path
        cache_key = (
            (normalized_path, other_path)
            if image_number == 1
            else (other_path, normalized_path)
        )
        cache = controller.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.pop(cache_key)

        if image_number == 1:
            doc.current_index1 = index
        else:
            doc.current_index2 = index

        QTimer.singleShot(
            50, lambda num=image_number: controller.set_current_image(num)
        )
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")
    except (ValueError, IndexError):
        pass


def _finalize_loaded_paths(
    controller,
    image_number: int,
    newly_added_indices: list[int],
    load_errors: list[str],
):
    if newly_added_indices:
        new_index = newly_added_indices[-1]
        document = controller.store.get_session_state_slot("document")
        if image_number == 1:
            document.current_index1 = new_index
        else:
            document.current_index2 = new_index

        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")

        QTimer.singleShot(
            50, lambda num=image_number: controller.set_current_image(num)
        )

        if controller.presenter:
            from sli_ui_toolkit.ui.widgets.composite.unified_flyout import FlyoutMode

            QTimer.singleShot(0, controller.presenter.repopulate_flyouts)
            if (
                controller.presenter.ui_manager.transient.unified_flyout.mode
                == FlyoutMode.DOUBLE
            ):
                QTimer.singleShot(
                    50,
                    lambda: controller.presenter.ui_manager.transient.unified_flyout.refreshGeometry(
                        immediate=False
                    ),
                )

    if load_errors:
        error_message = (
            tr(
                "msg.some_images_could_not_be_loaded",
                controller.store.settings.current_language,
            )
            + ":\n\n - "
            + "\n - ".join(load_errors)
        )
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(error_message))
        else:
            controller.error_occurred.emit(error_message)


def set_current_image(
    controller, image_number: int, force_refresh: bool = False, emit_signal: bool = True
):
    document = controller.store.get_session_state_slot("document")
    target_list = document.image_list1 if image_number == 1 else document.image_list2
    current_index = (
        document.current_index1 if image_number == 1 else document.current_index2
    )

    if not (0 <= current_index < len(target_list)):
        document_store_ops.clear_image_slot_data(controller.store, image_number)
        _invalidate_diff_cache(controller)
        # clear_image_slot_data already drops this slot's display/scaled caches.
        # invalidate_geometry_cache() would also wipe the other side and flash
        # a blank canvas while the live half is still valid.
        controller._invalidate_image_canvas_render_state(clear_magnifier=True)
        controller._schedule_image_canvas_update()
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_batch_update(
                ["combobox", "file_names", "resolution", "ratings"]
            )
        if controller.store.viewport.session_data.render_cache.unification_in_progress:
            pending = (
                controller.store.viewport.session_data.render_cache.pending_unification_paths
            )
            if pending:
                current_path = (
                    document.image1_path
                    if image_number == 1
                    else document.image2_path
                )
                if current_path and current_path not in pending:
                    controller.store.viewport.session_data.render_cache.unification_in_progress = (
                        False
                    )
                    controller.store.viewport.session_data.render_cache.pending_unification_paths = (
                        None
                    )
        controller.metrics_service.on_metrics_calculated(None)
        controller.store.emit_state_change("document")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        return

    item = target_list[current_index]
    pil_img = item.image
    path = item.path
    if pil_img is None:
        # Path-only selection must not keep the previous slot's full_res/preview.
        # Cross-list move of the live current image onto an empty list leaves the
        # remaining unloaded item as current: SetImagePathAction alone used to
        # keep the moved image's store on this slot, so a premature unify shared
        # it and close_pixel_store later closed the other side's live store.
        document_store_ops.clear_image_slot_data(controller.store, image_number)
    controller._update_image_slot(
        image_number, image=pil_img, path=path, is_full_res=bool(pil_img), emit=False
    )
    _invalidate_diff_cache(controller)
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_magnifier=False)
    controller._schedule_image_canvas_update()

    document = controller.store.get_session_state_slot("document")
    path1 = document.image1_path
    path2 = document.image2_path
    if path1 and path2:
        cache_key = (path1, path2)
        cache = controller.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.move_to_end(cache_key)
            u1, u2 = cache[cache_key]
            controller.store.viewport.session_data.image_state.image1 = u1
            controller.store.viewport.session_data.image_state.image2 = u2
            # display_cache_image1/2 is exclusively owned/refreshed by the
            # per-frame create_preview_cache_async pipeline (see
            # docs/dev/DISPLAY_IMAGE_PIPELINE.md) -- clear it here rather than
            # writing the full-resolution u1/u2 pair into it directly, which
            # bypassed downscaling entirely and was the actual cause of the
            # "images shrink into a tiny square" bug with >8192px images.
            controller.store.viewport.session_data.render_cache.display_cache_image1 = (
                None
            )
            controller.store.viewport.session_data.render_cache.display_cache_image2 = (
                None
            )
            controller.store.viewport.session_data.render_cache.last_display_cache_params = (
                None
            )
            controller.store.viewport.session_data.render_cache.unification_in_progress = (
                False
            )
            controller.store.viewport.session_data.render_cache.scaled_image1_for_display = (
                None
            )
            controller.store.viewport.session_data.render_cache.scaled_image2_for_display = (
                None
            )
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
        worker = GenericWorker(
            controller._load_image_async, path, image_number, current_index, None
        )
        worker.signals.result.connect(controller._on_image_loaded_from_worker)
        controller.thread_pool.start(worker)
    else:
        controller._trigger_preview_unification(image_number)

    if emit_signal:
        controller.store.emit_state_change("document")


def on_unified_images_ready(controller, result):
    if not result:
        _clear_unification_flags(controller)
        controller.metrics_service.on_metrics_calculated(None)
        return
    try:
        if isinstance(result, tuple) and len(result) == 5:
            u1, u2, path1, path2, task_id = result
        else:
            _clear_unification_flags(controller)
            controller.metrics_service.on_metrics_calculated(None)
            return

        if task_id != controller._unification_task_id:
            return

        document = controller.store.get_session_state_slot("document")
        session_data = getattr(controller.store.viewport, "session_data", None)
        render_cache = (
            getattr(session_data, "render_cache", None) if session_data else None
        )
        image_state = (
            getattr(session_data, "image_state", None) if session_data else None
        )
        # Worker finished after a workspace switch: no document / IC session_data.
        if document is None or render_cache is None or image_state is None:
            _clear_unification_flags(controller)
            return

        current_paths_now = (document.image1_path, document.image2_path)
        if (path1 != current_paths_now[0]) or (path2 != current_paths_now[1]):
            _clear_unification_flags(controller)
            controller.store.invalidate_geometry_cache()
            controller.store.emit_state_change("viewport")
            return
        if not (u1 and u2):
            _clear_unification_flags(controller)
            controller.metrics_service.on_metrics_calculated(None)
            return

        image_state.image1 = u1
        image_state.image2 = u2
        _invalidate_diff_cache(controller)
        # display_cache_image1/2 is exclusively owned/refreshed by the
        # per-frame create_preview_cache_async pipeline (see
        # docs/dev/DISPLAY_IMAGE_PIPELINE.md) -- clear it here so a stale
        # display cache from the previous image pair never lingers, rather
        # than writing a second, competing copy of it from this worker
        # result.
        render_cache.scaled_image1_for_display = None
        render_cache.scaled_image2_for_display = None
        render_cache.display_cache_image1 = None
        render_cache.display_cache_image2 = None
        render_cache.last_display_cache_params = None
        controller.store.invalidate_render_cache()
        controller._invalidate_image_canvas_render_state(clear_magnifier=False)
        controller._schedule_image_canvas_update()

        try:
            cache_key = (path1, path2)
            cache = render_cache.unified_image_cache
            if cache_key in cache:
                cache.move_to_end(cache_key)
            cache[cache_key] = (u1, u2)
            while len(cache) > 20:
                cache.popitem(last=False)
        except Exception:
            pass

        _clear_unification_flags(controller)
        controller._trigger_metrics_calculation_if_needed()
        try:
            if controller.event_bus:
                controller.event_bus.emit(CoreUpdateRequestedEvent())
            else:
                controller.update_requested.emit()
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_batch_update(
                    ["resolution", "file_names"]
                )
        except Exception:
            pass
    except Exception:
        _clear_unification_flags(controller)
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass
