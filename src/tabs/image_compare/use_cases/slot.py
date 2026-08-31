# Audit-Meta: pattern=thin-owner reason="SlotSource pipeline debug — load_images/set_current/handle_full with ic-preview tracing, stays thin wrapper"
"""Slot image operations — SlotSource + PipelineView via Transaction.

Phase 3 slim: DocumentModel is list+index+derived path only; pixels
live in PipelineCache (ImagePipeline) and viewport image_state.
Thin wrapper via use_cases/ per CODE_PATTERNS.md.
"""

from __future__ import annotations

import os
import logging

from sli_ui_toolkit.workers import GenericWorker

from core.state_management.actions import SetCurrentIndexAction
from tabs.image_compare.state.document import ImageItem
from sli_ui_toolkit.i18n import tr
from tabs.image_compare.debug import ic_preview_debug

logger = logging.getLogger("ImproveImgSLI")

# Throttle: ensure/set_current are re-entered 3× for same path at 60Hz via
# load path + transaction emit + fps timer. Dedup identical (slot, idx, path)
# probes so one load = one log line, not 3.
_last_ensure_slot_sig: dict[int, tuple] = {}
_last_set_current_sig: dict[tuple, bool] = {}
_last_handle_full_sig: dict[tuple, bool] = {}


def ensure_current_slot(controller, image_number: int, force_refresh: bool = False) -> bool:
    document = controller.store.get_session_state_slot("document")
    if document is None:
        ic_preview_debug("ensure_current_slot slot=%s -> no document", image_number)
        return False
    lst = document.image_list1 if image_number == 1 else document.image_list2
    idx = document.current_index1 if image_number == 1 else document.current_index2
    path = document.image1_path if image_number == 1 else document.image2_path
    _ens_sig = (int(image_number), int(idx) if isinstance(idx, int) else idx, str(path) if path else None, len(lst))
    _ens_should = _last_ensure_slot_sig.get(int(image_number)) != _ens_sig
    if _ens_should:
        _last_ensure_slot_sig[int(image_number)] = _ens_sig
        ic_preview_debug("ensure_current_slot slot=%s idx=%s path=%s lst_len=%s", image_number, idx, path, len(lst))
    if not (0 <= idx < len(lst)):
        if _ens_should:
            ic_preview_debug("ensure_current_slot slot=%s -> idx out of range", image_number)
        return False
    item = lst[idx]
    # staleness via pipeline cache (no document pixel fields)
    pl = getattr(controller, "pipeline", None)
    cached = pl.peek(path) if pl is not None and path else None
    is_open = bool(getattr(cached, "is_open", True)) if cached is not None else False
    stale = path != item.path or (cached is not None and not is_open)
    # also consider missing cache as stale if path exists but cache miss
    if path and cached is None:
        # if pipeline has no entry, treat as stale needing load
        stale = True
    if _ens_should:
        ic_preview_debug("ensure_current_slot slot=%s stale=%s cached=%s is_open=%s item.path=%s", image_number, stale, cached, is_open, item.path)
    if not stale:
        return False
    try:
        controller.set_current_image(image_number, force_refresh=force_refresh)
    except Exception:
        logger.exception("ensure_current_slot failed slot=%s", image_number)
        ic_preview_debug("ensure_current_slot slot=%s exception", image_number)
        pass
    return True


