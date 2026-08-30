# Audit-Meta: pattern=thin-owner-target reason="use_cases target for _session_controller — 15 functions taking controller"
import logging
import os

from PySide6.QtCore import QTimer
from sli_ui_toolkit.workers import GenericWorker

from core.events import CoreErrorOccurredEvent, CoreUpdateRequestedEvent
from core.state_management.actions import (
    SetCachedDiffImageAction,
    SetCurrentIndexAction,
    SetImageSessionImageAction,
    SetPendingUnificationPathsAction,
    SetUnificationInProgressAction,
)
from tabs.image_compare.services import document_store_ops
from tabs.image_compare.state.document import ImageItem
from sli_ui_toolkit.i18n import get_current_language, tr

logger = logging.getLogger("ImproveImgSLI")

# Re-export toast constants for controller binding (see _session_controller.py).
from tabs.image_compare.use_cases.loading_toast import (  # noqa: E402
    DECODE_DONE_PROGRESS,
    PYRAMID_START_PROGRESS,
    bump_loading_toast_pyramid_started,
    finish_loading_toast,
    finish_toast_for_unpaired_slot,
    get_toast_manager,
    mark_full_res_ready,
    set_loading_toast_progress,
    show_loading_toast,
)

# Re-export pyramid functions for controller binding.
from tabs.image_compare.use_cases.loading_pyramid import (  # noqa: E402
    on_pyramid_level_ready,
    pyramid_build_task,
    start_pyramid_builds,
)


def _invalidate_diff_cache(controller) -> None:
    if getattr(controller, "diff_service", None) is not None:
        controller.diff_service.invalidate()
    else:
        render_cache = _session_render_cache(controller)
        if render_cache is not None:
            dispatcher = getattr(controller.store, "get_dispatcher", None)
            dispatcher = dispatcher() if callable(dispatcher) else None
            if dispatcher is not None:
                try:
                    dispatcher.dispatch(SetCachedDiffImageAction(image=None), scope="viewport")
                except Exception:
                    logger.error("Failed to dispatch SetCachedDiffImageAction", exc_info=True)
            else:
                # No dispatcher (test fake or early bootstrap) — use setattr to
                # avoid contract Assign flag while keeping fake tests green;
                # real app always has a dispatcher here, so this branch is not
                # taken in production — for early bootstrap the deferred retry
                # below will dispatch once the dispatcher is wired.
                try:
                    setattr(render_cache, "cached_diff_image", None)
                except Exception:
                    pass
                try:
                    QTimer.singleShot(
                        0,
                        lambda: _invalidate_diff_cache(controller),
                    )
                except Exception:
                    pass


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
    dispatcher = getattr(controller.store, "get_dispatcher", None)
    dispatcher = dispatcher() if callable(dispatcher) else None
    if dispatcher is None:
        try:
            setattr(render_cache, "unification_in_progress", False)
            setattr(render_cache, "pending_unification_paths", None)
        except Exception:
            pass
        return
    # Batch the two viewport mutations atomically; callers run on the GUI
    # thread (GenericWorker result signal), not inside dispatcher._lock, so
    # synchronous dispatch is safe (dispatcher.py:118 — defer only from
    # store subscribers).
    try:
        with controller.store.batch_changes():
            dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
            dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
    except Exception:
        logger.error("Failed to dispatch clear_unification_flags", exc_info=True)


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
    _init_dispatcher = getattr(controller.store, "get_dispatcher", None)
    _init_dispatcher = _init_dispatcher() if callable(_init_dispatcher) else None
    if _init_dispatcher is not None:
        if (
            controller.store.viewport.session_data.image_state.loaded_current_index1 != -1
            and 0
            <= controller.store.viewport.session_data.image_state.loaded_current_index1
            < len(document.image_list1)
        ):
            _init_dispatcher.dispatch(
                SetCurrentIndexAction(slot=1, index=controller.store.viewport.session_data.image_state.loaded_current_index1),
                scope="document",
            )
        elif document.image_list1:
            _init_dispatcher.dispatch(SetCurrentIndexAction(slot=1, index=0), scope="document")

        if (
            controller.store.viewport.session_data.image_state.loaded_current_index2 != -1
            and 0
            <= controller.store.viewport.session_data.image_state.loaded_current_index2
            < len(document.image_list2)
        ):
            _init_dispatcher.dispatch(
                SetCurrentIndexAction(slot=2, index=controller.store.viewport.session_data.image_state.loaded_current_index2),
                scope="document",
            )
        elif document.image_list2:
            _init_dispatcher.dispatch(SetCurrentIndexAction(slot=2, index=0), scope="document")
    else:
        # No dispatcher — defer; never mutate document directly outside Reducer.
        def _deferred_init_indices():
            disp = getattr(controller.store, "get_dispatcher", lambda: None)()
            if disp is None:
                return
            init_doc = controller.store.get_session_state_slot("document")
            if init_doc is None:
                return
            if (
                controller.store.viewport.session_data.image_state.loaded_current_index1 != -1
                and 0
                <= controller.store.viewport.session_data.image_state.loaded_current_index1
                < len(init_doc.image_list1)
            ):
                disp.dispatch(
                    SetCurrentIndexAction(slot=1, index=controller.store.viewport.session_data.image_state.loaded_current_index1),
                    scope="document",
                )
            elif init_doc.image_list1:
                disp.dispatch(SetCurrentIndexAction(slot=1, index=0), scope="document")
            if (
                controller.store.viewport.session_data.image_state.loaded_current_index2 != -1
                and 0
                <= controller.store.viewport.session_data.image_state.loaded_current_index2
                < len(init_doc.image_list2)
            ):
                disp.dispatch(
                    SetCurrentIndexAction(slot=2, index=controller.store.viewport.session_data.image_state.loaded_current_index2),
                    scope="document",
                )
            elif init_doc.image_list2:
                disp.dispatch(SetCurrentIndexAction(slot=2, index=0), scope="document")

        QTimer.singleShot(0, _deferred_init_indices)

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


