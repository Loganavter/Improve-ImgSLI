import logging

from shared_toolkit.workers import GenericWorker
from ui.widgets.gl_canvas.helpers import get_gl_like_canvas

from .diff_toasts import (
    complete_diff_toast,
    dismiss_active_diff_toast,
    update_diff_toast_progress,
)

logger = logging.getLogger("ImproveImgSLI")

def build_gl_background_layers_task(
    image1,
    image2,
    diff_mode,
    channel_mode,
    optimize_ssim=False,
    progress_callback=None,
):
    from plugins.analysis.processing import prepare_gl_background_layers_for_mode

    return prepare_gl_background_layers_for_mode(
        image1,
        image2,
        diff_mode,
        channel_mode,
        optimize_ssim=optimize_ssim,
        progress_callback=progress_callback,
    )

def sync_gl_diff_texture(presenter, diff_mode):
    image_label = get_gl_like_canvas(getattr(presenter, "ui", None))
    if image_label is None:
        return

    if diff_mode not in {"highlight", "grayscale", "ssim", "edges"} and getattr(
        presenter, "_active_diff_toast_id", None
    ) is not None:
        dismiss_active_diff_toast(presenter)

    cached_diff_image = getattr(
        presenter.store.viewport.session_data.render_cache, "cached_diff_image", None
    )
    if cached_diff_image is None:
        cached_diff_image = getattr(presenter, "_cached_gl_diff_image", None)

    current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
    current_uploaded_id = None if current_uploaded_diff is None else id(current_uploaded_diff)
    target_diff_id = None if cached_diff_image is None else id(cached_diff_image)

    if diff_mode != "off" and cached_diff_image is not None:
        if current_uploaded_id != target_diff_id:
            image_label.upload_diff_source_pil_image(cached_diff_image)
    elif diff_mode == "off":
        if current_uploaded_diff is not None:
            image_label.upload_diff_source_pil_image(None)
        dismiss_active_diff_toast(presenter)

def request_gl_background_layers_async(
    presenter,
    image1,
    image2,
    diff_mode,
    channel_mode,
    cache_key,
    optimize_ssim=False,
):
    if getattr(presenter, "_pending_gl_background_layers_key", None) == cache_key:
        return

    presenter._pending_gl_background_layers_key = cache_key
    presenter._pending_gl_background_layers_started_at = None

    worker = GenericWorker(
        build_gl_background_layers_task,
        image1.copy(),
        image2.copy(),
        diff_mode,
        channel_mode,
        optimize_ssim,
    )
    worker.kwargs["progress_callback"] = worker.signals.partial_result.emit

    def _on_result(result):
        if getattr(presenter, "_pending_gl_background_layers_key", None) != cache_key:
            return
        presenter._pending_gl_background_layers_key = None
        presenter._pending_gl_background_layers_started_at = None
        if result is None:
            dismiss_active_diff_toast(presenter)
            return
        presenter._cached_gl_background_layers_key = cache_key
        presenter._cached_gl_background_layers = result
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and result[0] is not None
            and result[0] is result[1]
            and diff_mode != "off"
        ):
            presenter._cached_gl_diff_image_key = cache_key
            presenter._cached_gl_diff_image = result[0]
        else:
            presenter._cached_gl_diff_image_key = None
            presenter._cached_gl_diff_image = None
        if diff_mode in {"ssim", "edges"}:
            complete_diff_toast(presenter, cache_key)
        presenter._gl_last_img_sig = None
        presenter._last_bg_signature = None
        presenter.schedule_update()

    def _on_error(error_tuple):
        if getattr(presenter, "_pending_gl_background_layers_key", None) != cache_key:
            return
        presenter._pending_gl_background_layers_key = None
        presenter._pending_gl_background_layers_started_at = None
        exctype, value, _traceback_str = error_tuple
        logger.error(
            "Failed to precompute GL background layers: %s: %s",
            getattr(exctype, "__name__", exctype),
            value,
        )
        dismiss_active_diff_toast(presenter)

    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    worker.signals.partial_result.connect(
        lambda progress_payload: update_diff_toast_progress(
            presenter,
            cache_key,
            progress_payload,
        )
    )
    presenter.main_window_app.thread_pool.start(worker, priority=1)
