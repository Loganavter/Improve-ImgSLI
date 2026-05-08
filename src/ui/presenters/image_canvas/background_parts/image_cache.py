import logging

import PIL.Image

from shared_toolkit.workers import GenericWorker

logger = logging.getLogger("ImproveImgSLI")

def ensure_images_unified(presenter, source1, source2):
    last_s1 = getattr(presenter.store.viewport, "_last_source1_id", 0)
    last_s2 = getattr(presenter.store.viewport, "_last_source2_id", 0)

    if (
        not presenter.store.viewport.session_data.image_state.image1
        or not presenter.store.viewport.session_data.image_state.image2
        or id(source1) != last_s1
        or id(source2) != last_s2
    ):
        cache_key = (
            presenter.store.document.image1_path,
            presenter.store.document.image2_path,
        )
        cache = presenter.store.viewport.session_data.render_cache.unified_image_cache
        if cache_key in cache:
            cache.move_to_end(cache_key)
            u1, u2 = cache[cache_key]
            presenter.store.viewport.session_data.image_state.image1 = u1
            presenter.store.viewport.session_data.image_state.image2 = u2
            setattr(presenter.store.viewport, "_last_source1_id", id(source1))
            setattr(presenter.store.viewport, "_last_source2_id", id(source2))
            presenter.store.viewport.session_data.render_cache.scaled_image1_for_display = None
            presenter.store.viewport.session_data.render_cache.scaled_image2_for_display = None
            presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims = None
            return True
        return False
    return True

def ensure_images_scaled(presenter, w, h):
    if (
        presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
        and presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims
    ):
        cw, ch = presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims
        is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode
        tolerance = 0.15 if is_interactive else 0

        if abs(cw - w) <= max(1, w * tolerance) and abs(ch - h) <= max(1, h * tolerance):
            return True

    if presenter.store.viewport.session_data.image_state.image1 and presenter.store.viewport.session_data.image_state.image2:
        src1 = presenter.store.viewport.session_data.render_cache.display_cache_image1 or presenter.store.viewport.session_data.image_state.image1
        src2 = presenter.store.viewport.session_data.render_cache.display_cache_image2 or presenter.store.viewport.session_data.image_state.image2
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
            i1 = img1.resize((width, height), PIL.Image.Resampling.BILINEAR)
            i2 = img2.resize((width, height), PIL.Image.Resampling.BILINEAR)
            return i1, i2, width, height, tid

        worker = GenericWorker(scale_task, src1.copy(), src2.copy(), w, h, scaling_task_id)
        worker.signals.result.connect(presenter.background.on_display_scaling_ready)
        priority = 0 if presenter.store.viewport.interaction_state.is_interactive_mode else 1
        presenter.main_window_app.thread_pool.start(worker, priority=priority)
    except Exception as exc:
        logger.error("Scaling start failed: %s", exc)

def on_display_scaling_ready(presenter, result):
    if not result:
        return
    img1_s, img2_s, w, h, task_id = result
    if int(task_id) != int(presenter.current_scaling_task_id):
        return

    presenter.store.viewport.session_data.render_cache.scaled_image1_for_display = img1_s
    presenter.store.viewport.session_data.render_cache.scaled_image2_for_display = img2_s
    presenter.store.viewport.session_data.render_cache.cached_scaled_image_dims = (w, h)
    presenter.schedule_update()

def create_preview_cache_async(presenter, img1, img2):
    def cache_task(i1, i2, limit):
        w, h = i1.size
        if limit > 0 and max(w, h) > limit:
            ratio = min(limit / w, limit / h)
            nw, nh = int(w * ratio), int(h * ratio)
            return i1.resize((nw, nh), PIL.Image.Resampling.LANCZOS), i2.resize(
                (nw, nh), PIL.Image.Resampling.LANCZOS
            )
        return i1, i2

    worker = GenericWorker(
        cache_task,
        img1.copy(),
        img2.copy(),
        presenter.store.viewport.render_config.display_resolution_limit,
    )
    worker.signals.result.connect(presenter.background.on_preview_cache_ready)
    presenter.main_window_app.thread_pool.start(worker, priority=1)

def on_preview_cache_ready(presenter, result):
    if result:
        c1, c2 = result
        presenter.store.viewport.session_data.render_cache.display_cache_image1 = c1
        presenter.store.viewport.session_data.render_cache.display_cache_image2 = c2
        presenter.schedule_update()
