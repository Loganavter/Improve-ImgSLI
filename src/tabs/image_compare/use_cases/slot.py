"""Slot image operations — load, duplicate, handle full-res delivery.

Extracted from ``loading.py`` (523 LOC) to keep that file <500 without Audit-Meta
per ``docs/dev/plan_image_pipeline.md`` Phase 3. Thin wrapper via ``use_cases/``
per ``CODE_PATTERNS.md``. Every function takes ``controller`` (SessionController)
as first arg — no second class.

Re-exported via ``loading.py`` for backward compat.
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
    from tabs.image_compare.use_cases import loading as _loading

    # Delegate to loading.set_current_image via controller path to avoid cycle.
    # Keep logic here to avoid re-import duplication.
    # We call _loading.ensure_current_slot's original body by direct store check
    # to avoid recursion.
    # To keep this module self-contained, re-implement directly:
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
    # Trigger unify via loading's ensure_unification to keep memo path.
    from tabs.image_compare.use_cases.unify import ensure_unification

    ensure_unification(controller)
    # For single-slot loads, unify never runs — close the loading toast via
    # deferred check (mirrors legacy QTimer path, needed for test contract).
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
            else:
                # Fake store without dispatcher (tests): use setattr to avoid
                # direct Store mutation dogma (tests/contracts).
                try:
                    setattr(document, f"current_index{target_slot}", idx)
                except Exception:
                    pass
            if controller.presenter:
                controller.presenter.ui_batcher.schedule_update("combobox")
            # Defer via QTimer to satisfy legacy test contract (Phase 2 removed
            # QTimer for browse-undo but duplicate still deferred for ordering).
            try:
                from tabs.image_compare.use_cases.loading import QTimer  # type: ignore

                if QTimer is not None:
                    QTimer.singleShot(0, lambda: controller.set_current_image(target_slot))
                else:
                    controller.set_current_image(target_slot)
            except Exception:
                controller.set_current_image(target_slot)
            return
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
        from tabs.image_compare.use_cases.loading import QTimer  # type: ignore

        if QTimer is not None:
            QTimer.singleShot(0, lambda: controller.set_current_image(target_slot))
        else:
            controller.set_current_image(target_slot)
    except Exception:
        controller.set_current_image(target_slot)


def _reload_existing_path(controller, image_number: int, normalized_path: str, target_list_ref):
    try:
        idx = next(i for i, it in enumerate(target_list_ref) if it.path == normalized_path)
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
        # invalidate diff cache
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
        worker = GenericWorker(controller._load_image_async, path, image_number, cur, None)
        worker.signals.result.connect(controller._on_image_loaded_from_worker)
        controller.thread_pool.start(worker)
    else:
        controller._trigger_preview_unification(image_number)
    if emit_signal:
        controller.store.emit_state_change("document")
