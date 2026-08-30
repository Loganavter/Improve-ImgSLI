# Pipeline-based loading — replaces 946-LOC brute-force brute.
# Demand-driven, single-flight via PipelineCache, one Store.transact per image change.
# See docs/dev/plan_image_pipeline.md Phase 2–3.
import logging
import os

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
from sli_ui_toolkit.i18n import tr

logger = logging.getLogger("ImproveImgSLI")

# Re-export toast/pyramid for controller binding (Phase 1 skeleton keeps API)
from tabs.image_compare.use_cases.loading_toast import (  # noqa: E402,F401
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
from tabs.image_compare.use_cases.loading_pyramid import (  # noqa: E402,F401
    on_pyramid_level_ready,
    pyramid_build_task,
    start_pyramid_builds,
)


def _session_render_cache(controller):
    sd = getattr(controller.store.viewport, "session_data", None)
    return getattr(sd, "render_cache", None) if sd else None


def _invalidate_diff_cache(controller) -> None:
    if getattr(controller, "diff_service", None) is not None:
        controller.diff_service.invalidate()
        return
    rc = _session_render_cache(controller)
    if rc is None:
        return
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d is None:
        return
    try:
        d.dispatch(SetCachedDiffImageAction(image=None), scope="viewport")
    except Exception:
        logger.error("Failed to dispatch SetCachedDiffImageAction", exc_info=True)


def _clear_unification_flags(controller) -> None:
    rc = _session_render_cache(controller)
    if rc is None:
        return
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d is None:
        return
    try:
        with controller.store.batch_changes():
            d.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
            d.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
    except Exception:
        logger.error("Failed to clear unification flags", exc_info=True)


def _unify_resize_method(controller) -> str:
    from shared.rendering.interpolation import get_effective_main_interpolation_method

    return get_effective_main_interpolation_method(controller.store.viewport)


def ensure_unification(controller, delay_ms: int = 0) -> None:
    """Demand-driven unify via PipelineCache (memo by uid). No QTimer dedup."""
    # delay_ms kept for API compat — pipeline is sync-memo, delay is no-op.
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    s1 = document.full_res_image1 or document.preview_image1
    s2 = document.full_res_image2 or document.preview_image2
    if not (s1 and s2):
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass
        return
    # Pipeline memo: if already unified for these uids+method, skip worker.
    pl = getattr(controller, "pipeline", None)
    if pl is not None:
        try:
            method = _unify_resize_method(controller)
            # peek unify cache without decode
            cached = pl.cache.get_unified(
                getattr(s1, "uid", id(s1)), getattr(s2, "uid", id(s2)), method, 0, 0
            )
            # 0,0 is wildcard — real size memo is inside ensure_unified; treat None as miss
            _ = cached  # keep for future size-aware memo
        except Exception:
            pass
    rc = _session_render_cache(controller)
    if rc is not None and getattr(rc, "unification_in_progress", False):
        pending = getattr(rc, "pending_unification_paths", None)
        if pending == (document.image1_path, document.image2_path):
            return
    if not document.image1_path or not document.image2_path:
        return
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d is not None:
        try:
            with controller.store.batch_changes():
                d.dispatch(SetUnificationInProgressAction(enabled=True), scope="viewport")
                d.dispatch(
                    SetPendingUnificationPathsAction(paths=(document.image1_path, document.image2_path)),
                    scope="viewport",
                )
        except Exception:
            logger.error("Failed to dispatch unification pending", exc_info=True)
    try:
        controller._unification_task_id += 1
        tid = controller._unification_task_id
        worker = GenericWorker(
            controller._unify_images_worker_task,
            s1, s2, document.image1_path, document.image2_path, tid, _unify_resize_method(controller),
        )
        worker.signals.result.connect(controller._on_unified_images_ready)
        controller.thread_pool.start(worker, priority=1)
    except Exception:
        _clear_unification_flags(controller)
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass


def ensure_current_slot(controller, image_number: int, force_refresh: bool = False) -> bool:
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return False
    lst = document.image_list1 if image_number == 1 else document.image_list2
    idx = document.current_index1 if image_number == 1 else document.current_index2
    path = document.image1_path if image_number == 1 else document.image2_path
    full = document.full_res_image1 if image_number == 1 else document.full_res_image2
    if not (0 <= idx < len(lst)):
        return False
    item = lst[idx]
    stale = path != item.path or (getattr(full, "is_open", None) is not None and not full.is_open)
    if stale or force_refresh:
        try:
            controller.set_current_image(image_number, force_refresh=force_refresh)
        except Exception:
            pass
        return True
    return False


def initialize_app_display(controller):
    if controller.store.get_session_state_slot("document") is None:
        return
    # History already in DocumentModel as path-only ImageItems — no preload.
    # Just ensure current indices are valid (single dispatch each).
    document = controller.store.get_session_state_slot("document")
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d is not None:
        isd = controller.store.viewport.session_data.image_state
        if 0 <= isd.loaded_current_index1 < len(document.image_list1):
            d.dispatch(SetCurrentIndexAction(slot=1, index=isd.loaded_current_index1), scope="document")
        elif document.image_list1:
            d.dispatch(SetCurrentIndexAction(slot=1, index=0), scope="document")
        if 0 <= isd.loaded_current_index2 < len(document.image_list2):
            d.dispatch(SetCurrentIndexAction(slot=2, index=isd.loaded_current_index2), scope="document")
        elif document.image_list2:
            d.dispatch(SetCurrentIndexAction(slot=2, index=0), scope="document")
    controller.set_current_image(1, emit_signal=False)
    controller.set_current_image(2, emit_signal=False)
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(["combobox", "file_names", "resolution", "ratings"])
        controller.presenter.update_minimum_window_size()
    controller.store.emit_state_change("document")


def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(["file_names", "resolution"])
    ensure_unification(controller)


def handle_full_image_loaded(controller, full_img, path, image_number, index_in_list):
    if not full_img:
        return
    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    if not (0 <= index_in_list < len(lst)) or lst[index_in_list].path != path:
        return
    from shared.image_processing.tiled_pixel_store import TiledPixelStore, close_pixel_store, maybe_wrap_pixel_store

    if not isinstance(full_img, TiledPixelStore):
        full_img = maybe_wrap_pixel_store(full_img)
    lst[index_in_list].image = full_img
    cur = document.current_index1 if image_number == 1 else document.current_index2
    if index_in_list != cur:
        return
    outgoing = getattr(document, f"full_res_image{image_number}", None)
    other = 2 if image_number == 1 else 1
    other_full = getattr(document, f"full_res_image{other}", None)
    if outgoing is not None and outgoing is not other_full:
        close_pixel_store(outgoing)
    controller._update_image_slot(image_number, image=full_img, path=path, is_full_res=True)
    controller._mark_full_res_ready(image_number)
    ensure_unification(controller)


def load_images_from_paths(controller, file_paths: list[str], image_number: int):
    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    is_new = len(lst) == 0
    if is_new:
        other = 2 if image_number == 1 else 1
        other_lst = document.image_list1 if other == 1 else document.image_list2
        d = getattr(controller.store, "get_dispatcher", lambda: None)()
        if d is not None:
            try:
                with controller.store.batch_changes():
                    d.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                    d.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
            except Exception:
                pass
        if len(other_lst) == 0:
            document_store_ops.clear_image_slot_data(controller.store, 1)
            document_store_ops.clear_image_slot_data(controller.store, 2)
            if d is not None:
                try:
                    with controller.store.batch_changes():
                        d.dispatch(SetImageSessionImageAction(slot=1, image=None), scope="viewport")
                        d.dispatch(SetImageSessionImageAction(slot=2, image=None), scope="viewport")
                except Exception:
                    pass
            if getattr(controller, "diff_service", None) is not None:
                controller.diff_service.invalidate()
            elif d is not None:
                try:
                    d.dispatch(SetCachedDiffImageAction(image=None), scope="viewport")
                except Exception:
                    pass
        else:
            stale = bool(document.full_res_image1 or document.image1_path) if image_number == 1 else bool(document.full_res_image2 or document.image2_path)
            if stale:
                document_store_ops.clear_image_slot_data(controller.store, image_number)

    errors, new_idx = [], []
    seen = {e.path for e in lst if e.path}
    for fp in file_paths:
        if not isinstance(fp, str) or not fp:
            errors.append(f"{fp}: {tr('msg.invalid_item_type_or_empty_path', controller.store.settings.current_language)}")
            continue
        try:
            norm = os.path.normpath(fp)
            disp = os.path.basename(norm) or "-----"
        except Exception:
            errors.append(f"{fp}: {tr('msg.error_normalizing_path', controller.store.settings.current_language)}")
            continue
        if norm in seen:
            _reload_existing_path(controller, image_number, norm, lst)
            continue
        try:
            lst.append(ImageItem(image=None, path=norm, display_name=os.path.splitext(disp)[0], rating=0))
            seen.add(norm)
            new_idx.append(len(lst) - 1)
        except Exception:
            errors.append(f"{disp}: {tr('msg.error_processing_path', controller.store.settings.current_language)}")
    _finalize_loaded_paths(controller, image_number, new_idx, errors)


def duplicate_image_to_slot(controller, source_slot: int, target_slot: int) -> None:
    if source_slot not in (1, 2) or target_slot not in (1, 2):
        return
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    s_lst = document.image_list1 if source_slot == 1 else document.image_list2
    s_idx = document.current_index1 if source_slot == 1 else document.current_index2
    if not (0 <= s_idx < len(s_lst)):
        return
    s_item = s_lst[s_idx]
    path = s_item.path or ""
    if not path:
        return
    t_lst = document.image_list1 if target_slot == 1 else document.image_list2
    for idx, ex in enumerate(t_lst):
        if ex.path == path:
            d = getattr(controller.store, "get_dispatcher", lambda: None)()
            if d:
                try:
                    d.dispatch(SetCurrentIndexAction(slot=target_slot, index=idx), scope="document")
                except Exception:
                    pass
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
            # Reentrant: direct, no QTimer
            controller.set_current_image(target_slot)
            return
    # Share via PipelineCache if available — no duplicate decode
    pl = getattr(controller, "pipeline", None)
    cached = pl.peek(path) if pl else None
    if cached is not None and not bool(getattr(cached, "is_open", True)):
        cached = None
    t_lst.append(ImageItem(image=cached, path=path, display_name=s_item.display_name, rating=int(getattr(s_item, "rating", 0) or 0)))
    new_index = len(t_lst) - 1
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d:
        try:
            d.dispatch(SetCurrentIndexAction(slot=target_slot, index=new_index), scope="document")
        except Exception:
            pass
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_update("combobox")
        try:
            from ui.widgets.unified_list_picker import FlyoutMode

            controller.presenter.repopulate_flyouts()
            if controller.presenter.ui_manager.transient.unified_flyout.mode == FlyoutMode.DOUBLE:
                try:
                    controller.presenter.ui_manager.transient.unified_flyout.refreshGeometry(immediate=False)
                except Exception:
                    pass
        except Exception:
            pass
    controller.set_current_image(target_slot)


def _reload_existing_path(controller, image_number: int, normalized_path: str, target_list_ref):
    try:
        idx = next(i for i, it in enumerate(target_list_ref) if it.path == normalized_path)
        # Keep cached pixels if pipeline has it — avoid clearing
        pl = getattr(controller, "pipeline", None)
        cached = pl.peek(normalized_path) if pl else None
        target_list_ref[idx].image = cached
        d = getattr(controller.store, "get_dispatcher", lambda: None)()
        if d:
            try:
                d.dispatch(SetCurrentIndexAction(slot=image_number, index=idx), scope="document")
            except Exception:
                pass
        controller.set_current_image(image_number)
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")
    except (ValueError, IndexError):
        pass


def _finalize_loaded_paths(controller, image_number: int, newly_added_indices: list[int], load_errors: list[str]):
    if newly_added_indices:
        new_index = newly_added_indices[-1]
        d = getattr(controller.store, "get_dispatcher", lambda: None)()
        if d:
            try:
                d.dispatch(SetCurrentIndexAction(slot=image_number, index=new_index), scope="document")
            except Exception:
                pass
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_update("combobox")
        controller.set_current_image(image_number)
        if controller.presenter:
            try:
                controller.presenter.repopulate_flyouts()
                from ui.widgets.unified_list_picker import FlyoutMode
                if controller.presenter.ui_manager.transient.unified_flyout.mode == FlyoutMode.DOUBLE:
                    try:
                        controller.presenter.ui_manager.transient.unified_flyout.refreshGeometry(immediate=False)
                    except Exception:
                        pass
            except Exception:
                pass
    if load_errors:
        msg = tr("image_compare.msg.some_images_could_not_be_loaded", controller.store.settings.current_language) + ":\n\n - " + "\n - ".join(load_errors)
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(msg))
        else:
            controller.error_occurred.emit(msg)


