import logging
import os

from PySide6.QtCore import QTimer
from sli_ui_toolkit.workers import GenericWorker

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from tabs.image_compare.services import document_store_ops
from tabs.image_compare.state.document import ImageItem
from sli_ui_toolkit.i18n import get_current_language, tr

logger = logging.getLogger("ImproveImgSLI")

# Progress checkpoints for the "loading full version of image" toast: 0 at
# the quick preview, DECODE_DONE_PROGRESS once the full-res decode lands,
# PYRAMID_START_PROGRESS..100 tracking pyramid level build-out (skipped
# straight to 100 for stores that need no pyramid).
DECODE_DONE_PROGRESS = 20
PYRAMID_START_PROGRESS = 40


def get_toast_manager(controller):
    # controller.presenter is a MainWindowPresenter, not the window shell
    # itself -- it owns main_window_app, which is where toast_manager
    # actually lives (see ExportSaveFlowCoordinator._get_toast_manager,
    # the same lookup used by the save-image toast).
    toast_manager = getattr(
        getattr(controller.presenter, "main_window_app", None), "toast_manager", None
    )
    if toast_manager is None:
        logger.debug(
            "[FullImageLoad] no toast_manager available (presenter=%r)",
            controller.presenter,
        )
    return toast_manager


def show_loading_toast(controller, image_number: int) -> None:
    if image_number in controller._loading_toasts:
        return
    toast_manager = get_toast_manager(controller)
    if toast_manager is None:
        return
    message = tr("msg.loading_full_image_in_progress", get_current_language())
    try:
        controller._loading_toasts[image_number] = toast_manager.show_toast(
            message, duration=0, progress=0
        )
        logger.debug(
            "[FullImageLoad] toast shown (slot=%s toast_id=%s msg=%r)",
            image_number,
            controller._loading_toasts[image_number],
            message,
        )
    except Exception:
        logger.exception("Failed to show full-image loading toast")


def set_loading_toast_progress(controller, image_number: int, percent: int) -> None:
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.get(image_number)
    if toast_manager is None or toast_id is None:
        logger.debug(
            "[FullImageLoad] skip toast update (slot=%s toast_manager=%s "
            "toast_id=%s percent=%d)",
            image_number,
            toast_manager is not None,
            toast_id,
            percent,
        )
        return
    try:
        toast_manager.update_toast(
            toast_id,
            tr("msg.loading_full_image_in_progress", get_current_language()),
            success=False,
            duration=0,
            progress=max(0, min(99, percent)),
        )
    except Exception:
        logger.exception("Failed to update full-image loading toast")


def mark_full_res_ready(controller, image_number: int) -> None:
    set_loading_toast_progress(controller, image_number, DECODE_DONE_PROGRESS)


def bump_loading_toast_pyramid_started(controller, image_number: int) -> None:
    set_loading_toast_progress(controller, image_number, PYRAMID_START_PROGRESS)


def finish_loading_toast(controller, image_number: int) -> None:
    toast_manager = get_toast_manager(controller)
    toast_id = controller._loading_toasts.pop(image_number, None)
    if toast_manager is None or toast_id is None:
        return
    try:
        toast_manager.update_toast(
            toast_id,
            tr("msg.loading_full_image_done", get_current_language()),
            success=True,
            duration=2000,
            progress=100,
        )
        logger.debug(
            "[FullImageLoad] toast done (slot=%s toast_id=%s)",
            image_number,
            toast_id,
        )
    except Exception:
        logger.exception("Failed to complete full-image loading toast")


