import logging

from sli_ui_toolkit.workers import GenericWorker

from core.state_management.actions import SetCachedDiffImageAction

from shared.image_processing.store_lease import StoreLease
from shared.rendering.image_identity import image_uid

logger = logging.getLogger("ImproveImgSLI")


def _as_crop_box(box):
    """Normalize a CropBox / plain ``(left, top, right, bottom)`` tuple.

    The magnifier resolves warmed boxes as plain tuples (``box_remap``);
    the analysis chain (``crop_source_to_box``) consumes ``CropBox``
    attribute access — a plain tuple would silently no-op there. ``None``
    (or degenerate) → ``None`` so callers keep today's full-frame math.
    """
    if box is None:
        return None
    try:
        left, top, right, bottom = (
            int(box[0]),
            int(box[1]),
            int(box[2]),
            int(box[3]),
        )
    except Exception:
        return None
    if right <= left or bottom <= top:
        return None
    try:
        from shared.image_processing.autocrop.model import CropBox

        return CropBox(left, top, right, bottom)
    except Exception:
        return None


def _box_key_tuple(box):
    """Hashable box identity for the request key (w3c ``box_key`` pattern)."""
    normalized = _as_crop_box(box)
    return normalized.to_tuple() if normalized is not None else None


def build_cached_diff_image_task(
    source1,
    source2,
    diff_mode,
    lease1,
    lease2,
    progress_callback=None,
    *,
    box1=None,
    box2=None,
):
    from tabs.image_compare.services.analysis.background_layers import (
        build_cached_diff_image,
    )

    return build_cached_diff_image(
        source1,
        source2,
        diff_mode,
        "RGB",
        optimize_ssim=False,
        progress_callback=progress_callback,
        lease1=lease1,
        lease2=lease2,
        box1=_as_crop_box(box1),
        box2=_as_crop_box(box2),
    )


def request_cached_diff_image_async(
    presenter, source1, source2, diff_mode, box1=None, box2=None
):
    from tabs.image_compare.presenters.image_canvas.background_parts.diff_toasts import (
        complete_diff_toast,
        dismiss_active_diff_toast,
        show_or_reuse_diff_toast,
        update_diff_toast_progress,
    )

    if diff_mode != "ssim":
        return
    if source1 is None or source2 is None:
        return

    # W3d: diff over the crop windows. Both boxes None → legacy 5-tuple key,
    # bit-identical to today (existing served/pending keys still match);
    # either box present → box tuples ride the key so a box change
    # recomputes instead of hitting a stale-box entry.
    box_key = (_box_key_tuple(box1), _box_key_tuple(box2))
    request_key = (
        diff_mode,
        # image_uid, not id(): id() is a memory address CPython can reuse
        # once the old source is garbage collected -- exactly what tends to
        # happen right after a swap discards it -- so a request for the new
        # pair could collide with a stale cached request_key from before
        # the swap and get skipped as "already pending/served" (see the
        # sibling fix in rhi_renderer/__init__.py's source_ids).
        image_uid(source1),
        image_uid(source2),
        getattr(source1, "size", None),
        getattr(source2, "size", None),
    )
    if box_key != (None, None):
        request_key = (*request_key, box_key)
    render_cache = presenter.store.viewport.session_data.render_cache
    # Already have a diff for this exact source pair -- render_flow.py calls
    # this unconditionally every frame diff_mode=="ssim" (not just when
    # cached_diff_image is None, so the stale previous-pair diff stays
    # visible across a swap instead of vanishing); this is what stops that
    # from recomputing SSIM every single frame once it's already served.
    if getattr(render_cache, "cached_diff_source_key", None) == request_key:
        return
    pending_key = getattr(presenter, "_pending_cached_diff_request_key", None)
    if pending_key == request_key:
        return

    presenter._pending_cached_diff_request_key = request_key
    show_or_reuse_diff_toast(presenter, diff_mode, request_key)

    def _on_result(diff_image):
        presenter._pending_cached_diff_request_key = None
        if diff_image is None:
            dismiss_active_diff_toast(presenter)
            return
        # Both fields are updated together so a future request_key
        # comparison never sees a served key without its matching image.
        dispatcher = getattr(presenter.store, "get_dispatcher", None)
        dispatcher = dispatcher() if callable(dispatcher) else None
        if dispatcher is not None:
            try:
                dispatcher.dispatch(SetCachedDiffImageAction(image=diff_image), scope="viewport")
            except Exception:
                logger.error("Failed to dispatch SetCachedDiffImageAction", exc_info=True)
                try:
                    setattr(presenter.store.viewport.session_data.render_cache, "cached_diff_image", diff_image)
                except Exception:
                    pass
        else:
            try:
                setattr(presenter.store.viewport.session_data.render_cache, "cached_diff_image", diff_image)
            except Exception:
                pass
        try:
            setattr(presenter.store.viewport.session_data.render_cache, "cached_diff_source_key", request_key)
        except Exception:
            pass
        complete_diff_toast(presenter, request_key)
        presenter._last_mag_signature = None
        presenter._last_bg_signature = None
        presenter._last_img_sig = None
        presenter.schedule_update()

    def _on_error(error_tuple):
        presenter._pending_cached_diff_request_key = None
        exctype, value, _traceback_str = error_tuple
        logger.error(
            "Failed to build cached diff image asynchronously: %s: %s",
            getattr(exctype, "__name__", exctype),
            value,
        )
        dismiss_active_diff_toast(presenter)

    worker = GenericWorker(
        build_cached_diff_image_task,
        source1,
        source2,
        diff_mode,
        StoreLease.capture(source1),
        StoreLease.capture(source2),
        box1=_as_crop_box(box1),
        box2=_as_crop_box(box2),
    )
    worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    worker.signals.partial_result.connect(
        lambda progress_payload: update_diff_toast_progress(
            presenter,
            request_key,
            progress_payload,
        )
    )
    presenter.main_window_app.thread_pool.start(worker, priority=1)


def ensure_cached_diff_image(
    presenter,
    source1,
    source2,
    *,
    local_source1=None,
    local_source2=None,
    box1=None,
    box2=None,
):
    vp = presenter.store.viewport
    diff_mode = getattr(vp.view_state, "diff_mode", "off")
    cached = getattr(vp.session_data.render_cache, "cached_diff_image", None)
    if cached is not None or diff_mode != "ssim":
        return cached

    cached = getattr(presenter, "_cached_diff_image", None)
    if cached is not None:
        return cached
    s1 = local_source1 if local_source1 is not None else source1
    s2 = local_source2 if local_source2 is not None else source2
    if s1 is not None and s2 is not None:
        try:
            is_open1 = getattr(s1, "is_open", True)
            is_open2 = getattr(s2, "is_open", True)
            if callable(is_open1):
                is_open1 = is_open1()
            if callable(is_open2):
                is_open2 = is_open2()
            if not is_open1 or not is_open2:
                return None
        except Exception:
            pass
        try:
            rc = getattr(vp.session_data, "render_cache", None)
            if rc is not None and bool(getattr(rc, "unification_in_progress", False)):
                return None
        except Exception:
            pass
        try:
            request_cached_diff_image_async(
                presenter, s1, s2, diff_mode, box1=box1, box2=box2
            )
        except Exception:
            pass
    return None
