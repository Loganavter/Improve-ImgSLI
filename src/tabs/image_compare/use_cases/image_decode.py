"""Image decode flow — extracted from _session_controller.py (Phase 4).

Holds _load_image_async, _on_image_loaded, _load_full_resolution_async
and related helpers as plain functions taking controller. Thin-owner
pattern (CODE_PATTERNS.md:161).
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject
from sli_ui_toolkit.workers import GenericWorker
from sli_ui_toolkit.i18n import tr

from core.events import CoreErrorOccurredEvent
from core.state_management.actions import (
    SetPendingUnificationPathsAction,
    SetUnificationInProgressAction,
)

logger = logging.getLogger("ImproveImgSLI")


def _format_worker_error(err) -> str:
    if isinstance(err, tuple) and len(err) >= 2:
        return str(err[1])
    return str(err)


def load_image_async(controller, path, image_number, index_in_list, target_size=None):
    from shared.image_processing.progressive_loader import (
        load_preview_image,
        should_use_progressive_load,
    )

    crop_service = controller._get_crop_service()
    try:
        use_progressive = should_use_progressive_load(path)
        from shared.image_processing.autocrop.debug import autocrop_debug

        autocrop_debug(
            "slot=%d path=%s crop_service=%s progressive=%s",
            image_number,
            path,
            bool(crop_service),
            use_progressive,
        )
        if use_progressive:
            preview = load_preview_image(path, crop_service=crop_service)
            if preview:
                return preview, path, image_number, index_in_list, True
        from shared.image_processing.pixel_cache_loader import load_pixel_store

        store = load_pixel_store(path, crop_service=crop_service)
        return store, path, image_number, index_in_list, False
    except Exception as e:
        if controller.event_bus:
            controller.event_bus.emit(
                CoreErrorOccurredEvent(
                    f"{tr('msg.failed_to_load_image', controller.store.settings.current_language)}:\n{path}\n\n{e}"
                )
            )
        else:
            controller.error_occurred.emit(
                f"{tr('msg.failed_to_load_image', controller.store.settings.current_language)}:\n{path}\n\n{e}"
            )
        return None, path, image_number, index_in_list, False


def cancel_pending_unification(controller, new_path1: str = "", new_path2: str = "", force: bool = False) -> bool:
    try:
        cache = getattr(getattr(controller.store.viewport, "session_data", None), "render_cache", None)
        if cache is None or not getattr(cache, "unification_in_progress", False):
            return False
    except Exception:
        return False
    if force:
        try:
            dispatcher = controller.store.get_dispatcher()
            if dispatcher is not None:
                with controller.store.batch_changes():
                    dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                    dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
            else:
                cache.unification_in_progress = False  # type: ignore[attr-defined]
                cache.pending_unification_paths = None  # type: ignore[attr-defined]
            controller.store.invalidate_geometry_cache()
        except Exception:
            pass
        return True
    pending = getattr(cache, "pending_unification_paths", None)
    if pending and (pending[0] != new_path1 or pending[1] != new_path2):
        try:
            dispatcher = controller.store.get_dispatcher()
            if dispatcher is not None:
                with controller.store.batch_changes():
                    dispatcher.dispatch(SetUnificationInProgressAction(enabled=False), scope="viewport")
                    dispatcher.dispatch(SetPendingUnificationPathsAction(paths=None), scope="viewport")
            else:
                cache.unification_in_progress = False  # type: ignore[attr-defined]
                cache.pending_unification_paths = None  # type: ignore[attr-defined]
            controller.store.invalidate_geometry_cache()
        except Exception:
            pass
        return True
    return False


def on_image_loaded(controller, result):
    if result is None:
        return
    if isinstance(result, tuple) and len(result) == 5:
        pil_img, path, image_number, index_in_list, is_preview = result
    else:
        pil_img, path, image_number, index_in_list = result
        is_preview = False
    try:
        pending = getattr(controller, "_pending_image_loads", None)
        if pending is not None and path is not None:
            pending.discard((int(image_number), str(path)))
    except Exception:
        pass
    document = controller.store.get_session_state_slot("document")
    target_list = document.image_list1 if image_number == 1 else document.image_list2
    if not pil_img:
        if 0 <= index_in_list < len(target_list) and target_list[index_in_list].path == path:
            target_list.pop(index_in_list)
            current_app_index = document.current_index1 if image_number == 1 else document.current_index2
            if index_in_list == current_app_index:
                controller.set_current_image(image_number)
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
        return
    if 0 <= index_in_list < len(target_list) and target_list[index_in_list].path == path:
        item = target_list[index_in_list]
        # PipelineCache is single source — populate it so slot.py peek hits
        try:
            pl = getattr(controller, "pipeline", None)
            if pl is not None and pil_img is not None:
                from shared.image_processing.tiled_pixel_store import TiledPixelStore

                if isinstance(pil_img, TiledPixelStore) and getattr(pil_img, "is_open", True):
                    pl.cache.put_pixel(path, store=pil_img)
                elif hasattr(pil_img, "is_open"):
                    pl.cache.put_pixel(path, store=pil_img)
        except Exception:
            pass
        current_app_index = document.current_index1 if image_number == 1 else document.current_index2
        is_current = index_in_list == current_app_index
        if is_current:
            controller._show_loading_toast(image_number)
        if is_preview:
            if is_current:
                controller._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_preview=True,
                )
            load_full_resolution_async(controller, path, image_number, index_in_list)
        else:
            from shared.image_processing.tiled_pixel_store import (
                TiledPixelStore,
                close_pixel_store,
                maybe_wrap_pixel_store,
            )

            if not isinstance(pil_img, TiledPixelStore):
                pil_img = maybe_wrap_pixel_store(pil_img)
            if is_current:
                outgoing = getattr(document, f"full_res_image{image_number}", None)
                other = 2 if image_number == 1 else 1
                other_full = getattr(document, f"full_res_image{other}", None)
                if outgoing is not None and outgoing is not other_full:
                    close_pixel_store(outgoing)
                controller._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_full_res=True,
                )
                controller._mark_full_res_ready(image_number)
        try:
            item.image = pil_img
        except Exception:
            pass
        if is_current:
            if not is_preview:
                controller.set_current_image(image_number, force_refresh=True)
            else:
                controller._trigger_preview_unification(image_number)


def load_full_resolution_async(controller, path, image_number, index_in_list):
    from shared.image_processing.autocrop.debug import autocrop_debug

    crop_service = controller._get_crop_service()
    autocrop_debug(
        "full-res slot=%d path=%s crop_service=%s", image_number, path, bool(crop_service)
    )

    def load_full_task(path_str, svc, slot_number, item_index):
        from shared.image_processing.pixel_cache_loader import load_pixel_store

        store = load_pixel_store(path_str, crop_service=svc)
        return (
            store,
            path_str,
            slot_number,
            item_index,
        )

    _sig = None
    try:
        pl = getattr(controller, "pipeline", None)
        if pl is not None and hasattr(pl, "_inflight"):
            from tabs.image_compare.pipeline.abort import AbortSignal as _S

            _sig = _S()
            controller._pending_full_loads[image_number] = controller._pending_full_loads.get(image_number, 0) + 1  # type: ignore[union-attr]
            pl._inflight[(int(image_number), str(path), "full")] = _sig  # type: ignore[index]
            orig_task = load_full_task

            def _wrapped(path_str, svc, slot_number, item_index, _sig=_sig, _orig=orig_task):
                try:
                    if _sig is not None and _sig.is_aborted():
                        return (None, path_str, slot_number, item_index)
                except Exception:
                    pass
                res = _orig(path_str, svc, slot_number, item_index)
                try:
                    if _sig is not None and _sig.is_aborted():
                        return (None, path_str, slot_number, item_index)
                except Exception:
                    pass
                return res

            worker = GenericWorker(
                _wrapped,
                path,
                crop_service,
                image_number,
                index_in_list,
            )

            def _clear_full():
                try:
                    cur = pl._inflight.get((int(image_number), str(path), "full"))  # type: ignore[arg-type]
                    if cur is _sig:
                        pl._inflight.pop((int(image_number), str(path), "full"), None)
                except Exception:
                    pass

        else:
            raise AttributeError
    except Exception:
        worker = GenericWorker(
            load_full_task,
            path,
            crop_service,
            image_number,
            index_in_list,
        )
        try:
            controller._pending_full_loads[image_number] += 1  # type: ignore[index]
        except Exception:
            pass

        def _clear_full():  # type: ignore[no-redef]
            pass

    worker.signals.result.connect(controller._on_full_resolution_loaded_result)
    worker.signals.error.connect(
        lambda err: on_full_resolution_error(controller, path, err)
    )

    def _on_finished(num=image_number, _cf=_clear_full):
        try:
            _cf()
        except Exception:
            pass
        on_full_load_finished(controller, num)

    worker.signals.finished.connect(_on_finished)
    controller.thread_pool.start(worker)


def on_full_load_finished(controller, image_number: int) -> None:
    controller._pending_full_loads[image_number] = max(
        0, controller._pending_full_loads[image_number] - 1
    )
    if controller._pending_full_loads[image_number]:
        return
    document = controller.store.get_session_state_slot("document")
    if getattr(document, f"full_res_image{image_number}") is None:
        controller._trigger_preview_unification(image_number)


def on_full_resolution_loaded_result(controller, result) -> None:
    if not isinstance(result, tuple) or len(result) != 4:
        return
    full_img, path, image_number, index_in_list = result
    controller._on_full_image_loaded(
        full_img,
        path,
        int(image_number),
        int(index_in_list),
    )


def on_full_resolution_error(controller, path: str, err) -> None:
    logger.error(f"Failed to load full resolution: {err}", exc_info=True)
    message = (
        f"{tr('msg.failed_to_load_image', controller.store.settings.current_language)}:\n"
        f"{path}\n\n{_format_worker_error(err)}"
    )
    if controller.event_bus:
        controller.event_bus.emit(CoreErrorOccurredEvent(message))
    else:
        controller.error_occurred.emit(message)


def unify_images_worker_task(controller, img1, img2, path1, path2, task_or_signal, method_name):
    from shared.image_processing.pixel_ops.unify import unify_pair

    try:
        from tabs.image_compare.pipeline.abort import AbortSignal
    except Exception:
        AbortSignal = None  # type: ignore

    signal = None
    legacy_task_id = None
    if AbortSignal is not None and isinstance(task_or_signal, AbortSignal):
        signal = task_or_signal
        if signal.is_aborted():
            return None
        should_abort = signal.is_aborted  # type: ignore[assignment]
        log_id = getattr(signal, "_generation", id(signal))
    else:
        legacy_task_id = task_or_signal
        if legacy_task_id != controller._unification_task_id:
            return None
        should_abort = lambda: legacy_task_id != controller._unification_task_id  # type: ignore
        log_id = legacy_task_id
    try:
        import time

        t0 = time.perf_counter()
        logger.info(
            "[Unify] task %s started (%sx%s + %sx%s)",
            log_id,
            getattr(img1, "width", "?"),
            getattr(img1, "height", "?"),
            getattr(img2, "width", "?"),
            getattr(img2, "height", "?"),
        )
        u1, u2 = unify_pair(
            img1,
            img2,
            method_name,
            should_abort=should_abort,
        )
        if u1 is None and u2 is None:
            logger.info(
                "[Unify] task %s aborted/empty after %.2fs",
                log_id,
                time.perf_counter() - t0,
            )
            return None
        logger.info(
            "[Unify] task %s finished in %.2fs", log_id, time.perf_counter() - t0
        )
        return u1, u2, path1, path2, task_or_signal
    except Exception as e:
        logger.error(f"Failed to unify images: {e}", exc_info=True)
        return None