def start_pyramid_builds(controller, *stores) -> None:
    # Called as start_pyramid_builds(controller, u1, u2) -- positional order
    # matches image_state.image1/image2 at the call site, so slot number is
    # simply the 1-based position here.
    from shared.image_processing import pyramid_registry
    from shared.image_processing.pyramid_pixel_store import estimate_total_levels
    from shared.rendering.image_identity import image_uid

    task_id = controller._unification_task_id
    for slot_offset, store in enumerate(stores):
        image_number = slot_offset + 1
        # A cheap preview-resolution unify races ahead of the real
        # full-res decode and can hit this same method with a trivial,
        # already-complete pyramid. Only let the toast react once the
        # slot's real decode has actually landed -- otherwise it closes
        # over stale preview data before the real progress ever starts.
        slot_toast_live = controller._pending_full_loads.get(image_number, 0) == 0
        pyramid = pyramid_registry.ensure_pyramid(store)
        if pyramid is None:
            logger.debug(
                "[Pyramid] skip build: no pyramid for store %dx%d",
                getattr(store, "width", -1),
                getattr(store, "height", -1),
            )
            if slot_toast_live:
                controller._finish_loading_toast(image_number)
            continue
        if pyramid.is_complete():
            logger.debug(
                "[Pyramid] skip build: already complete for store %dx%d "
                "(levels=%d)",
                store.width,
                store.height,
                pyramid.level_count,
            )
            if slot_toast_live:
                controller._finish_loading_toast(image_number)
            continue
        uid = image_uid(store)
        if uid in controller._pyramid_builds:
            logger.debug("[Pyramid] skip build: already in flight (uid=%s)", uid)
            continue
        controller._pyramid_builds.add(uid)
        logger.info(
            "[Pyramid] build started for store %dx%d (uid=%s)",
            store.width,
            store.height,
            uid,
        )
        total_levels = estimate_total_levels(store.width, store.height)
        if slot_toast_live:
            controller._loading_toast_uid_slot[uid] = image_number
            controller._bump_loading_toast_pyramid_started(image_number)
        worker = GenericWorker(
            controller._pyramid_build_task, pyramid, task_id, uid, total_levels
        )
        worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
        worker.signals.partial_result.connect(controller._on_pyramid_level_ready)
        worker.signals.finished.connect(
            lambda uid=uid: controller._pyramid_builds.discard(uid)
        )
        controller.thread_pool.start(worker)


def pyramid_build_task(
    controller, pyramid, task_id, uid, total_levels, progress_callback=None
):
    # A newer unification supersedes this pair; abort at the next strip.
    # Base-store closure aborts independently via pyramid validity.
    def should_abort() -> bool:
        return task_id != controller._unification_task_id

    while pyramid.build_next_level(should_abort=should_abort):
        complete = pyramid.is_complete()
        if progress_callback is not None:
            progress_callback((uid, pyramid.level_count, total_levels, complete))
    return None


def on_pyramid_level_ready(controller, payload) -> None:
    uid, level_count, total_levels, complete = payload
    # Only a *completed* pyramid can flip pick_display_image from the
    # preview tier to the tiled store — that's the only publish that
    # needs the pick signatures dropped. Intermediate levels just need
    # a repaint so the per-frame LOD selector can use them; a full
    # invalidation per level caused plan re-applies mid-interaction
    # (docs/dev/rendering/display-image-pipeline.md, preview→store flip).
    if complete:
        controller._invalidate_image_canvas_render_state()
    controller._schedule_image_canvas_update()
    image_number = controller._loading_toast_uid_slot.get(uid)
    if image_number is None:
        return
    if complete:
        controller._loading_toast_uid_slot.pop(uid, None)
        controller._finish_loading_toast(image_number)
    else:
        fraction = level_count / max(total_levels, 1)
        percent = PYRAMID_START_PROGRESS + int(
            fraction * (100 - PYRAMID_START_PROGRESS)
        )
        controller._set_loading_toast_progress(image_number, percent)


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


def _defer_mixed_unify(controller, document) -> bool:
    """True when unify would upscale a preview to full-res size for nothing.

    A mixed pair (one side full-res, the other still a preview) with the
    preview side's full decode in flight produces a doomed unify: LANCZOS
    upscaling a ~1k preview to a 20k canvas for minutes, superseded the
    moment the real pixels land. Defer; the finishing load re-triggers.
    """
    full1 = document.full_res_image1 is not None
    full2 = document.full_res_image2 is not None
    if full1 == full2:
        return False
    waiting_slot = 2 if full1 else 1
    pending = getattr(controller, "_pending_full_loads", None)
    if pending is None:
        return False
    if pending.get(waiting_slot, 0) > 0:
        logger.info(
            "[Unify] deferred: slot %d full-res decode still in flight",
            waiting_slot,
        )
        return True
    return False


def _finish_toast_for_unpaired_slot(controller, document, image_number: int) -> None:
    """Unify -- and the pyramid build that normally closes the loading
    toast -- only ever runs once both slots hold an image. When the other
    slot has no image at all, unify will never fire, so the toast for this
    slot would otherwise hang forever. Close it here once this slot's own
    full-res decode has actually landed.
    """
    own_full = getattr(document, f"full_res_image{image_number}", None)
    other_number = 2 if image_number == 1 else 1
    other_path = getattr(document, f"image{other_number}_path", None)
    if own_full is not None and not other_path:
        controller._finish_loading_toast(image_number)