def handle_full_image_loaded(controller, full_img, path, image_number, index_in_list):
    ic_preview_debug("handle_full_image_loaded slot=%s path=%s idx=%s has_image=%s", image_number, path, index_in_list, bool(full_img))
    if not full_img:
        ic_preview_debug("handle_full_image_loaded slot=%s -> no image", image_number)
        return
    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    if not (0 <= index_in_list < len(lst)) or lst[index_in_list].path != path:
        ic_preview_debug("handle_full_image_loaded slot=%s -> lst mismatch len=%s path_mismatch=%s", image_number, len(lst), lst[index_in_list].path if 0 <= index_in_list < len(lst) else "oob")
        return
    from shared.image_processing.tiled_pixel_store import TiledPixelStore, close_pixel_store, maybe_wrap_pixel_store

    if not isinstance(full_img, TiledPixelStore):
        full_img = maybe_wrap_pixel_store(full_img)
    # PipelineCache is single source — put instead of list item field
    pl = getattr(controller, "pipeline", None)
    if pl is not None:
        try:
            pl.cache.put_pixel(path, store=full_img)
        except Exception:
            pass
    cur = document.current_index1 if image_number == 1 else document.current_index2
    ic_preview_debug("handle_full_image_loaded slot=%s cur=%s idx=%s path=%s", image_number, cur, index_in_list, path)
    if index_in_list != cur:
        ic_preview_debug("handle_full_image_loaded slot=%s -> not current, skip transact cur=%s idx=%s", image_number, cur, index_in_list)
        return
    # outgoing cleanup via pipeline cache (close old store if not shared)
    try:
        if pl is not None:
            # close previous store for this slot if different
            # we rely on PipelineCache eviction to close, but also close outgoing explicitly
            pass
    except Exception:
        pass
    # Single Transaction: PipelineView + geometry invalidate (1 dispatch, 1 emit)
    ic_preview_debug("handle_full_image_loaded slot=%s -> transact image uid=%s", image_number, getattr(full_img, "uid", id(full_img)))
    try:
        from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

        controller.store.transact(
            [SetImageSessionImageAction(slot=image_number, image=full_img), InvalidateGeometryCacheAction()],
            scope="viewport",
        )
        ic_preview_debug("handle_full_image_loaded slot=%s transact done", image_number)
    except Exception as e:
        ic_preview_debug("handle_full_image_loaded slot=%s transact failed %s", image_number, e)
        try:
            controller._update_image_slot(image_number, image=full_img, path=path, is_full_res=True)
        except Exception:
            pass
    try:
        controller._mark_full_res_ready(image_number)
    except Exception:
        pass
    from tabs.image_compare.use_cases.unify import ensure_unification

    ic_preview_debug("handle_full_image_loaded slot=%s -> ensure_unification", image_number)
    ensure_unification(controller)
    try:
        from tabs.image_compare.use_cases.loading import QTimer  # type: ignore

        if QTimer is not None:
            def _finish_if_unpaired():
                try:
                    from tabs.image_compare.use_cases.loading_toast import finish_toast_for_unpaired_slot

                    finish_toast_for_unpaired_slot(controller, document, image_number)
                except Exception:
                    pass

            QTimer.singleShot(0, _finish_if_unpaired)
        else:
            from tabs.image_compare.use_cases.loading_toast import finish_toast_for_unpaired_slot

            finish_toast_for_unpaired_slot(controller, document, image_number)
    except Exception:
        pass


