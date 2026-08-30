"""Unification flow — demand-driven via PipelineCache memo.

Extracted from ``loading.py`` to keep that file <500. Re-exported via ``loading.py``.
"""

from __future__ import annotations

import logging

from sli_ui_toolkit.workers import GenericWorker

from core.state_management.actions import (
    SetCachedDiffImageAction,
    SetImageSessionImageAction,
    SetPendingUnificationPathsAction,
    SetUnificationInProgressAction,
)

from sli_ui_toolkit.i18n import tr

logger = logging.getLogger("ImproveImgSLI")


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
    pl = getattr(controller, "pipeline", None)
    if pl is not None:
        try:
            method = _unify_resize_method(controller)
            try:
                w1, h1 = int(getattr(s1, "width", 0) or 0), int(getattr(s1, "height", 0) or 0)
                w2, h2 = int(getattr(s2, "width", 0) or 0), int(getattr(s2, "height", 0) or 0)
                # fallback for QImage sources
                if w1 == 0 or h1 == 0:
                    from shared.image_processing.tiled_pixel_store import pixel_source_size

                    w1, h1 = pixel_source_size(s1)
                if w2 == 0 or h2 == 0:
                    from shared.image_processing.tiled_pixel_store import pixel_source_size

                    w2, h2 = pixel_source_size(s2)
                wh = (max(w1, w2), max(h1, h2))
            except Exception:
                wh = (0, 0)
            cached = pl.cache.get_unified(
                getattr(s1, "uid", id(s1)), getattr(s2, "uid", id(s2)), method, wh[0], wh[1]
            )
            _ = cached
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


def trigger_preview_unification(controller, image_number: int):
    if controller.presenter:
        controller.presenter.ui_batcher.schedule_batch_update(["file_names", "resolution"])
    # Single-slot pairing: unify never runs, so close the loading toast here
    # (otherwise it hangs forever — see test_single_slot_loading_toast_finishes).
    document = controller.store.get_session_state_slot("document")
    if document is not None:
        s1 = document.full_res_image1 or document.preview_image1
        s2 = document.full_res_image2 or document.preview_image2
        # If exactly one side has an image and the other slot is empty (no path),
        # finish the toast for the side that just loaded.
        # But don't finish while the slot's own full-res decode is still pending
        # (preview-only, _pending_full_loads >0) — that would close prematurily.
        try:
            from tabs.image_compare.use_cases.loading_toast import finish_toast_for_unpaired_slot
        except Exception:
            finish_toast_for_unpaired_slot = None  # type: ignore
        if finish_toast_for_unpaired_slot is not None:
            if (s1 and not s2) or (s2 and not s1):
                pending = getattr(controller, "_pending_full_loads", None)
                # If the triggering slot still has a full-res decode pending, wait.
                if pending is not None and pending.get(image_number, 0) > 0:
                    pass
                else:
                    try:
                        finish_toast_for_unpaired_slot(controller, document, image_number)
                    except Exception:
                        pass
    ensure_unification(controller)


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
        pl = getattr(controller, "pipeline", None)
        if pl is not None:
            try:
                method = _unify_resize_method(controller)
                try:
                    w1, h1 = int(getattr(u1, "width", 0) or 0), int(getattr(u1, "height", 0) or 0)
                    w2, h2 = int(getattr(u2, "width", 0) or 0), int(getattr(u2, "height", 0) or 0)
                    if w1 == 0 or h1 == 0:
                        from shared.image_processing.tiled_pixel_store import pixel_source_size

                        w1, h1 = pixel_source_size(u1)
                    if w2 == 0 or h2 == 0:
                        from shared.image_processing.tiled_pixel_store import pixel_source_size

                        w2, h2 = pixel_source_size(u2)
                    wh = (max(w1, w2), max(h1, h2))
                except Exception:
                    wh = (0, 0)
                pl.cache.put_unified(getattr(u1, "uid", id(u1)), getattr(u2, "uid", id(u2)), method, wh[0], wh[1], (u1, u2))
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
                from core.events import CoreUpdateRequestedEvent

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