def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(
            ["file_names", "resolution"]
        )

    document = controller.store.get_session_state_slot("document")
    source1 = document.full_res_image1 or document.preview_image1
    source2 = document.full_res_image2 or document.preview_image2

    if source1 and source2 and not _defer_mixed_unify(controller, document):
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
        _finish_toast_for_unpaired_slot(controller, document, image_number)

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

    if not isinstance(full_img, TiledPixelStore):
        full_img = maybe_wrap_pixel_store(full_img)
    item = target_list[index_in_list]
    item.image = full_img

    # A superseded worker (user already switched this slot to another
    # index while this decode was in flight) must not overwrite the live
    # slot -- only cache the decoded pixels on the list item above. Doing
    # the overwrite unconditionally races multiple in-flight decodes for
    # the same slot and corrupts document.full_res_imageN/pathN with
    # whichever one happens to finish last (rapid Space+click bug).
    current_app_index = (
        document.current_index1 if image_number == 1 else document.current_index2
    )
    if index_in_list != current_app_index:
        return

    outgoing = getattr(document, f"full_res_image{image_number}", None)
    other = 2 if image_number == 1 else 1
    other_full = getattr(document, f"full_res_image{other}", None)
    if outgoing is not None and outgoing is not other_full:
        close_pixel_store(outgoing)
    controller._update_image_slot(
        image_number, image=full_img, path=path, is_full_res=True
    )
    controller._mark_full_res_ready(image_number)
    # Deliberately not _invalidate_diff_cache(controller) here: this is a
    # swap (a new image replacing an already-displayed one), not a removal
    # -- clearing cached_diff_image upfront would blank the diff overlay
    # for the whole time it takes render_flow.py's
    # request_cached_diff_image_async to notice the source pair changed
    # (via cached_diff_source_key) and recompute, showing a diff-vanishes/
    # plain-image/diff-reappears flash. Leaving the stale diff in place
    # lets the canvas keep showing it until the new one is ready, then
    # swap atomically (docs/dev/KNOWN_BUGS.md same-slot-swap SSIM
    # follow-up).

    def trigger_unification():
        live_document = controller.store.get_session_state_slot("document")
        source1 = live_document.full_res_image1 or live_document.preview_image1
        source2 = live_document.full_res_image2 or live_document.preview_image2
        if _defer_mixed_unify(controller, live_document):
            return
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
            _finish_toast_for_unpaired_slot(controller, live_document, image_number)

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
        from ui.widgets.unified_list_picker import FlyoutMode

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
            from ui.widgets.unified_list_picker import FlyoutMode

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
                "image_compare.msg.some_images_could_not_be_loaded",
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
    # Not _invalidate_diff_cache(controller): a swap, see the matching
    # comment above _mark_full_res_ready's call site.
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_magnifier=False)
    controller._schedule_image_canvas_update()

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
        controller._start_pyramid_builds(u1, u2)
        # Not _invalidate_diff_cache(controller): a swap, see the matching
        # comment above _mark_full_res_ready's call site.
        controller.store.invalidate_render_cache()
        controller._invalidate_image_canvas_render_state(clear_magnifier=False)
        controller._schedule_image_canvas_update()

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



def resync_current_image_slots(controller) -> None:
    """Re-sync the displayed image after undo/redo of browsing.

    Undo/redo restores the document reference snapshot: the index points
    back at the previous entry, but the slot's pixels may reference the
    closed ``TiledPixelStore`` of the image that was loaded after the undo
    entry was recorded (loading closes the replaced store). Reload the
    current entry from the list (path+reload) when the stored path diverges
    from the list entry or the full-res store is closed. A healthy slot —
    normal loads already match — is left untouched.
    """
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    for image_number, image_list, current_index, image_path, full_res in (
        (
            1,
            document.image_list1,
            document.current_index1,
            document.image1_path,
            document.full_res_image1,
        ),
        (
            2,
            document.image_list2,
            document.current_index2,
            document.image2_path,
            document.full_res_image2,
        ),
    ):
        if not (0 <= current_index < len(image_list)):
            continue
        item = image_list[current_index]
        stale = image_path != item.path
        if not stale:
            is_open = getattr(full_res, "is_open", None)
            stale = is_open is not None and not is_open
        if stale:
            # Through the controller's public seam (which delegates back to
            # this module) so callers/tests can stub the reload decision.
            controller.set_current_image(image_number, force_refresh=True)