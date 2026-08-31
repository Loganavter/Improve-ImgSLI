"""Unification flow — demand-driven via PipelineCache memo."""

from __future__ import annotations

import logging

from sli_ui_toolkit.workers import GenericWorker

from core.state_management.actions import (
    SetCachedDiffImageAction,
    SetImageSessionImageAction,
    SetPendingUnificationPathsAction,
    SetUnificationInProgressAction,
)

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


def _peek_both(pl, path: str | None):
    """Tier-aware peek: _pixel (TiledPixelStore) or _preview (QImage 1024)."""
    if not path or pl is None:
        return None
    try:
        hit = pl.peek(path)
        if hit is not None:
            return hit
    except Exception:
        pass
    try:
        return pl.peek_preview(path)
    except Exception:
        return None


def _slot_sources(controller, document):
    """PipelineCache is single source; fallback to viewport image_state."""
    pl = getattr(controller, "pipeline", None)
    vp_state = getattr(controller.store.viewport.session_data, "image_state", None)
    s1 = s2 = None
    if document is not None:
        if pl is not None:
            try:
                p1 = document.image1_path
                p2 = document.image2_path
                if p1:
                    s1 = _peek_both(pl, p1)
                if p2:
                    s2 = _peek_both(pl, p2)
            except Exception:
                pass
        if s1 is None and vp_state is not None:
            s1 = getattr(vp_state, "image1", None)
        if s2 is None and vp_state is not None:
            s2 = getattr(vp_state, "image2", None)
    return s1, s2


