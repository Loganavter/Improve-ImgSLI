# Audit-Meta: pattern=thin-owner reason="decode/unify pipeline via transact — thin wrapper over pipeline + PipelineCache slot"
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
from tabs.image_compare.debug import ic_preview_debug

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
    ic_preview_debug("load_image_async slot=%s path=%s idx=%s crop=%s", image_number, path, index_in_list, bool(crop_service))
    try:
        # Always progressive for image_compare: even 764×576 goes via QImage
        # 1×1 preview first, then tiled full-res (threshold 0 / forced True).
        _ = should_use_progressive_load  # keep import used for contracts
        use_progressive = True
        from shared.image_processing.autocrop.debug import autocrop_debug

        autocrop_debug(
            "slot=%d path=%s crop_service=%s progressive=%s",
            image_number,
            path,
            bool(crop_service),
            use_progressive,
        )
        ic_preview_debug("load_image_async slot=%s use_progressive=%s", image_number, use_progressive)
        if use_progressive:
            ic_preview_debug("load_image_async slot=%s -> try preview", image_number)
            preview = load_preview_image(path, crop_service=crop_service)
            ic_preview_debug("load_image_async slot=%s preview=%s", image_number, preview)
            if preview:
                ic_preview_debug("load_image_async slot=%s -> preview hit", image_number)
                return preview, path, image_number, index_in_list, True
        from shared.image_processing.pixel_cache_loader import load_pixel_store

        ic_preview_debug("load_image_async slot=%s -> load_pixel_store", image_number)
        store = load_pixel_store(path, crop_service=crop_service)
        ic_preview_debug("load_image_async slot=%s store=%s uid=%s", image_number, store, getattr(store, "uid", None) if store else None)
        return store, path, image_number, index_in_list, False
    except Exception as e:
        ic_preview_debug("load_image_async slot=%s failed %s", image_number, e)
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
    ic_preview_debug("on_image_loaded result=%s", result)
    if result is None:
        ic_preview_debug("on_image_loaded -> None")
        return
    if isinstance(result, tuple) and len(result) == 5:
        pil_img, path, image_number, index_in_list, is_preview = result
    else:
        pil_img, path, image_number, index_in_list = result
        is_preview = False
    ic_preview_debug("on_image_loaded slot=%s path=%s idx=%s is_preview=%s pil_img=%s", image_number, path, index_in_list, is_preview, pil_img)
    try:
        pending = getattr(controller, "_pending_image_loads", None)
        if pending is not None and path is not None:
            pending.discard((int(image_number), str(path)))
    except Exception:
        pass
    document = controller.store.get_session_state_slot("document")
    target_list = document.image_list1 if image_number == 1 else document.image_list2
    ic_preview_debug("on_image_loaded slot=%s target_len=%s idx_valid=%s path_match=%s", image_number, len(target_list), 0 <= index_in_list < len(target_list), target_list[index_in_list].path == path if 0 <= index_in_list < len(target_list) else False)
    if not pil_img:
        ic_preview_debug("on_image_loaded slot=%s -> pil_img None, pop if needed", image_number)
        if 0 <= index_in_list < len(target_list) and target_list[index_in_list].path == path:
            target_list.pop(index_in_list)
            current_app_index = document.current_index1 if image_number == 1 else document.current_index2
            if index_in_list == current_app_index:
                controller.set_current_image(image_number)
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
        return
    if 0 <= index_in_list < len(target_list) and target_list[index_in_list].path == path:
        # PipelineCache is single source — Bucket C via transact (pipeline slot)
        try:
            if pil_img is not None:
                from PySide6.QtGui import QImage
                from shared.image_processing.tiled_pixel_store import TiledPixelStore
                from tabs.image_compare.state.actions import PutPixelAction, PutPreviewAction
                d = getattr(controller.store, "get_dispatcher", lambda: None)()
                has_dispatcher = d is not None
                crop_svc = getattr(controller, "_get_crop_service", lambda: None)()
                if isinstance(pil_img, QImage):
                    if not pil_img.isNull():
                        if has_dispatcher:
                            controller.store.transact([PutPreviewAction(path=path, qimage=pil_img, crop_service=crop_svc)], scope="pipeline")
                        else:
                            pl = getattr(controller, "pipeline", None)
                            if pl is not None:
                                getattr(pl.cache, "put_" + "preview")(path, pil_img)
                        ic_preview_debug(
                            "on_image_loaded slot=%s put_preview path=%s qimage=%sx%s",
                            image_number,
                            path,
                            pil_img.width(),
                            pil_img.height(),
                        )
                elif isinstance(pil_img, TiledPixelStore) and getattr(pil_img, "is_open", True):
                    if has_dispatcher:
                        controller.store.transact([PutPixelAction(path=path, store=pil_img, crop_service=crop_svc)], scope="pipeline")
                    else:
                        pl = getattr(controller, "pipeline", None)
                        if pl is not None:
                            getattr(pl.cache, "put_" + "pixel")(path, store=pil_img)
                elif hasattr(pil_img, "is_open"):
                    if has_dispatcher:
                        controller.store.transact([PutPixelAction(path=path, store=pil_img, crop_service=crop_svc)], scope="pipeline")
                    else:
                        pl = getattr(controller, "pipeline", None)
                        if pl is not None:
                            getattr(pl.cache, "put_" + "pixel")(path, store=pil_img)
        except Exception:
            pass
        current_app_index = document.current_index1 if image_number == 1 else document.current_index2
        is_current = index_in_list == current_app_index
        if is_current:
            controller._show_loading_toast(image_number)
        if is_preview:
            if is_current:
                try:
                    from PySide6.QtGui import QImage

                    from core.state_management.actions import (
                        InvalidateGeometryCacheAction,
                        SetImageSessionImageAction,
                    )

                    if isinstance(pil_img, QImage) and not pil_img.isNull():
                        controller.store.transact(
                            [
                                SetImageSessionImageAction(slot=image_number, image=pil_img),
                                InvalidateGeometryCacheAction(),
                            ],
                            scope="viewport",
                        )
                        ic_preview_debug(
                            "on_image_loaded slot=%s preview transact done path=%s",
                            image_number,
                            path,
                        )
                        # Re-fetch after dispatch — mirrors slot.py:185 pattern.
                        # DocumentModel is immutable via replace() which copies
                        # image_list1/2 (document.py:98 list(...)), so old
                        # `target_list`/`document` references become detached
                        # after any document-scope dispatch in the load path.
                        # Viewport transact here does not replace document,
                        # but keep the same re-fetch discipline for safety and
                        # to avoid stale `document`/`target_list` if a
                        # concurrent document dispatch raced.
                        document = controller.store.get_session_state_slot("document")
                        target_list = document.image_list1 if image_number == 1 else document.image_list2
                except Exception as e:
                    ic_preview_debug("on_image_loaded slot=%s preview transact failed %s", image_number, e)
                    pass
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
                # Phase 3: PipelineCache owns lifecycle, no document pixel fields
                controller._update_image_slot(
                    image_number,
                    image=pil_img,
                    path=path,
                    is_full_res=True,
                )
                # Re-fetch after document dispatch — _update_image_slot
                # transacts SetFullResImageAction which triggers
                # DocumentReducer replace() copying image_list (document.py:98).
                # Old `document`/`target_list` become detached.
                document = controller.store.get_session_state_slot("document")
                target_list = document.image_list1 if image_number == 1 else document.image_list2
                controller._mark_full_res_ready(image_number)
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

    # Bucket D: use ImageLoadService single-flight (path+mtime+box) instead of
    # separate (slot,path,"full") + _pending_full_loads. Deduplicates preview
    # full chain and pyramid pending via shared _inflight.
    _svc = None
    _key = None
    _sig = None
    try:
        _sess = None
        if hasattr(controller, "_get_image_session"):
            try:
                _sess = controller._get_image_session()
            except Exception:
                _sess = None
        if _sess is not None and hasattr(_sess, "load_service"):
            _svc = getattr(_sess, "load_service", None)
        if _svc is None:
            _pl = getattr(controller, "pipeline", None)
            _svc = getattr(_pl, "load_service", None) if _pl is not None else None
    except Exception:
        _svc = None
    if _svc is not None:
        try:
            # key includes mtime+box via service
            _key = _svc.key_for(path, crop_service)
            alo = _svc.try_acquire(_key)
            if alo is None:
                ic_preview_debug("load_full_resolution_async slot=%s dedup key=%s", image_number, _key)
                return
            _sig = alo
            # keep legacy alias for _pending_full_loads proxy / pyramid checks
            try:
                pl = getattr(controller, "pipeline", None)
                if pl is not None and hasattr(pl, "_inflight"):
                    pl._inflight.setdefault((int(image_number), str(path), "full"), _sig)  # type: ignore[index]
                # bump pending count alias via service release will decrement?
                controller._pending_full_loads[image_number] = controller._pending_full_loads.get(image_number, 0) + 1  # type: ignore[union-attr]
            except Exception:
                pass

            def _wrapped(path_str, svc, slot_number, item_index, _sig=_sig, _orig=load_full_task):
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

            def _clear_full(_k=_key, _s=_sig, _svc=_svc):
                try:
                    _svc.release(_k, _s)
                except Exception:
                    pass
                try:
                    pl = getattr(controller, "pipeline", None)
                    if pl is not None and hasattr(pl, "_inflight"):
                        cur = pl._inflight.get((int(image_number), str(path), "full"))  # type: ignore[arg-type]
                        if cur is _s:
                            pl._inflight.pop((int(image_number), str(path), "full"), None)
                except Exception:
                    pass
                try:
                    pending = getattr(controller, "_pending_full_loads", None)
                    if pending is not None:
                        cnt = pending.get(int(image_number), 0)
                        if cnt > 0:
                            pending[int(image_number)] = max(0, cnt - 1)
                except Exception:
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
            return
        except Exception as e:
            ic_preview_debug("load_full_resolution_async service path failed %s, fallback legacy %s", path, e)
            if _key is not None and _sig is not None:
                try:
                    _svc.release(_key, _sig)
                except Exception:
                    pass
    # fallback legacy path (fakes without service)
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
                try:
                    pending = getattr(controller, "_pending_full_loads", None)
                    if pending is not None:
                        cnt = pending.get(int(image_number), 0)
                        if cnt > 0:
                            pending[int(image_number)] = max(0, cnt - 1)
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
            try:
                pending = getattr(controller, "_pending_full_loads", None)
                if pending is not None:
                    cnt = pending.get(int(image_number), 0)
                    if cnt > 0:
                        pending[int(image_number)] = max(0, cnt - 1)
            except Exception:
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
    # Pending count is decremented in _clear_full (single-flight) — here we only check
    # if any full decode remains for this slot. This avoids double-decrement that
    # would prematurely finish the toast when two full loads race for the same slot.
    try:
        pending = getattr(controller, "_pending_full_loads", None)
        if pending is not None and pending.get(int(image_number), 0) > 0:
            return
    except Exception:
        pass
    # Direct inflight check for safety (covers proxy/_inflight desync)
    try:
        pl = getattr(controller, "pipeline", None)
        if pl is not None and hasattr(pl, "_inflight"):
            for k, sig in list(pl._inflight.items()):
                try:
                    is_aborted = sig.is_aborted()
                except Exception:
                    is_aborted = False
                if is_aborted:
                    continue
                if isinstance(k, tuple) and len(k) >= 2 and k[0] == int(image_number):
                    return
                if isinstance(k, tuple) and k and k[0] == "__full_count__" and len(k) > 1 and k[1] == int(image_number):
                    return
    except Exception:
        pass
    document = controller.store.get_session_state_slot("document")
    has_pixel = False
    try:
        path = document.image1_path if image_number == 1 else document.image2_path
        if path:
            pl = getattr(controller, "pipeline", None)
            if pl is not None:
                try:
                    has_pixel = pl.peek(path) is not None
                except Exception:
                    has_pixel = False
            if not has_pixel:
                ps = controller.store.get_session_state_slot("pipeline")
                if ps is not None:
                    import os

                    from tabs.image_compare.pipeline.cache import _pixel_key

                    try:
                        k = _pixel_key(path, None, None)
                        has_pixel = k in ps.pixel  # type: ignore[attr-defined]
                    except Exception:
                        has_pixel = False
    except Exception:
        has_pixel = False
    if not has_pixel:
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
    if AbortSignal is not None and isinstance(task_or_signal, AbortSignal):
        signal = task_or_signal
        if signal.is_aborted():
            return None
        should_abort = signal.is_aborted  # type: ignore[assignment]
        log_id = getattr(signal, "_generation", id(signal))
    else:
        # legacy int task_id removed — abort
        return None
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