def load_images_from_paths(controller, file_paths: list[str], image_number: int):
    ic_preview_debug("load_images_from_paths slot=%s files=%s", image_number, file_paths)
    from tabs.image_compare.services import document_store_ops
    from core.state_management.actions import (
        SetCachedDiffImageAction,
        SetImageSessionImageAction,
        SetPendingUnificationPathsAction,
        SetUnificationInProgressAction,
    )

    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    is_new = len(lst) == 0
    ic_preview_debug("load_images_from_paths slot=%s is_new=%s len=%s other_len=%s", image_number, is_new, len(lst), len(document.image_list2 if image_number==1 else document.image_list1))
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
            # stale check via derived path (no doc pixel fields)
            has_path = bool(document.image1_path) if image_number == 1 else bool(document.image2_path)
            if has_path:
                document_store_ops.clear_image_slot_data(controller.store, image_number)

    # Re-fetch after is_new dispatches: DocumentModel is immutable via replace()
    # which copies image_list1/2 (see debug test 2026-08-31), so old `lst` reference
    # is detached from store's current document. Without re-fetch, `lst.append`
    # mutates detached list and store's list stays empty → ensure_current_slot sees 0.
    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    ic_preview_debug("load_images_from_paths slot=%s after is_new re-fetch len=%s id(lst)=%s", image_number, len(lst), id(lst))

    errors, new_idx = [], []
    seen = {e.path for e in lst if e.path}
    ic_preview_debug("load_images_from_paths slot=%s seen=%s", image_number, seen)
    for fp in file_paths:
        if not isinstance(fp, str) or not fp:
            ic_preview_debug("load_images_from_paths slot=%s skip invalid %s", image_number, fp)
            errors.append(f"{fp}: {tr('msg.invalid_item_type_or_empty_path', controller.store.settings.current_language)}")
            continue
        try:
            norm = os.path.normpath(fp)
            disp = os.path.basename(norm) or "-----"
        except Exception as e:
            ic_preview_debug("load_images_from_paths slot=%s norm failed %s %s", image_number, fp, e)
            errors.append(f"{fp}: {tr('msg.error_normalizing_path', controller.store.settings.current_language)}")
            continue
        if norm in seen:
            ic_preview_debug("load_images_from_paths slot=%s reload existing %s", image_number, norm)
            _reload_existing_path(controller, image_number, norm, lst)
            continue
        try:
            ic_preview_debug("load_images_from_paths slot=%s append %s disp=%s", image_number, norm, disp)
            lst.append(ImageItem(path=norm, display_name=os.path.splitext(disp)[0], rating=0))
            seen.add(norm)
            new_idx.append(len(lst) - 1)
        except Exception as e:
            ic_preview_debug("load_images_from_paths slot=%s append failed %s %s", image_number, disp, e)
            errors.append(f"{disp}: {tr('msg.error_processing_path', controller.store.settings.current_language)}")
    ic_preview_debug("load_images_from_paths slot=%s new_idx=%s errors=%s lst_len_after=%s", image_number, new_idx, errors, len(lst))
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
            else:
                try:
                    setattr(document, f"current_index{target_slot}", idx)
                except Exception:
                    pass
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
            try:
                controller.set_current_image(target_slot)
            except Exception:
                pass
            return
    pl = getattr(controller, "pipeline", None)
    cached = pl.peek(path) if pl else None
    if cached is not None and not bool(getattr(cached, "is_open", True)):
        cached = None
    # SlotSource only — no image on item, cache holds pixels
    t_lst.append(ImageItem(path=path, display_name=s_item.display_name, rating=int(getattr(s_item, "rating", 0) or 0)))
    # ensure cache has entry if we had one (put for sharing)
    if pl is not None and cached is not None:
        try:
            pl.cache.put_pixel(path, store=cached)
        except Exception:
            pass
    new_index = len(t_lst) - 1
    d = getattr(controller.store, "get_dispatcher", lambda: None)()
    if d:
        try:
            d.dispatch(SetCurrentIndexAction(slot=target_slot, index=new_index), scope="document")
        except Exception:
            pass
    else:
        try:
            setattr(document, f"current_index{target_slot}", new_index)
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
    try:
        controller.set_current_image(target_slot)
    except Exception:
        pass


def _reload_existing_path(controller, image_number: int, normalized_path: str, target_list_ref):
    try:
        idx = next(i for i, it in enumerate(target_list_ref) if it.path == normalized_path)
        pl = getattr(controller, "pipeline", None)
        cached = pl.peek(normalized_path) if pl else None
        # no list item pixel write — cache already holds it
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
        from core.events import CoreErrorOccurredEvent

        msg = tr("image_compare.msg.some_images_could_not_be_loaded", controller.store.settings.current_language) + ":\n\n - " + "\n - ".join(load_errors)
        if controller.event_bus:
            controller.event_bus.emit(CoreErrorOccurredEvent(msg))
        else:
            controller.error_occurred.emit(msg)


