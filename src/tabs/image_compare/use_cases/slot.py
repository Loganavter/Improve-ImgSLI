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

logger = logging.getLogger("ImproveImgSLI")


def ensure_current_slot(controller, image_number: int, force_refresh: bool = False) -> bool:
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return False
    lst = document.image_list1 if image_number == 1 else document.image_list2
    idx = document.current_index1 if image_number == 1 else document.current_index2
    path = document.image1_path if image_number == 1 else document.image2_path
    if not (0 <= idx < len(lst)):
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
    if not stale:
        return False
    try:
        controller.set_current_image(image_number, force_refresh=force_refresh)
    except Exception:
        pass
    return True


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
    # PipelineCache is single source — put instead of list item field
    pl = getattr(controller, "pipeline", None)
    if pl is not None:
        try:
            pl.cache.put_pixel(path, store=full_img)
        except Exception:
            pass
    cur = document.current_index1 if image_number == 1 else document.current_index2
    if index_in_list != cur:
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
    try:
        from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

        controller.store.transact(
            [SetImageSessionImageAction(slot=image_number, image=full_img), InvalidateGeometryCacheAction()],
            scope="viewport",
        )
    except Exception:
        try:
            controller._update_image_slot(image_number, image=full_img, path=path, is_full_res=True)
        except Exception:
            pass
    try:
        controller._mark_full_res_ready(image_number)
    except Exception:
        pass
    from tabs.image_compare.use_cases.unify import ensure_unification

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
            lst.append(ImageItem(path=norm, display_name=os.path.splitext(disp)[0], rating=0))
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
    cached = pl.peek(path) if pl is not None and path else None
    if cached is not None and not bool(getattr(cached, "is_open", True)):
        cached = None
    pil_img = cached
    if pil_img is None and path:
        document_store_ops.clear_image_slot_data(controller.store, image_number)
    # publish PipelineView via single Transaction (1 emit)
    if pil_img is not None:
        try:
            from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

            controller.store.transact(
                [SetImageSessionImageAction(slot=image_number, image=pil_img), InvalidateGeometryCacheAction()],
                scope="viewport",
            )
        except Exception:
            try:
                controller._update_image_slot(image_number, image=pil_img, path=path, is_full_res=True, emit=False)
            except Exception:
                pass
    else:
        # still publish clear via transaction if needed
        try:
            from core.state_management.actions import InvalidateGeometryCacheAction, SetImageSessionImageAction

            controller.store.transact(
                [SetImageSessionImageAction(slot=image_number, image=None), InvalidateGeometryCacheAction()],
                scope="viewport",
            )
        except Exception:
            pass
    controller.store.invalidate_render_cache()
    controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
    controller._schedule_image_canvas_update()
    if pil_img is None and path:
        pl = getattr(controller, "pipeline", None)
        key = (int(image_number), str(path))
        if pl is not None and hasattr(pl, "_inflight"):
            existing = pl._inflight.get(key)  # type: ignore[arg-type]
            if existing is not None:
                try:
                    if not existing.is_aborted():
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
            except Exception:
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