def ensure_unification(controller, delay_ms: int = 0) -> None:
    """Demand-driven unify via PipelineCache (memo by uid). No QTimer dedup."""
    document = controller.store.get_session_state_slot("document")
    if document is None:
        return
    s1, s2 = _slot_sources(controller, document)
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
                if w1 == 0 or h1 == 0:
                    from shared.image_processing.tiled_pixel_store import pixel_source_size

                    w1, h1 = pixel_source_size(s1)
                if w2 == 0 or h2 == 0:
                    from shared.image_processing.tiled_pixel_store import pixel_source_size

                    w2, h2 = pixel_source_size(s2)
                wh = (max(w1, w2), max(h1, h2))
            except Exception:
                wh = (0, 0)
            from shared.rendering.image_identity import image_uid

            cached = pl.cache.get_unified(
                image_uid(s1), image_uid(s2), method, wh[0], wh[1]
            )
            if cached is not None:
                try:
                    u1, u2 = cached
                    if u1 is not None and u2 is not None:
                        # publish cached unified pair without spawning worker
                        d_hit = getattr(controller.store, "get_dispatcher", lambda: None)()
                        if d_hit is not None:
                            try:
                                with controller.store.batch_changes():
                                    d_hit.dispatch(SetImageSessionImageAction(slot=1, image=u1), scope="viewport")
                                    d_hit.dispatch(SetImageSessionImageAction(slot=2, image=u2), scope="viewport")
                            except Exception:
                                logger.error("Failed to dispatch cached unified images", exc_info=True)
                        try:
                            controller._start_pyramid_builds(u1, u2)
                        except Exception:
                            pass
                        try:
                            controller.store.invalidate_render_cache()
                        except Exception:
                            pass
                        try:
                            controller._invalidate_image_canvas_render_state(clear_overlay_state=False)
                        except Exception:
                            pass
                        try:
                            controller._schedule_image_canvas_update()
                        except Exception:
                            pass
                        try:
                            _clear_unification_flags(controller)
                        except Exception:
                            pass
                        try:
                            controller._trigger_metrics_calculation_if_needed()
                        except Exception:
                            pass
                        logger.info("get_unified hit method=%s wh=%s", method, wh)
                        return
                except Exception:
                    pass
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
            try:
                controller._unification_task_id += 1  # type: ignore[attr-defined]
                signal = controller._unification_task_id  # type: ignore[attr-defined]
            except Exception:
                signal = 0
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

        def _clear_unify_inflight(*_a, **_kw):
            if pl is not None and unify_key is not None:
                try:
                    cur = pl._inflight.get(unify_key)  # type: ignore[arg-type]
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
    document = controller.store.get_session_state_slot("document")
    if document is not None:
        s1, s2 = _slot_sources(controller, document)
        try:
            from tabs.image_compare.use_cases.loading_toast import finish_toast_for_unpaired_slot
        except Exception:
            finish_toast_for_unpaired_slot = None  # type: ignore
        if finish_toast_for_unpaired_slot is not None:
            if (s1 and not s2) or (s2 and not s1):
                has_pending = False
                pl = getattr(controller, "pipeline", None)
                if pl is not None and hasattr(pl, "_inflight"):
                    try:
                        for k, sig in list(pl._inflight.items()):
                            try:
                                if sig.is_aborted():
                                    continue
                            except Exception:
                                pass
                            # consistent with PendingFullLoadsProxy: any (slot, ...) with len>=2
                            if isinstance(k, tuple) and len(k) >= 2 and k[0] == int(image_number):
                                has_pending = True
                                break
                            if isinstance(k, tuple) and k and k[0] == "__full_count__" and len(k) > 1 and k[1] == int(image_number):
                                has_pending = True
                                break
                    except Exception:
                        has_pending = False
                    # proxy is alias to _inflight synthetic, but check for consistency
                    try:
                        pending = getattr(controller, "_pending_full_loads", None)
                        if not has_pending and pending is not None and pending.get(int(image_number), 0) > 0:  # type: ignore[union-attr]
                            has_pending = True
                    except Exception:
                        pass
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
        try:
            controller.metrics_service.on_metrics_calculated(None)
        except Exception:
            pass
        return
    try:
        if isinstance(result, tuple) and len(result) == 5:
            u1, u2, path1, path2, task_or_signal = result
        else:
            _clear_unification_flags(controller)
            try:
                controller.metrics_service.on_metrics_calculated(None)
            except Exception:
                pass
            return
        try:
            from tabs.image_compare.pipeline.abort import AbortSignal as _AbortSignal

            if isinstance(task_or_signal, _AbortSignal):
                if task_or_signal.is_aborted():
                    return
            else:
                if task_or_signal != controller._unification_task_id:
                    return
        except Exception:
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
                from shared.rendering.image_identity import image_uid

                # memo key is source uid, not result uid (fix never-hit)
                s1_src = s2_src = None
                try:
                    if hasattr(pl, "peek"):
                        try:
                            s1_src = pl.peek(path1)
                        except Exception:
                            pass
                        if s1_src is None:
                            try:
                                s1_src = pl.peek_preview(path1)
                            except Exception:
                                pass
                        try:
                            s2_src = pl.peek(path2)
                        except Exception:
                            pass
                        if s2_src is None:
                            try:
                                s2_src = pl.peek_preview(path2)
                            except Exception:
                                pass
                except Exception:
                    pass
                if s1_src is not None and s2_src is not None:
                    s1_uid = image_uid(s1_src)
                    s2_uid = image_uid(s2_src)
                else:
                    s1_uid = image_uid(s1_src) if s1_src is not None else image_uid(u1)
                    s2_uid = image_uid(s2_src) if s2_src is not None else image_uid(u2)
                pl.cache.put_unified(s1_uid, s2_uid, method, wh[0], wh[1], (u1, u2))
                # Union letterbox hold: keep prev union letterbox for 300-400ms after put_unified
                try:
                    import time as _t

                    try:
                        from shared.rendering.tile_constants import UNION_LETTERBOX_HOLD_MS as _HOLD
                    except Exception:
                        _HOLD = 350.0
                    until = _t.monotonic() + _HOLD / 1000.0
                    # Try canvas widget runtime_state first
                    for _obj in (
                        getattr(getattr(controller, "presenter", None), "widget", None),
                        getattr(controller, "widget", None),
                    ):
                        if _obj is not None and hasattr(_obj, "runtime_state"):
                            try:
                                _obj.runtime_state._union_letterbox_hold_until = until
                            except Exception:
                                pass
                        # also check image_label canvas inside widget
                        try:
                            from tabs.image_compare.canvas.helpers import get_canvas_widget

                            _canvas = get_canvas_widget(_obj) if _obj is not None else None
                            if _canvas is not None and hasattr(_canvas, "runtime_state"):
                                try:
                                    _canvas.runtime_state._union_letterbox_hold_until = until
                                except Exception:
                                    pass
                        except Exception:
                            pass
                except Exception:
                    pass
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
        try:
            controller._trigger_metrics_calculation_if_needed()
        except Exception:
            pass
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
