import logging

import PIL.Image
from sli_ui_toolkit.workers import GenericWorker

from shared.rendering.image_identity import image_uid

logger = logging.getLogger("ImproveImgSLI")


def _display_cache_key(img1, img2, limit):
    return (
        image_uid(img1),
        image_uid(img2),
        int(limit),
    )


def _set_display_cache(presenter, img1, img2, key):
    cache = presenter.store.viewport.session_data.render_cache
    cache.display_cache_image1 = img1
    cache.display_cache_image2 = img2
    cache.last_display_cache_params = key
    cache.scaled_image1_for_display = None
    cache.scaled_image2_for_display = None
    cache.cached_scaled_image_dims = None


def ensure_images_unified(presenter, source1, source2):
    runtime_cache = presenter.store.runtime_cache
    last_s1 = runtime_cache.last_source1_id
    last_s2 = runtime_cache.last_source2_id

    if (
        not presenter.store.viewport.session_data.image_state.image1
        or not presenter.store.viewport.session_data.image_state.image2
        or id(source1) != last_s1
        or id(source2) != last_s2
    ):
        document = presenter.store.get_session_state_slot("document")
        cache_key = (
            document.image1_path,
            document.image2_path,
        )
        cache = presenter.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.move_to_end(cache_key)
            u1, u2 = cache[cache_key]
            presenter.store.viewport.session_data.image_state.image1 = u1
            presenter.store.viewport.session_data.image_state.image2 = u2
            runtime_cache.last_source1_id = id(source1)
            runtime_cache.last_source2_id = id(source2)
            presenter.store.viewport.session_data.render_cache.scaled_image1_for_display = (
                None
            )
            presenter.store.viewport.session_data.render_cache.scaled_image2_for_display = (
                None
            )
            presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims = (
                None
            )
            return True
        return False
    return True


def ensure_images_scaled(presenter, w, h):
    if (
        presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
        and presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims
    ):
        cw, ch = (
            presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims
        )
        is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode
        tolerance = 0.15 if is_interactive else 0

        if abs(cw - w) <= max(1, w * tolerance) and abs(ch - h) <= max(
            1, h * tolerance
        ):
            return True

    if (
        presenter.store.viewport.session_data.image_state.image1
        and presenter.store.viewport.session_data.image_state.image2
    ):
        src1 = (
            presenter.store.viewport.session_data.render_cache.display_cache_image1
            or presenter.store.viewport.session_data.image_state.image1
        )
        src2 = (
            presenter.store.viewport.session_data.render_cache.display_cache_image2
            or presenter.store.viewport.session_data.image_state.image2
        )
        is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode
        if (
            is_interactive
            and presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
            and presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
        ):
            return True

        start_scaling_worker(presenter, src1, src2, w, h)
    return False


def start_scaling_worker(presenter, src1, src2, w, h):
    try:
        presenter.current_scaling_task_id += 1
        scaling_task_id = presenter.current_scaling_task_id

        def scale_task(img1, img2, width, height, tid):
            from shared.image_processing.lazy_pixel_source import to_real_pil_copy

            i1 = to_real_pil_copy(img1).resize(
                (width, height), PIL.Image.Resampling.BILINEAR
            )
            i2 = to_real_pil_copy(img2).resize(
                (width, height), PIL.Image.Resampling.BILINEAR
            )
            return i1, i2, width, height, tid

        worker = GenericWorker(scale_task, src1, src2, w, h, scaling_task_id)
        worker.signals.result.connect(presenter.background.on_display_scaling_ready)
        priority = (
            0 if presenter.store.viewport.interaction_state.is_interactive_mode else 1
        )
        presenter.main_window_app.thread_pool.start(worker, priority=priority)
    except Exception as exc:
        logger.error("Scaling start failed: %s", exc)


def on_display_scaling_ready(presenter, result):
    if not result:
        return
    img1_s, img2_s, w, h, task_id = result
    if int(task_id) != int(presenter.current_scaling_task_id):
        return

    presenter.store.viewport.session_data.render_cache.scaled_image1_for_display = (
        img1_s
    )
    presenter.store.viewport.session_data.render_cache.scaled_image2_for_display = (
        img2_s
    )
    presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims = (w, h)
    presenter.schedule_update()


def create_preview_cache_async(presenter, img1, img2):
    limit = int(presenter.store.viewport.render_config.display_resolution_limit)
    request_key = _display_cache_key(img1, img2, limit)
    cache = presenter.store.viewport.session_data.render_cache

    if (
        cache.display_cache_image1 is not None
        and cache.display_cache_image2 is not None
        and cache.last_display_cache_params == request_key
    ):
        return True

    w, h = img1.size
    if limit <= 0 or max(w, h) <= limit:
        presenter._display_cache_request_key = None
        _set_display_cache(presenter, img1, img2, request_key)
        return True

    if getattr(presenter, "_display_cache_request_key", None) == request_key:
        return False

    presenter._display_cache_request_key = request_key

    def cache_task(i1, i2, requested_limit, key):
        from shared.image_processing.lazy_pixel_source import to_real_pil_copy
        from shared.image_processing.resize import downscale_pair_to_limit

        i1, i2 = to_real_pil_copy(i1), to_real_pil_copy(i2)
        d1, d2 = downscale_pair_to_limit(i1, i2, requested_limit)
        return d1, d2, key

    worker = GenericWorker(
        cache_task,
        img1,
        img2,
        limit,
        request_key,
    )
    worker.signals.result.connect(presenter.background.on_preview_cache_ready)
    worker.signals.error.connect(
        lambda error, key=request_key: _on_preview_cache_failed(presenter, key, error)
    )
    presenter.main_window_app.thread_pool.start(worker, priority=1)
    return False


def on_preview_cache_ready(presenter, result):
    if not result or len(result) != 3:
        return

    c1, c2, request_key = result
    if getattr(presenter, "_display_cache_request_key", None) != request_key:
        return

    image_state = presenter.store.viewport.session_data.image_state
    current1 = image_state.image1
    current2 = image_state.image2
    if current1 is None or current2 is None:
        presenter._display_cache_request_key = None
        return

    current_key = _display_cache_key(
        current1,
        current2,
        presenter.store.viewport.render_config.display_resolution_limit,
    )
    if current_key != request_key:
        presenter._display_cache_request_key = None
        return

    presenter._display_cache_request_key = None
    _set_display_cache(presenter, c1, c2, request_key)
    presenter.schedule_update()


def _on_preview_cache_failed(presenter, request_key, error):
    if getattr(presenter, "_display_cache_request_key", None) == request_key:
        presenter._display_cache_request_key = None
    logger.error("Display cache creation failed: %s", error)
