import logging

from sli_ui_toolkit.workers import GenericWorker

from shared.image_processing.store_lease import StoreLease

logger = logging.getLogger("ImproveImgSLI")


def build_cached_diff_image_task(
    source1,
    source2,
    diff_mode,
    lease1,
    lease2,
    progress_callback=None,
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
    )


def request_cached_diff_image_async(presenter, source1, source2, diff_mode):
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

    request_key = (
        diff_mode,
        id(source1),
        id(source2) if source2 is not None else 0,
        getattr(source1, "size", None),
        getattr(source2, "size", None),
    )
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
        presenter.store.viewport.session_data.render_cache.cached_diff_image = (
            diff_image
        )
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
):
    vp = presenter.store.viewport
    diff_mode = getattr(vp.view_state, "diff_mode", "off")
    cached = getattr(vp.session_data.render_cache, "cached_diff_image", None)
    if cached is not None or diff_mode != "ssim":
        return cached

    cached = getattr(presenter, "_cached_diff_image", None)
    if cached is not None:
        return cached
    return None