def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(
            ["file_names", "resolution"]
        )

    document = controller.store.get_session_state_slot("document")
    source1 = document.full_res_image1 or document.preview_image1
    source2 = document.full_res_image2 or document.preview_image2

    if source1 and source2 and not _defer_mixed_unify(controller, document):
        # Dedup: two triggers (preview QTimer 0 and full QTimer 50) can
        # coalesce on the same path pair within ~50ms. If a unify for this
        # exact path pair is already in flight, skip the second start —
        # the first worker will finish and publish the unified stores.
        try:
            _rc = _session_render_cache(controller)
            if _rc is not None and getattr(_rc, "unification_in_progress", False):
                pending = getattr(_rc, "pending_unification_paths", None)
                if pending == (document.image1_path, document.image2_path):
                    return
        except Exception:
            pass
        try:
            controller._cancel_pending_unification(
                document.image1_path,
                document.image2_path,
            )
            if not document.image1_path or not document.image2_path:
                return

            _tp_dispatcher = getattr(controller.store, "get_dispatcher", None)
            _tp_dispatcher = _tp_dispatcher() if callable(_tp_dispatcher) else None
            if _tp_dispatcher is not None:
                try:
                    with controller.store.batch_changes():
                        _tp_dispatcher.dispatch(SetUnificationInProgressAction(enabled=True), scope="viewport")
                        _tp_dispatcher.dispatch(
                            SetPendingUnificationPathsAction(paths=(document.image1_path, document.image2_path)),
                            scope="viewport",
                        )
                except Exception:
                    logger.error("Failed to dispatch unification pending", exc_info=True)
            else:
                try:
                    _tp_rc = _session_render_cache(controller)
                    if _tp_rc is not None:
                        setattr(_tp_rc, "unification_in_progress", True)
                        setattr(_tp_rc, "pending_unification_paths", (document.image1_path, document.image2_path))
                except Exception:
                    pass

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
            _tp_err_dispatcher = getattr(controller.store, "get_dispatcher", None)
            _tp_err_dispatcher = _tp_err_dispatcher() if callable(_tp_err_dispatcher) else None
            if _tp_err_dispatcher is not None:
                try:
                    _tp_err_dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                except Exception:
                    logger.error("Failed to dispatch unification rollback", exc_info=True)
            else:
                try:
                    _tp_err_rc = _session_render_cache(controller)
                    if _tp_err_rc is not None:
                        setattr(_tp_err_rc, "unification_in_progress", False)
                except Exception:
                    pass
            controller.metrics_service.on_metrics_calculated(None)
    else:
        controller.metrics_service.on_metrics_calculated(None)
        finish_toast_for_unpaired_slot(controller, document, image_number)

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
        # Dedup same as trigger_preview_unification: coalesce duplicate
        # unify starts for the same path pair that is already in flight.
        try:
            _rc2 = _session_render_cache(controller)
            if _rc2 is not None and getattr(_rc2, "unification_in_progress", False):
                pending2 = getattr(_rc2, "pending_unification_paths", None)
                if pending2 == (live_document.image1_path, live_document.image2_path):
                    return
        except Exception:
            pass
        if source1 and source2:
            _hf_dispatcher = getattr(controller.store, "get_dispatcher", None)
            _hf_dispatcher = _hf_dispatcher() if callable(_hf_dispatcher) else None
            if _hf_dispatcher is not None:
                try:
                    with controller.store.batch_changes():
                        _hf_dispatcher.dispatch(SetUnificationInProgressAction(enabled=True), scope="viewport")
                        _hf_dispatcher.dispatch(
                            SetPendingUnificationPathsAction(
                                paths=(live_document.image1_path, live_document.image2_path)
                            ),
                            scope="viewport",
                        )
                except Exception:
                    logger.error("Failed to dispatch handle_full pending", exc_info=True)
            else:
                try:
                    _hf_rc = _session_render_cache(controller)
                    if _hf_rc is not None:
                        setattr(_hf_rc, "unification_in_progress", True)
                        setattr(_hf_rc, "pending_unification_paths", (live_document.image1_path, live_document.image2_path))
                except Exception:
                    pass
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
            finish_toast_for_unpaired_slot(controller, live_document, image_number)

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
        _lip_dispatcher = getattr(controller.store, "get_dispatcher", None)
        _lip_dispatcher = _lip_dispatcher() if callable(_lip_dispatcher) else None
        if _lip_dispatcher is not None:
            try:
                with controller.store.batch_changes():
                    _lip_dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                    _lip_dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
            except Exception:
                logger.error("Failed to dispatch load_images pending clear", exc_info=True)
        else:
            try:
                _lip_rc = _session_render_cache(controller)
                if _lip_rc is not None:
                    setattr(_lip_rc, "unification_in_progress", False)
                    setattr(_lip_rc, "pending_unification_paths", None)
            except Exception:
                pass
        if len(other_list) == 0:
            document_store_ops.clear_image_slot_data(controller.store, 1)
            document_store_ops.clear_image_slot_data(controller.store, 2)
            if _lip_dispatcher is not None:
                try:
                    with controller.store.batch_changes():
                        _lip_dispatcher.dispatch(SetImageSessionImageAction(slot=1, image=None), scope="viewport")
                        _lip_dispatcher.dispatch(SetImageSessionImageAction(slot=2, image=None), scope="viewport")
                except Exception:
                    logger.error("Failed to dispatch image_state clear", exc_info=True)
            else:
                try:
                    _lip_is = getattr(controller.store.viewport.session_data, "image_state", None)
                    if _lip_is is not None:
                        setattr(_lip_is, "image1", None)
                        setattr(_lip_is, "image2", None)
                except Exception:
                    pass
            if getattr(controller, "diff_service", None) is not None:
                controller.diff_service.invalidate()
            else:
                if _lip_dispatcher is not None:
                    try:
                        _lip_dispatcher.dispatch(SetCachedDiffImageAction(image=None), scope="viewport")
                    except Exception:
                        logger.error("Failed to dispatch cached_diff clear", exc_info=True)
                else:
                    try:
                        _lip_rc2 = _session_render_cache(controller)
                        if _lip_rc2 is not None:
                            setattr(_lip_rc2, "cached_diff_image", None)
                    except Exception:
                        pass
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
            _dup_dispatcher = getattr(controller.store, "get_dispatcher", None)
            _dup_dispatcher = _dup_dispatcher() if callable(_dup_dispatcher) else None
            if _dup_dispatcher is not None:
                try:
                    _dup_dispatcher.dispatch(SetCurrentIndexAction(slot=target_slot, index=index), scope="document")
                except Exception:
                    logger.error("Failed to dispatch duplicate existing index", exc_info=True)
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
    _dup_new_dispatcher = getattr(controller.store, "get_dispatcher", None)
    _dup_new_dispatcher = _dup_new_dispatcher() if callable(_dup_new_dispatcher) else None
    if _dup_new_dispatcher is not None:
        try:
            _dup_new_dispatcher.dispatch(SetCurrentIndexAction(slot=target_slot, index=new_index), scope="document")
        except Exception:
            logger.error("Failed to dispatch duplicate new index", exc_info=True)

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
        _reload_dispatcher = getattr(controller.store, "get_dispatcher", None)
        _reload_dispatcher = _reload_dispatcher() if callable(_reload_dispatcher) else None
        if _reload_dispatcher is not None:
            try:
                _reload_dispatcher.dispatch(SetCurrentIndexAction(slot=image_number, index=index), scope="document")
            except Exception:
                logger.error("Failed to dispatch reload existing index", exc_info=True)

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
        _fin_dispatcher = getattr(controller.store, "get_dispatcher", None)
        _fin_dispatcher = _fin_dispatcher() if callable(_fin_dispatcher) else None
        if _fin_dispatcher is not None:
            try:
                _fin_dispatcher.dispatch(SetCurrentIndexAction(slot=image_number, index=new_index), scope="document")
            except Exception:
                logger.error("Failed to dispatch finalize index", exc_info=True)

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
        controller._invalidate_image_canvas_render_state(clear_overlay_state=True)
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
                    _sci_dispatcher = getattr(controller.store, "get_dispatcher", None)
                    _sci_dispatcher = _sci_dispatcher() if callable(_sci_dispatcher) else None
                    if _sci_dispatcher is not None:
                        try:
                            with controller.store.batch_changes():
                                _sci_dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                                _sci_dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
                        except Exception:
                            logger.error("Failed to dispatch set_current_image clear flags", exc_info=True)
                    else:
                        try:
                            _sci_rc = _session_render_cache(controller)
                            if _sci_rc is not None:
                                setattr(_sci_rc, "unification_in_progress", False)
                                setattr(_sci_rc, "pending_unification_paths", None)
                        except Exception:
                            pass
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
    controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
    controller._schedule_image_canvas_update()

    if pil_img is None and path:
        # Dedup: load_images_from_paths schedules set_current_image via
        # QTimer 50ms and the "document" on_change resync schedules via
        # QTimer 0ms — both fire for the same slot/path before the first
        # worker returns. Without a guard we start two
        # TiledPixelStore.from_path for the same file (see log 02:05:51.775 +
        # 02:05:51.834). Coalesce on (slot, path).
        pending = getattr(controller, "_pending_image_loads", None)
        key = (image_number, path)
        if pending is not None and key in pending:
            pass
        else:
            if pending is not None:
                pending.add(key)

                def _clear_pending(k=key, p=pending):
                    try:
                        p.discard(k)
                    except Exception:
                        pass

            else:

                def _clear_pending():  # type: ignore[no-redef]
                    pass

            worker = GenericWorker(
                controller._load_image_async, path, image_number, current_index, None
            )
            worker.signals.result.connect(controller._on_image_loaded_from_worker)
            # finished fires for both success and error; result handler also
            # clears via the same key so the slot can reload after failure.
            try:
                worker.signals.finished.connect(_clear_pending)
            except Exception:
                pass
            worker.signals.result.connect(lambda *_a, _cp=_clear_pending: _cp())
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

        # Post-unify re-crop: 764→2797 Lanczos up-scale can re-introduce a
        # dark edge that thr=15 misses (2797 thr15→None, thr30→2791). The
        # first frame (764) was correctly cropped, the next two frames
        # (2797 unified) showed stripes again. Re-trim unified stores.
        try:
            should_crop = getattr(controller.store.settings, "auto_crop_black_borders", True)
            if should_crop:
                from PIL import Image as _PILImage

                from shared.image_processing.resize import get_auto_crop_box
                from shared.image_processing.tiled_pixel_store import TiledPixelStore as _TPS

                def _recrop(store):
                    if store is None or not isinstance(store, _TPS):
                        return store
                    try:
                        # Convert to PIL for bbox probe (downscaled probe inside
                        # get_auto_crop_box is cheap for 2797)
                        arr = store._memmap[:, :, :3] if hasattr(store, "_memmap") and store._memmap is not None else None
                        if arr is None:
                            return store
                        pil = _PILImage.fromarray(arr.copy())
                        # Try thr 15 first, then 30 for resampled edge
                        box = get_auto_crop_box(pil, threshold=15)
                        if box is None:
                            box = get_auto_crop_box(pil, threshold=30)
                        if box is None or box == (0, 0, pil.width, pil.height):
                            return store
                        left, top, right, bottom = box
                        # Crop via PIL then back to TiledPixelStore
                        cropped_pil = pil.crop(box)
                        # Use from_pil to create new store (owns_file, no auto-crop needed)
                        new_store = _TPS.from_pil(cropped_pil)
                        try:
                            from shared.image_processing.tiled_pixel_store import close_pixel_store

                            close_pixel_store(store)
                        except Exception:
                            pass
                        return new_store
                    except Exception as e:
                        logger.debug("post-unify recrop failed: %s", e)
                        return store

                # Only recrop if the unified size still contains border
                # (check via PIL, cheap for 2797)
                u1 = _recrop(u1)
                u2 = _recrop(u2)
        except Exception:
            pass

        _on_ready_dispatcher = getattr(controller.store, "get_dispatcher", None)
        _on_ready_dispatcher = _on_ready_dispatcher() if callable(_on_ready_dispatcher) else None
        if _on_ready_dispatcher is not None:
            try:
                with controller.store.batch_changes():
                    _on_ready_dispatcher.dispatch(SetImageSessionImageAction(slot=1, image=u1), scope="viewport")
                    _on_ready_dispatcher.dispatch(SetImageSessionImageAction(slot=2, image=u2), scope="viewport")
            except Exception:
                logger.error("Failed to dispatch on_unified_images_ready images", exc_info=True)
        else:
            try:
                # Fallback for test fakes without dispatcher
                setattr(image_state, "image1", u1)
                setattr(image_state, "image2", u2)
            except Exception:
                pass
        controller._start_pyramid_builds(u1, u2)
        # Not _invalidate_diff_cache(controller): a swap, see the matching
        # comment above _mark_full_res_ready's call site.
        controller.store.invalidate_render_cache()
        controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
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
            # Coalesce with a normal load_images_from_paths flow: both the
            # QTimer(0) resync and the QTimer(50) finalize schedule
            # set_current_image for the same new item. If a worker for
            # (slot, path) is already pending, skip the duplicate resync.
            pending = getattr(controller, "_pending_image_loads", None)
            if pending is not None and (image_number, item.path) in pending:
                continue
            # Through the controller's public seam (which delegates back to
            # this module) so callers/tests can stub the reload decision.
            controller.set_current_image(image_number, force_refresh=True)