def set_current_image(controller, image_number: int, force_refresh: bool = False, emit_signal: bool = True):
    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    cur = document.current_index1 if image_number == 1 else document.current_index2
    if not (0 <= cur < len(lst)):
        document_store_ops.clear_image_slot_data(controller.store, image_number)
        _invalidate_diff_cache(controller)
        controller._invalidate_image_canvas_render_state(clear_overlay_state=True)
        controller._schedule_image_canvas_update()
        if controller.presenter:
            controller.presenter.ui_batcher.schedule_batch_update(["combobox", "file_names", "resolution", "ratings"])
        if controller.store.viewport.session_data.render_cache.unification_in_progress:
            pending = controller.store.viewport.session_data.render_cache.pending_unification_paths
            if pending and (document.image1_path if image_number == 1 else document.image2_path) not in pending:
                d = getattr(controller.store, "get_dispatcher", lambda: None)()
                if d:
                    try:
                        with controller.store.batch_changes():
                            d.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                            d.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
                    except Exception:
                        pass
        controller.metrics_service.on_metrics_calculated(None)
        controller.store.emit_state_change("document")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        return
    item = lst[cur]
    pil_img, path = item.image, item.path
    if pil_img is None:
        # Check pipeline cache before clearing slot — share, don't wipe live store
        pl = getattr(controller, "pipeline", None)
        cached = pl.peek(path) if pl and path else None
        if cached is not None and bool(getattr(cached, "is_open", True)):
            pil_img = cached
            item.image = cached
        else:
            document_store_ops.clear_image_slot_data(controller.store, image_number)
    controller._update_image_slot(image_number, image=pil_img, path=path, is_full_res=bool(pil_img), emit=False)
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
    controller._schedule_image_canvas_update()
    if pil_img is None and path:
        # Single-flight via pipeline cache + controller._pending_image_loads guard removed —
        # pipeline handles dedup. Direct worker start, no QTimer.
        worker = GenericWorker(controller._load_image_async, path, image_number, cur, None)
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
        sd = getattr(controller.store.viewport, "session_data", None)
        rc = getattr(sd, "render_cache", None) if sd else None
        im = getattr(sd, "image_state", None) if sd else None
        if document is None or rc is None or im is None:
            _clear_unification_flags(controller)
            return
        if (path1, path2) != (document.image1_path, document.image2_path):
            _clear_unification_flags(controller)
            controller.store.invalidate_geometry_cache()
            controller.store.emit_state_change("viewport")
            return
        if not (u1 and u2):
            _clear_unification_flags(controller)
            controller.metrics_service.on_metrics_calculated(None)
            return
        # Cache unified pair in pipeline
        pl = getattr(controller, "pipeline", None)
        if pl is not None:
            try:
                method = _unify_resize_method(controller)
                pl.cache.put_unified(getattr(u1, "uid", id(u1)), getattr(u2, "uid", id(u2)), method, 0, 0, (u1, u2))
            except Exception:
                pass
        d = getattr(controller.store, "get_dispatcher", lambda: None)()
        if d is not None:
            try:
                with controller.store.batch_changes():
                    d.dispatch(SetImageSessionImageAction(slot=1, image=u1), scope="viewport")
                    d.dispatch(SetImageSessionImageAction(slot=2, image=u2), scope="viewport")
            except Exception:
                logger.error("Failed to dispatch unified images", exc_info=True)
        controller._start_pyramid_builds(u1, u2)
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
                controller.presenter.ui_batcher.schedule_batch_update(["resolution", "file_names"])
        except Exception:
            pass
    except Exception:
        _clear_unification_flags(controller)
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass


def resync_current_image_slots(controller) -> None:
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    for n in (1, 2):
        ensure_current_slot(controller, n, force_refresh=True)