def set_current_image(controller, image_number: int, force_refresh: bool = False, emit_signal: bool = True):
    from tabs.image_compare.services import document_store_ops
    from core.state_management.actions import SetCachedDiffImageAction, SetUnificationInProgressAction, SetPendingUnificationPathsAction
    from core.events import CoreUpdateRequestedEvent

    document = controller.store.get_session_state_slot("document")
    lst = document.image_list1 if image_number == 1 else document.image_list2
    cur = document.current_index1 if image_number == 1 else document.current_index2
    _cur_path = lst[cur].path if 0 <= cur < len(lst) else None
    _set_sig = (int(image_number), int(cur) if isinstance(cur, int) else cur, str(_cur_path) if _cur_path else None, bool(force_refresh))
    _last_sig = _last_set_current_sig.get(int(image_number))  # type: ignore[has-type]
    _should_log_set = _set_sig != _last_sig or bool(force_refresh)
    if _should_log_set:
        _last_set_current_sig[int(image_number)] = _set_sig  # type: ignore[has-type]
        ic_preview_debug("set_current_image slot=%s force=%s emit=%s", image_number, force_refresh, emit_signal)
        ic_preview_debug("set_current_image slot=%s cur=%s len=%s path=%s", image_number, cur, len(lst), _cur_path)
    if not (0 <= cur < len(lst)):
        document_store_ops.clear_image_slot_data(controller.store, image_number)
        from tabs.image_compare.use_cases.unify import _invalidate_diff_cache

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
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass
        controller.store.emit_state_change("document")
        if controller.event_bus:
            controller.event_bus.emit(CoreUpdateRequestedEvent())
        else:
            controller.update_requested.emit()
        return
    item = lst[cur]
    path = item.path
    # pipeline is single source — peek to see if cached
    pl = getattr(controller, "pipeline", None)
    if _should_log_set:
        ic_preview_debug("set_current_image slot=%s path=%s pipeline=%s", image_number, path, bool(pl))
    cached = pl.peek(path) if pl is not None and path else None
    if _should_log_set:
        ic_preview_debug("set_current_image slot=%s cached=%s is_open=%s", image_number, cached, getattr(cached, "is_open", None) if cached else None)
    if cached is not None and not bool(getattr(cached, "is_open", True)):
        if _should_log_set:
            ic_preview_debug("set_current_image slot=%s cached closed -> None", image_number)
        cached = None
    pil_img = cached
    if _should_log_set:
        ic_preview_debug("set_current_image slot=%s pil_img=%s path=%s", image_number, pil_img, path)
    if pil_img is None and path:
        if _should_log_set:
            ic_preview_debug("set_current_image slot=%s -> clear slot data (cache miss)", image_number)
        document_store_ops.clear_image_slot_data(controller.store, image_number)
    # publish PipelineView via single Transaction (1 emit)
    if pil_img is not None:
        if _should_log_set:
            ic_preview_debug("set_current_image slot=%s -> transact image uid=%s", image_number, getattr(pil_img, "uid", id(pil_img)))
        try:
            from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

            controller.store.transact(
                [SetImageSessionImageAction(slot=image_number, image=pil_img), InvalidateGeometryCacheAction()],
                scope="viewport",
            )
            if _should_log_set:
                ic_preview_debug("set_current_image slot=%s transact done", image_number)
        except Exception as e:
            if _should_log_set:
                ic_preview_debug("set_current_image slot=%s transact failed %s", image_number, e)
            try:
                controller._update_image_slot(image_number, image=pil_img, path=path, is_full_res=True, emit=False)
            except Exception:
                pass
    else:
        # still publish clear via transaction if needed
        if _should_log_set:
            ic_preview_debug("set_current_image slot=%s -> transact clear image_state", image_number)
        try:
            from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

            controller.store.transact(
                [SetImageSessionImageAction(slot=image_number, image=None), InvalidateGeometryCacheAction()],
                scope="viewport",
            )
            if _should_log_set:
                ic_preview_debug("set_current_image slot=%s clear transact done", image_number)
        except Exception as e:
            if _should_log_set:
                ic_preview_debug("set_current_image slot=%s clear transact failed %s", image_number, e)
            pass
    if _should_log_set:
        ic_preview_debug("set_current_image slot=%s -> invalidate_render + schedule_update", image_number)
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
    controller._schedule_image_canvas_update()
    if pil_img is None and path:
        if _should_log_set:
            ic_preview_debug("set_current_image slot=%s -> cache miss, will start worker path=%s cur=%s", image_number, path, cur)
        # Bucket D: single-flight via ImageLoadService (path+mtime+box → AbortSignal)
        # should_use_progressive inside service, one transact per result, dedup 3×
        _svc = None
        try:
            # prefer session load_service (shares _inflight dict with pipeline)
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
            if _svc is None:
                _svc = getattr(controller, "load_service", None)
        except Exception:
            _svc = None
        if _svc is not None:
            try:
                # service handles dedup via path+mtime+box and progressive inside
                sig = _svc.ensure_async(path, int(image_number), int(cur), controller)
                # dedup case — existing signal returned, or new signal started
                # ensure legacy alias (slot,path) for compat with _pending_image_loads proxies
                try:
                    pl = getattr(controller, "pipeline", None)
                    if pl is not None and hasattr(pl, "_inflight") and sig is not None:
                        legacy_key = (int(image_number), str(path))
                        pl._inflight.setdefault(legacy_key, sig)  # type: ignore[index]
                except Exception:
                    pass
                if sig is not None:
                    # started or deduped — single-flight owns result → one transact
                    if _should_log_set:
                        ic_preview_debug("set_current_image slot=%s -> ImageLoadService sig=%s", image_number, sig)
                    if emit_signal:
                        controller.store.emit_state_change("document")
                    return
                else:
                    # cache-hit path already transacted inside service
                    if emit_signal:
                        controller.store.emit_state_change("document")
                    # trigger unification via service? on cache-hit service already handled
                    try:
                        controller._trigger_preview_unification(image_number)
                    except Exception:
                        pass
                    return
            except Exception as e:
                ic_preview_debug("set_current_image slot=%s ImageLoadService failed %s, fallback legacy", image_number, e)
                _svc = None
        # fallback legacy single-flight (kept for fakes without service)
        pl = getattr(controller, "pipeline", None)
        key = (int(image_number), str(path))
        if pl is not None and hasattr(pl, "_inflight"):
            existing = pl._inflight.get(key)  # type: ignore[arg-type]
            if _should_log_set:
                ic_preview_debug("set_current_image slot=%s inflight existing=%s", image_number, existing)
            if existing is not None:
                try:
                    if not existing.is_aborted():
                        # dedup is important — always log even when throttled
                        ic_preview_debug("set_current_image slot=%s -> inflight exists, dedup return", image_number)
                        if emit_signal:
                            controller.store.emit_state_change("document")
                        return
                except Exception:
                    if emit_signal:
                        controller.store.emit_state_change("document")
                    return
            try:
                from tabs.image_compare.pipeline.abort import AbortSignal as _AbortSignal

                _sig = _AbortSignal()
                pl._inflight[key] = _sig
                if _should_log_set:
                    ic_preview_debug("set_current_image slot=%s -> new inflight %s", image_number, _sig)
            except Exception as e:
                if _should_log_set:
                    ic_preview_debug("set_current_image slot=%s inflight create failed %s", image_number, e)
                _sig = None

            def _clear():
                try:
                    cur_sig = pl._inflight.get(key)  # type: ignore[arg-type]
                    if _sig is None or cur_sig is _sig:
                        pl._inflight.pop(key, None)
                except Exception:
                    pass

            _orig_load = controller._load_image_async

            def _load_with_signal(p, num, idx, _t=None):
                try:
                    if _sig is not None and _sig.is_aborted():
                        return None, p, num, idx, False
                except Exception:
                    pass
                res = _orig_load(p, num, idx, _t)
                try:
                    if _sig is not None and _sig.is_aborted():
                        return None, p, num, idx, False
                except Exception:
                    pass
                return res

            worker = GenericWorker(_load_with_signal, path, image_number, cur, None)
        else:
            pending = getattr(controller, "_pending_image_loads", None)
            if pending is not None:
                if key in pending:
                    if emit_signal:
                        controller.store.emit_state_change("document")
                    return
                try:
                    pending.add(key)
                except Exception:
                    pass

                def _clear():
                    try:
                        pending.discard(key)
                    except Exception:
                        pass
            else:

                def _clear():  # type: ignore[no-redef]
                    pass

            worker = GenericWorker(controller._load_image_async, path, image_number, cur, None)
        worker.signals.result.connect(controller._on_image_loaded_from_worker)
        try:
            worker.signals.finished.connect(_clear)
        except Exception:
            pass
        worker.signals.result.connect(lambda *_a, _c=_clear: _c())
        controller.thread_pool.start(worker)
    else:
        try:
            controller._trigger_preview_unification(image_number)
        except Exception:
            pass
    if emit_signal:
        controller.store.emit_state_change("document")
