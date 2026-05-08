import logging
import time

from PyQt6.QtCore import QRect

from shared_toolkit.ui.managers.font_manager import FontManager
from shared_toolkit.workers import GenericWorker
from utils.resource_loader import get_magnifier_drawing_coords

logger = logging.getLogger("ImproveImgSLI")
_invalid_magnifier_bbox_log_count = 0

def render_magnifier_layer(presenter, sig):
    if not presenter._cached_base_pixmap:
        return False
    now = time.monotonic()
    if presenter._is_magnifier_worker_running:
        if sig == getattr(presenter, "_active_magnifier_signature", None):
            return True
        if sig == getattr(presenter, "_pending_magnifier_signature", None):
            return True
    presenter._magnifier_request_seq += 1
    request_seq = presenter._magnifier_request_seq
    if presenter._is_magnifier_worker_running:
        presenter._magnifier_update_pending = True
        presenter._pending_magnifier_signature = sig
        presenter._pending_magnifier_request_seq = request_seq
        presenter._pending_magnifier_requested_at = now
        return True

    presenter.view.sync_widget_overlay_coords()

    w, h = presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height
    try:
        magnifier_coords = get_magnifier_drawing_coords(
            store=presenter.store,
            drawing_width=w,
            drawing_height=h,
            container_width=w,
            container_height=h,
        )
        if not magnifier_coords or len(magnifier_coords) < 6:
            logger.warning("[RENDER] Invalid magnifier coordinates calculated: empty or too short")
            return False
        magnifier_bbox = magnifier_coords[5] if len(magnifier_coords) > 5 else None
        if magnifier_bbox is None or (hasattr(magnifier_bbox, "isValid") and not magnifier_bbox.isValid()):
            global _invalid_magnifier_bbox_log_count
            if _invalid_magnifier_bbox_log_count < 3:
                _invalid_magnifier_bbox_log_count += 1
                logger.warning("[RENDER] Invalid magnifier bbox in coordinates")
            return False
    except Exception as exc:
        logger.error("[RENDER] Geometry calculation failed: %s", exc, exc_info=True)
        return False

    image1 = presenter.store.viewport.session_data.render_cache.scaled_image1_for_display or presenter.store.viewport.session_data.image_state.image1
    image2 = presenter.store.viewport.session_data.render_cache.scaled_image2_for_display or presenter.store.viewport.session_data.image_state.image2
    if not image1 or not image2:
        logger.warning("[RENDER] Missing images for magnifier rendering")
        return False

    viewport = presenter.store.viewport
    interaction = getattr(viewport, "interaction_state", None)
    live_interaction = bool(
        interaction
        and (
            getattr(interaction, "is_interactive_mode", False)
            or getattr(interaction, "is_dragging_capture_point", False)
            or getattr(interaction, "is_dragging_split_in_magnifier", False)
            or getattr(interaction, "is_dragging_split_line", False)
            or bool(getattr(interaction, "pressed_keys", set()))
        )
    )
    render_params = viewport.get_render_params()
    render_params["is_interactive_mode"] = live_interaction
    render_params["optimize_magnifier_movement"] = getattr(
        viewport.view_state, "optimize_magnifier_movement", True
    )
    render_width, render_height = image1.size if image1 else (w, h)
    caches = {
        "magnifier": presenter.store.viewport.session_data.render_cache.magnifier_cache,
        "background": presenter.store.viewport.session_data.render_cache.caches,
    }

    presenter.current_rendering_task_id += 1
    task_id = presenter.current_rendering_task_id
    worker_payload = {
        "render_params": render_params,
        "image1": image1,
        "image2": image2,
        "orig1": presenter.store.document.full_res_image1,
        "orig2": presenter.store.document.full_res_image2,
        "coords": magnifier_coords,
        "width": render_width,
        "height": render_height,
        "font_path": FontManager.get_instance().get_font_path_for_image_text(presenter.store),
        "caches": caches,
        "task_id": task_id,
    }
    worker = GenericWorker(magnifier_worker_task, worker_payload)
    worker.signals.result.connect(presenter.magnifier.on_layer_ready)
    worker.signals.error.connect(presenter.magnifier.on_worker_error)

    presenter._is_magnifier_worker_running = True
    presenter._magnifier_update_pending = False
    presenter._pending_magnifier_signature = None
    presenter._pending_magnifier_request_seq = 0
    presenter._pending_magnifier_requested_at = 0.0
    presenter._active_magnifier_task_id = task_id
    presenter._active_magnifier_request_seq = request_seq
    presenter._active_magnifier_signature = sig
    presenter._active_magnifier_started_at = now
    priority = 0 if live_interaction else 2
    presenter.main_window_app.thread_pool.start(worker, priority=priority)
    return True

