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
        # Phase 2A: AbortSignal single-flight (replaces _unification_task_id)
        signal = None
        try:
            sess = None
            if hasattr(controller, "_get_image_session"):
                try:
                    sess = controller._get_image_session()
                except Exception:
                    sess = None
            if sess is not None and hasattr(sess, "new_abort"):
                signal = sess.new_abort()
            else:
                raise AttributeError
        except Exception:
            # fallback for fakes without session
            try:
                controller._unification_task_id += 1  # type: ignore[attr-defined]
                signal = controller._unification_task_id  # type: ignore[attr-defined]
            except Exception:
                signal = 0
        # single-flight dedup via pipeline._inflight if available
        method = _unify_resize_method(controller)
        pl = getattr(controller, "pipeline", None)
        unify_key = None
        if pl is not None and hasattr(pl, "_inflight"):
            try:
                unify_key = (document.image1_path, document.image2_path, method)
                existing = pl._inflight.get(unify_key)  # type: ignore[arg-type]
                if existing is not None:
                    try:
                        if not existing.is_aborted():
                            return
                    except Exception:
                        return
                # reserve; store AbortSignal if signal is int fallback, wrap
                if signal is not None and hasattr(signal, "is_aborted"):
                    pl._inflight[unify_key] = signal  # type: ignore[index]
                else:
                    try:
                        from tabs.image_compare.pipeline.abort import AbortSignal as _S

                        _wrap = _S()
                        pl._inflight[unify_key] = _wrap  # type: ignore[index]
                    except Exception:
                        pass
            except Exception:
                unify_key = None
        worker = GenericWorker(
            controller._unify_images_worker_task,
            s1, s2, document.image1_path, document.image2_path, signal if signal is not None else 0, method,
        )

        # clear single-flight on finish
        def _clear_unify_inflight(*_a, **_kw):
            if pl is not None and unify_key is not None:
                try:
                    cur = pl._inflight.get(unify_key)  # type: ignore[arg-type]
                    # only clear if still our signal
                    if signal is None or cur is signal or (hasattr(cur, "is_aborted") and hasattr(signal, "is_aborted")):
                        pl._inflight.pop(unify_key, None)
                except Exception:
                    pass

        worker.signals.result.connect(controller._on_unified_images_ready)
        try:
            worker.signals.finished.connect(_clear_unify_inflight)
        except Exception:
            pass
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
        # But don't finish while the slot's own full-res decode is still in flight
        # via pipeline._inflight — that would close prematurely.
        try:
            from tabs.image_compare.use_cases.loading_toast import finish_toast_for_unpaired_slot
        except Exception:
            finish_toast_for_unpaired_slot = None  # type: ignore
        if finish_toast_for_unpaired_slot is not None:
            if (s1 and not s2) or (s2 and not s1):
                # Check pipeline single-flight first, then legacy pending alias
                has_pending = False
                pl = getattr(controller, "pipeline", None)
                if pl is not None and hasattr(pl, "_inflight"):
                    try:
                        for k, sig in pl._inflight.items():
                            if isinstance(k, tuple) and len(k) == 2 and k[0] == int(image_number):
                                if not sig.is_aborted():
                                    has_pending = True
                                    break
                            if isinstance(k, tuple) and k and k[0] == "__full_count__" and len(k) > 1 and k[1] == int(image_number):
                                if not sig.is_aborted():
                                    has_pending = True
                                    break
                    except Exception:
                        has_pending = False
                    if has_pending:
                        pass
                    else:
                        # fallback to legacy pending_full_loads alias
                        pending = getattr(controller, "_pending_full_loads", None)
                        if pending is not None and pending.get(image_number, 0) > 0:  # type: ignore[union-attr]
                            has_pending = True
                        if not has_pending:
                            try:
                                finish_toast_for_unpaired_slot(controller, document, image_number)
                            except Exception:
                                pass
                else:
                    pending = getattr(controller, "_pending_full_loads", None)
                    if pending is not None and pending.get(image_number, 0) > 0:  # type: ignore[union-attr]
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
            u1, u2, path1, path2, task_or_signal = result
        else:
            _clear_unification_flags(controller)
            controller.metrics_service.on_metrics_calculated(None)
            return
        # Phase 2A: AbortSignal takes precedence over legacy task_id
        try:
            from tabs.image_compare.pipeline.abort import AbortSignal as _AbortSignal

            if isinstance(task_or_signal, _AbortSignal):
                if task_or_signal.is_aborted():
                    return
                # also check if current session has newer signal (aborted old)
                # is_aborted already covers global new_abort, but if pipeline
                # cleared _inflight we still reject stale via abort flag
            else:
                if task_or_signal != controller._unification_task_id:
                    return
        except Exception:
            # fallback legacy
            try:
                if task_or_signal != controller._unification_task_id:  # type: ignore[attr-defined]
                    return
            except Exception:
                pass
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
