import logging
import PIL.Image
from PyQt6.QtGui import QPixmap

from domain.types import Rect
from resources.translations import tr
from shared_toolkit.ui.managers.font_manager import FontManager
from shared_toolkit.workers import GenericWorker
from utils.resource_loader import get_scaled_pixmap_dimensions
from workers.image_rendering_worker import ImageRenderingWorker

logger = logging.getLogger("ImproveImgSLI")

def _build_gl_background_layers_task(
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

def _dismiss_active_diff_toast(presenter):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is not None and toast_id is not None:
        try:
            toast_manager.close_toast(toast_id)
        except Exception:
            logger.exception("Failed to close SSIM toast")
    presenter._active_diff_toast_id = None
    presenter._active_diff_toast_key = None

def _get_diff_toast_message(presenter, diff_mode: str) -> str:
    current_language = getattr(presenter.store.settings, "current_language", "en")
    if diff_mode == "highlight":
        message = tr("msg.highlight_diff_in_progress", current_language)
        if message == "msg.highlight_diff_in_progress":
            return "Highlight diff..."
        return message
    if diff_mode == "grayscale":
        message = tr("msg.grayscale_diff_in_progress", current_language)
        if message == "msg.grayscale_diff_in_progress":
            return "Grayscale diff..."
        return message
    if diff_mode == "edges":
        message = tr("msg.edge_comparison_in_progress", current_language)
        if message == "msg.edge_comparison_in_progress":
            return "Edge comparison..."
        return message

    message = tr("msg.ssim_calculation_in_progress", current_language)
    if message == "msg.ssim_calculation_in_progress":
        return "SSIM calculation..."
    return message

def _format_diff_toast_message(presenter, diff_mode: str, progress_payload=None) -> str:
    return _get_diff_toast_message(presenter, diff_mode)

def _show_or_reuse_diff_toast(presenter, diff_mode, request_key):
    if diff_mode not in {"highlight", "grayscale", "ssim", "edges"}:
        return

    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    if toast_manager is None:
        return

    if getattr(presenter, "_active_diff_toast_key", None) == request_key:
        return

    existing_toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if existing_toast_id is not None:
        try:
            toast_manager.close_toast(existing_toast_id)
        except Exception:
            logger.exception("Failed to replace SSIM toast")

    try:
        toast_id = toast_manager.show_toast(
            _format_diff_toast_message(presenter, diff_mode),
            duration=0,
            progress=0,
        )
        presenter._active_diff_toast_id = toast_id
        presenter._active_diff_toast_key = request_key
    except Exception:
        logger.exception("Failed to show SSIM toast")

def _update_diff_toast_progress(presenter, request_key, progress_payload):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is None or toast_id is None:
        return
    if getattr(presenter, "_active_diff_toast_key", None) != request_key:
        return

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    progress_value = progress_payload
    if isinstance(progress_payload, dict):
        progress_value = progress_payload.get("progress", 0)

    try:
        toast_manager.update_toast(
            toast_id,
            _format_diff_toast_message(
                presenter,
                diff_mode,
                progress_payload=progress_payload,
            ),
            success=False,
            duration=0,
            progress=progress_value,
        )
    except Exception:
        logger.exception("Failed to update diff toast progress")

def _complete_diff_toast(presenter, request_key):
    toast_manager = getattr(presenter.main_window_app, "toast_manager", None)
    toast_id = getattr(presenter, "_active_diff_toast_id", None)
    if toast_manager is None or toast_id is None:
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None
        return
    if getattr(presenter, "_active_diff_toast_key", None) != request_key:
        return

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    current_language = getattr(presenter.store.settings, "current_language", "en")
    if diff_mode == "highlight":
        done_message = tr("msg.highlight_diff_done", current_language)
        if done_message == "msg.highlight_diff_done":
            done_message = "Highlight diff done"
    elif diff_mode == "grayscale":
        done_message = tr("msg.grayscale_diff_done", current_language)
        if done_message == "msg.grayscale_diff_done":
            done_message = "Grayscale diff done"
    elif diff_mode == "edges":
        done_message = tr("msg.edge_comparison_done", current_language)
        if done_message == "msg.edge_comparison_done":
            done_message = "Edge comparison done"
    else:
        done_message = tr("msg.ssim_calculation_done", current_language)
        if done_message == "msg.ssim_calculation_done":
            done_message = "SSIM done"

    try:
        toast_manager.update_toast(
            toast_id,
            done_message,
            success=True,
            duration=2000,
            progress=100,
        )
    except Exception:
        logger.exception("Failed to complete diff toast")
    finally:
        presenter._active_diff_toast_id = None
        presenter._active_diff_toast_key = None

def _sync_gl_diff_texture(presenter, diff_mode):
    image_label = getattr(getattr(presenter, "ui", None), "image_label", None)
    if image_label is None or not hasattr(image_label, "upload_diff_source_pil_image"):
        return

    if diff_mode not in {"highlight", "grayscale", "ssim", "edges"} and getattr(presenter, "_active_diff_toast_id", None) is not None:
        _dismiss_active_diff_toast(presenter)

    cached_diff_image = getattr(presenter.store.viewport.session_data.render_cache, "cached_diff_image", None)
    if cached_diff_image is None:
        cached_diff_image = getattr(presenter, "_cached_gl_diff_image", None)

    current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
    current_uploaded_id = (
        None if current_uploaded_diff is None else id(current_uploaded_diff)
    )
    target_diff_id = None if cached_diff_image is None else id(cached_diff_image)

    if diff_mode != "off" and cached_diff_image is not None:
        if current_uploaded_id != target_diff_id:
            image_label.upload_diff_source_pil_image(cached_diff_image)
    elif diff_mode == "off":
        if current_uploaded_diff is not None:
            image_label.upload_diff_source_pil_image(None)
        _dismiss_active_diff_toast(presenter)

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
        _build_gl_background_layers_task,
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
            _dismiss_active_diff_toast(presenter)
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
            _complete_diff_toast(presenter, cache_key)
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
        _dismiss_active_diff_toast(presenter)

    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    worker.signals.partial_result.connect(
        lambda progress_payload: _update_diff_toast_progress(
            presenter,
            cache_key,
            progress_payload,
        )
    )
    presenter.main_window_app.thread_pool.start(worker, priority=1)

def schedule_update(presenter):
    if hasattr(presenter.main_window_app, "_closing") and presenter.main_window_app._closing:
        return

    is_interactive = presenter.store.viewport.interaction_state.is_interactive_mode

    if is_interactive:
        presenter._pending_interactive_mode = True

    if is_interactive:
        presenter._update_scheduler_timer.stop()
        result = presenter.update_comparison_if_needed()
        if result:
            presenter._pending_interactive_mode = None
    else:
        if not presenter._update_scheduler_timer.isActive():
            presenter._update_scheduler_timer.start()

def update_comparison_if_needed(presenter):
    image_label = getattr(getattr(presenter, "ui", None), "image_label", None)
    if (
        not getattr(presenter.main_window_app, "_is_ui_stable", False)
        or presenter.store.viewport.interaction_state.resize_in_progress
    ):
        return False

    if not presenter.main_window_app.isVisible() or presenter.main_window_app.isMinimized():
        return False

    label_width, label_height = presenter.get_current_label_dimensions()
    if label_width <= 2 or label_height <= 2:
        return False

    if getattr(presenter.store.viewport.session_data.render_cache, "unification_in_progress", False):
        if presenter.store.viewport.session_data.image_state.image1 is None:
            return False

    source1 = presenter.store.document.full_res_image1 or presenter.store.document.original_image1
    source2 = presenter.store.document.full_res_image2 or presenter.store.document.original_image2

    if presenter.store.viewport.view_state.showing_single_image_mode != 0:
        image_to_show = (
            presenter.store.viewport.session_data.render_cache.display_cache_image1
            or presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
            or presenter.store.viewport.session_data.image_state.image1
            or source1
        ) if presenter.store.viewport.view_state.showing_single_image_mode == 1 else (
            presenter.store.viewport.session_data.render_cache.display_cache_image2
            or presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
            or presenter.store.viewport.session_data.image_state.image2
            or source2
        )
        presenter.view.display_single_image_on_label(image_to_show)
        return False

    if (
        presenter.store.viewport.session_data.image_state.image1 is None
        or presenter.store.viewport.session_data.image_state.image2 is None
        or not source1
        or not source2
    ):
        presenter.ui.image_label.clear()
        presenter.current_displayed_pixmap = None
        return False

    if presenter.background.ensure_images_unified(source1, source2):
        if not presenter.store.viewport.session_data.render_cache.display_cache_image1:
            presenter.background.create_preview_cache_async(
                presenter.store.viewport.session_data.image_state.image1, presenter.store.viewport.session_data.image_state.image2
            )
            return False

    src_resize1 = presenter.store.viewport.session_data.render_cache.display_cache_image1 or presenter.store.viewport.session_data.image_state.image1
    src_resize2 = presenter.store.viewport.session_data.render_cache.display_cache_image2 or presenter.store.viewport.session_data.image_state.image2
    scaled_w, scaled_h = get_scaled_pixmap_dimensions(
        src_resize1, src_resize2, label_width, label_height
    )

    if not presenter.view.is_gl_canvas() and not presenter.background.ensure_images_scaled(scaled_w, scaled_h):
        return False

    presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height = (scaled_w, scaled_h)
    img_x, img_y = (label_width - scaled_w) // 2, (label_height - scaled_h) // 2
    presenter.store.viewport.geometry_state.image_display_rect_on_label = Rect(img_x, img_y, scaled_w, scaled_h)

    current_bg_sig = presenter.background.get_background_signature(source1, source2)
    last_bg_sig = getattr(presenter, "_last_bg_signature", None)
    current_label_dims = (label_width, label_height)
    label_dims_changed = presenter._last_label_dims != current_label_dims

    bg_is_dirty = (
        (current_bg_sig != last_bg_sig)
        or label_dims_changed
        or (presenter._cached_base_pixmap is None)
    )

    diff_mode = getattr(presenter.store.viewport.view_state, "diff_mode", "off")
    if (
        presenter.view.is_gl_canvas()
        and diff_mode in ("highlight", "grayscale", "ssim", "edges")
        and getattr(presenter.store.viewport.session_data.render_cache, "cached_diff_image", None) is None
    ):
        from ui.presenters.image_canvas.magnifier import _request_cached_diff_image_async

        _request_cached_diff_image_async(
            presenter,
            source1,
            source2,
            diff_mode,
        )

    if presenter.view.is_gl_canvas():
        _sync_gl_diff_texture(
            presenter,
            diff_mode,
        )

    if bg_is_dirty:
        if presenter.view.is_gl_canvas():
            img1 = (
                presenter.store.viewport.session_data.render_cache.display_cache_image1
                or presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
                or presenter.store.viewport.session_data.image_state.image1
            )
            img2 = (
                presenter.store.viewport.session_data.render_cache.display_cache_image2
                or presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
                or presenter.store.viewport.session_data.image_state.image2
            )
            channel_mode = getattr(presenter.store.viewport.view_state, "channel_view_mode", "RGB")
            if diff_mode != "off":
                bg_layers_key = (
                    id(img1),
                    id(img2),
                    getattr(img1, "size", None),
                    getattr(img2, "size", None),
                    diff_mode,
                    channel_mode,
                )
                if getattr(presenter, "_cached_gl_background_layers_key", None) != bg_layers_key:
                    request_gl_background_layers_async(
                        presenter,
                        img1,
                        img2,
                        diff_mode,
                        channel_mode,
                        bg_layers_key,
                        optimize_ssim=False,
                    )
                    return False
                gl_img1, gl_img2 = getattr(
                    presenter, "_cached_gl_background_layers", (img1, img2)
                )
            else:
                gl_img1, gl_img2 = presenter.view.prepare_gl_background_layers(img1, img2)
            gui_source1 = (
                presenter.store.document.full_res_image1
                or presenter.store.document.original_image1
            )
            gui_source2 = (
                presenter.store.document.full_res_image2
                or presenter.store.document.original_image2
            )
            source_key = (
                presenter.store.document.image1_path,
                presenter.store.document.image2_path,
                id(gui_source1) if gui_source1 is not None else 0,
                id(gui_source2) if gui_source2 is not None else 0,
                gui_source1.size if gui_source1 is not None else None,
                gui_source2.size if gui_source2 is not None else None,
            )
            gl_img_sig = (
                id(gl_img1),
                id(gl_img2),
                current_label_dims,
                presenter.store.viewport.view_state.diff_mode,
                presenter.store.viewport.view_state.channel_view_mode,
                source_key,
            )
            if gl_img_sig != getattr(presenter, "_gl_last_img_sig", None):
                presenter._gl_last_img_sig = gl_img_sig
                if gl_img1 and gl_img2:
                    if hasattr(presenter.ui.image_label, "set_apply_channel_mode_in_shader"):
                        presenter.ui.image_label.set_apply_channel_mode_in_shader(False)
                    kwargs = {}
                    if gui_source1 is not None and gui_source2 is not None:
                        kwargs = {
                            "source_image1": gui_source1,
                            "source_image2": gui_source2,
                            "source_key": source_key,
                        }
                    presenter.ui.image_label.set_pil_layers(
                        gl_img1,
                        gl_img2,
                        shader_letterbox=True,
                        **kwargs,
                    )
            presenter._last_mag_signature = None
            presenter._last_bg_signature = current_bg_sig
            presenter._last_label_dims = current_label_dims
            if presenter._cached_base_pixmap is None:
                presenter._cached_base_pixmap = QPixmap(1, 1)
        else:
            if presenter._is_generating_background:
                return False

            presenter._is_generating_background = True
            presenter._last_bg_signature = current_bg_sig
            presenter._last_label_dims = current_label_dims
            presenter._last_mag_signature = None
            presenter.background.render_background(current_bg_sig)
            return True
    if presenter.store.viewport.view_state.use_magnifier:
        current_mag_sig = presenter.magnifier.get_signature()
        last_mag_sig = getattr(presenter, "_last_mag_signature", None)
        mag_pixmap = getattr(presenter.ui.image_label, "_magnifier_pixmap", None)
        if presenter.view.is_gl_canvas():
            current_mag_state = (
                current_mag_sig,
                getattr(image_label, "_source_images_ready", False),
                tuple(getattr(image_label, "_source_image_ids", []) or []),
            )
            mag_is_dirty = current_mag_state != last_mag_sig
        else:
            mag_is_dirty = (current_mag_sig != last_mag_sig) or (mag_pixmap is None)
            current_mag_state = current_mag_sig

        if mag_is_dirty:
            if presenter.view.is_gl_canvas():
                presenter.magnifier.render_gl_fast()
                presenter._last_mag_signature = current_mag_state
                return True

            if presenter.magnifier.render_layer(current_mag_sig):
                presenter._last_mag_signature = current_mag_state
                return True
            return False
    else:
        if presenter.view.is_gl_canvas():
            if hasattr(presenter.ui.image_label, "clear_magnifier_gpu"):
                presenter.ui.image_label.clear_magnifier_gpu()
            if hasattr(presenter.ui.image_label, "set_overlay_coords"):
                presenter.ui.image_label.set_overlay_coords(None, 0, [], 0)
            presenter._last_mag_signature = None
        else:
            mag_pixmap = getattr(presenter.ui.image_label, "_magnifier_pixmap", None)
            if mag_pixmap is not None:
                if hasattr(presenter.ui.image_label, "set_magnifier_content"):
                    presenter.ui.image_label.set_magnifier_content(None, None)
                else:
                    presenter.view.set_image_layers(presenter._cached_base_pixmap)
                presenter._last_mag_signature = None
                if hasattr(presenter.ui.image_label, "set_overlay_coords"):
                    presenter.ui.image_label.set_overlay_coords(None, 0, [], 0)
                elif hasattr(presenter.ui.image_label, "set_capture_area"):
                    presenter.ui.image_label.set_capture_area(None, 0)
    return False

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

        presenter.background.start_scaling_worker(src1, src2, w, h)
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
        logger.error(f"Scaling start failed: {exc}")

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

def should_use_dirty_rects_optimization(presenter, render_params_dict, label_dims=None):
    if not presenter.store.viewport.interaction_state.is_interactive_mode:
        return False
    if render_params_dict.get("use_magnifier", False):
        return False
    if not presenter._cached_base_pixmap or presenter._cached_base_pixmap.isNull():
        return False
    if label_dims is None:
        label_dims = presenter.get_current_label_dimensions()

    current_params = (
        render_params_dict.get("diff_mode", "off"),
        render_params_dict.get("channel_view_mode", "RGB"),
        render_params_dict.get("is_horizontal", False),
        render_params_dict.get("include_file_names_in_saved", False),
        label_dims,
    )
    if presenter._cached_render_params and presenter._cached_render_params[:4] != current_params[:4]:
        return False
    return True

def render_background(presenter, sig):
    presenter.current_rendering_task_id += 1
    task_id = presenter.current_rendering_task_id

    render_params = presenter.store.viewport.get_render_params()
    render_params["use_magnifier"] = False
    render_params["is_interactive_mode"] = presenter.store.viewport.interaction_state.is_interactive_mode

    image1 = presenter.store.viewport.session_data.render_cache.scaled_image1_for_display
    image2 = presenter.store.viewport.session_data.render_cache.scaled_image2_for_display
    if not image1 or not image2:
        return

    params_wrapper = {
        "render_params_dict": render_params,
        "image1_scaled_for_display": image1,
        "image2_scaled_for_display": image2,
        "original_image1_pil": presenter.store.document.full_res_image1,
        "original_image2_pil": presenter.store.document.full_res_image2,
        "magnifier_coords": None,
        "font_path_absolute": FontManager.get_instance().get_font_path_for_image_text(presenter.store),
        "file_name1_text": presenter.store.document.get_current_display_name(1),
        "file_name2_text": presenter.store.document.get_current_display_name(2),
        "finished_signal": presenter._worker_finished_signal,
        "error_signal": presenter._worker_error_signal,
        "task_id": task_id,
        "label_dims": presenter.get_current_label_dimensions(),
        "type": "background",
        "session_caches": {"background": presenter.store.viewport.session_data.render_cache.caches},
    }
    worker = ImageRenderingWorker(params_wrapper, lambda: presenter.current_rendering_task_id)
    priority = 1 if not presenter.store.viewport.interaction_state.is_interactive_mode else 0
    presenter.main_window_app.thread_pool.start(worker, priority=priority)

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

def finish_resize_delay(presenter):
    if presenter.store.viewport.interaction_state.resize_in_progress:
        presenter.store.viewport.interaction_state.resize_in_progress = False
        presenter.schedule_update()