def start_magnifier_only_worker(
    presenter,
    render_params_dict,
    image1_scaled_for_display,
    image2_scaled_for_display,
    original_image1_pil,
    original_image2_pil,
    magnifier_coords,
    label_width,
    label_height,
):
    try:
        presenter.view.sync_widget_overlay_coords()
        presenter.current_rendering_task_id += 1

        from shared.image_processing.pipeline import create_render_context_from_params

        width, height = image1_scaled_for_display.size if image1_scaled_for_display else (0, 0)

        def magnifier_patch_task(render_params, ctx_dict, task_id):
            from shared.image_processing.pipeline import RenderingPipeline

            ctx = create_render_context_from_params(
                render_params_dict=render_params,
                width=width,
                height=height,
                magnifier_drawing_coords=magnifier_coords,
                image1_scaled=image1_scaled_for_display,
                image2_scaled=image2_scaled_for_display,
                original_image1=original_image1_pil,
                original_image2=original_image2_pil,
                session_caches=ctx_dict.get("session_caches", {}),
            )
            ctx.is_interactive_mode = bool(
                render_params.get("is_interactive_mode", False)
            )
            font_path = FontManager.get_instance().get_font_path_for_image_text(presenter.store)
            pipeline = RenderingPipeline(font_path)
            magnifier_patch, mag_pos = pipeline.render_magnifier_patch(ctx)
            return magnifier_patch, mag_pos, task_id, magnifier_coords

        session_caches = {
            "magnifier": presenter.store.viewport.session_data.render_cache.magnifier_cache,
            "background": presenter.store.viewport.session_data.render_cache.caches,
        }
        worker = GenericWorker(
            magnifier_patch_task,
            render_params_dict,
            {"session_caches": session_caches},
            presenter.current_rendering_task_id,
        )
        worker.signals.result.connect(presenter.magnifier.on_patch_ready)
        worker.signals.error.connect(presenter.results.on_generic_worker_error)
        presenter.main_window_app.thread_pool.start(worker, priority=0)
    except Exception as exc:
        logger.error("Failed to start magnifier-only worker: %s", exc, exc_info=True)

def render_capture_area_only_optimized(
    presenter,
    render_params_dict,
    image1_scaled_for_display,
    image2_scaled_for_display,
    original_image1_pil,
    original_image2_pil,
    magnifier_coords,
    label_width,
    label_height,
):
    try:
        presenter.current_rendering_task_id += 1

        from shared.image_processing.pipeline import create_render_context_from_params

        width, height = image1_scaled_for_display.size if image1_scaled_for_display else (0, 0)

        def capture_patch_task(render_params, ctx_dict, task_id):
            from shared.image_processing.pipeline import RenderingPipeline

            ctx = create_render_context_from_params(
                render_params_dict=render_params,
                width=width,
                height=height,
                magnifier_drawing_coords=magnifier_coords,
                image1_scaled=image1_scaled_for_display,
                image2_scaled=image2_scaled_for_display,
                original_image1=original_image1_pil,
                original_image2=original_image2_pil,
                session_caches=ctx_dict.get("session_caches", {}),
            )
            ctx.is_interactive_mode = bool(
                render_params.get("is_interactive_mode", False)
            )
            font_path = FontManager.get_instance().get_font_path_for_image_text(presenter.store)
            pipeline = RenderingPipeline(font_path)

            target_rect = presenter.store.viewport.geometry_state.image_display_rect_on_label
            img_rect = QRect(0, 0, width, height)
            padding_left = target_rect.x
            padding_top = target_rect.y
            capture_patch, patch_pos = pipeline.render_capture_area_patch(
                ctx, img_rect, padding_left, padding_top
            )
            return capture_patch, patch_pos, task_id

        session_caches = {
            "magnifier": presenter.store.viewport.session_data.render_cache.magnifier_cache,
            "background": presenter.store.viewport.session_data.render_cache.caches,
        }
        worker = GenericWorker(
            capture_patch_task,
            render_params_dict,
            {"session_caches": session_caches},
            presenter.current_rendering_task_id,
        )
        worker.signals.result.connect(presenter.magnifier.on_capture_patch_ready)
        presenter.main_window_app.thread_pool.start(worker, priority=0)
    except Exception as exc:
        logger.error("Failed to start capture-area-only worker: %s", exc, exc_info=True)

def magnifier_worker_task(payload):
    from shared.image_processing.pipeline import RenderingPipeline, create_render_context_from_params

    coords = payload["coords"]
    render_params = payload["render_params"]
    image1 = payload["image1"]
    image2 = payload["image2"]
    orig1 = payload["orig1"]
    orig2 = payload["orig2"]
    width = payload["width"]
    height = payload["height"]
    font_path = payload["font_path"]
    caches = payload["caches"]
    task_id = payload["task_id"]

    ctx = create_render_context_from_params(
        render_params_dict=render_params,
        width=width,
        height=height,
        magnifier_drawing_coords=coords,
        image1_scaled=image1,
        image2_scaled=image2,
        original_image1=orig1,
        original_image2=orig2,
        session_caches=caches,
    )
    ctx.is_interactive_mode = render_params.get("is_interactive_mode", False)
    pipeline = RenderingPipeline(font_path)
    magnifier_patch, patch_top_left = pipeline.render_magnifier_patch(ctx)
    return {"magnifier_patch": magnifier_patch, "magnifier_patch_top_left": patch_top_left}, task_id
