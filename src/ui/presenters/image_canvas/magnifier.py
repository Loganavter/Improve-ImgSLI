import logging

from PyQt6.QtCore import QPoint, QPointF, QRect
from PyQt6.QtGui import QPainter

from domain.types import Point, Rect
from domain.qt_adapters import color_to_qcolor
from shared_toolkit.ui.managers.font_manager import FontManager
from shared_toolkit.workers import GenericWorker
from utils.resource_loader import get_magnifier_drawing_coords

logger = logging.getLogger("ImproveImgSLI")
CAPTURE_RING_AA_PX = 1.15

def _build_cached_diff_image_task(
    source1,
    source2,
    diff_mode,
    progress_callback=None,
):
    from plugins.analysis.processing import build_cached_diff_image

    return build_cached_diff_image(
        source1,
        source2,
        diff_mode,
        "RGB",
        optimize_ssim=False,
        progress_callback=progress_callback,
    )

def _request_cached_diff_image_async(presenter, source1, source2, diff_mode):
    from ui.presenters.image_canvas.background import (
        _complete_diff_toast,
        _dismiss_active_diff_toast,
        _show_or_reuse_diff_toast,
        _update_diff_toast_progress,
    )

    if diff_mode not in ("highlight", "grayscale", "ssim", "edges"):
        return
    if source1 is None or (source2 is None and diff_mode != "edges"):
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
    if diff_mode in ("highlight", "grayscale", "ssim", "edges"):
        _show_or_reuse_diff_toast(presenter, diff_mode, request_key)

    def _on_result(diff_image):
        presenter._pending_cached_diff_request_key = None
        if diff_image is None:
            _dismiss_active_diff_toast(presenter)
            return
        presenter.store.viewport.session_data.render_cache.cached_diff_image = diff_image
        if diff_mode in ("highlight", "grayscale", "ssim", "edges"):
            _complete_diff_toast(presenter, request_key)
        presenter._last_mag_signature = None
        presenter.schedule_update()

    def _on_error(error_tuple):
        presenter._pending_cached_diff_request_key = None
        exctype, value, _traceback_str = error_tuple
        logger.error(
            "Failed to build cached diff image asynchronously: %s: %s",
            getattr(exctype, "__name__", exctype),
            value,
        )
        _dismiss_active_diff_toast(presenter)

    worker = GenericWorker(_build_cached_diff_image_task, source1, source2, diff_mode)
    worker.kwargs["progress_callback"] = worker.signals.partial_result.emit
    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    worker.signals.partial_result.connect(
        lambda progress_payload: _update_diff_toast_progress(
            presenter,
            request_key,
            progress_payload,
        )
    )
    presenter.main_window_app.thread_pool.start(worker, priority=1)

def _request_magnifier_cached_diff_image_async(presenter, source1, source2, diff_mode):
    if diff_mode not in ("highlight", "grayscale", "ssim", "edges"):
        return
    if source1 is None or (source2 is None and diff_mode != "edges"):
        return

    request_key = (
        diff_mode,
        id(source1),
        id(source2) if source2 is not None else 0,
        getattr(source1, "size", None),
        getattr(source2, "size", None),
    )
    pending_key = getattr(presenter, "_pending_magnifier_cached_diff_request_key", None)
    if pending_key == request_key:
        return

    presenter._pending_magnifier_cached_diff_request_key = request_key

    def _on_result(diff_image):
        if getattr(presenter, "_pending_magnifier_cached_diff_request_key", None) != request_key:
            return
        presenter._pending_magnifier_cached_diff_request_key = None
        if diff_image is None:
            return
        presenter._magnifier_cached_diff_request_key = request_key
        presenter._magnifier_cached_diff_image = diff_image
        presenter._last_mag_signature = None
        presenter.schedule_update()

    def _on_error(error_tuple):
        if getattr(presenter, "_pending_magnifier_cached_diff_request_key", None) != request_key:
            return
        presenter._pending_magnifier_cached_diff_request_key = None
        exctype, value, _traceback_str = error_tuple
        logger.error(
            "Failed to build magnifier cached diff image asynchronously: %s: %s",
            getattr(exctype, "__name__", exctype),
            value,
        )

    worker = GenericWorker(_build_cached_diff_image_task, source1, source2, diff_mode)
    worker.signals.result.connect(_on_result)
    worker.signals.error.connect(_on_error)
    presenter.main_window_app.thread_pool.start(worker, priority=1)

def _ensure_cached_diff_image(
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
    if cached is not None or diff_mode not in ("highlight", "grayscale", "ssim", "edges"):
        return cached

    gl_cached = getattr(presenter, "_cached_gl_diff_image", None)
    if gl_cached is not None:
        return gl_cached
    return None

def _is_effective_magnifier_interactive(vp) -> bool:
    return bool(
        getattr(vp.interaction_state, "is_interactive_mode", False)
        and getattr(vp.view_state, "optimize_magnifier_movement", True)
    )

def _get_effective_main_interpolation_method(vp) -> str:
    viewport_value = getattr(vp.render_config, "interpolation_method", None)
    if viewport_value:
        return viewport_value
    render_cfg = getattr(vp, "render_config", None)
    return getattr(render_cfg, "interpolation_method", "BILINEAR") if render_cfg else "BILINEAR"

def _clamp_capture_overlay_geometry(
    vp,
    image_label,
    center_x: float,
    center_y: float,
    radius: float,
    stroke_margin: float = 0.0,
):
    rect = _get_effective_overlay_bounds_rect(vp, image_label)
    if rect is None or radius <= 0:
        return center_x, center_y, max(0.0, radius)

    left = float(rect.x)
    top = float(rect.y)
    right = float(rect.x + rect.w)
    bottom = float(rect.y + rect.h)

    usable_left = left + stroke_margin
    usable_top = top + stroke_margin
    usable_right = right - stroke_margin
    usable_bottom = bottom - stroke_margin

    max_radius_x = max(0.0, (usable_right - usable_left) / 2.0)
    max_radius_y = max(0.0, (usable_bottom - usable_top) / 2.0)
    clamped_radius = min(radius, max_radius_x, max_radius_y)

    clamped_x = min(
        max(center_x, usable_left + clamped_radius),
        usable_right - clamped_radius,
    )
    clamped_y = min(
        max(center_y, usable_top + clamped_radius),
        usable_bottom - clamped_radius,
    )
    return clamped_x, clamped_y, clamped_radius

def _get_effective_overlay_bounds_rect(vp, image_label) -> Rect | None:
    geometry = getattr(vp, "geometry_state", None)
    if geometry is None:
        return None

    rect = getattr(geometry, "image_display_rect_on_label", None)
    rect_w = int(getattr(rect, "w", 0) or 0)
    rect_h = int(getattr(rect, "h", 0) or 0)

    if rect_w > 0 and rect_h > 0:
        base_rect = Rect(
            int(getattr(rect, "x", 0) or 0),
            int(getattr(rect, "y", 0) or 0),
            rect_w,
            rect_h,
        )
    else:
        pix_w = int(getattr(geometry, "pixmap_width", 0) or 0)
        pix_h = int(getattr(geometry, "pixmap_height", 0) or 0)
        if pix_w <= 0 or pix_h <= 0 or image_label is None:
            return None
        label_w = int(getattr(image_label, "width", lambda: 0)() or 0)
        label_h = int(getattr(image_label, "height", lambda: 0)() or 0)
        if label_w <= 0 or label_h <= 0:
            return None
        base_rect = Rect(
            int((label_w - pix_w) // 2),
            int((label_h - pix_h) // 2),
            pix_w,
            pix_h,
        )

    clip_rect = getattr(vp, "divider_clip_rect", None)
    image_state = getattr(getattr(vp, "session_data", None), "image_state", None)
    display_image = getattr(image_state, "image1", None)
    img_w = int(getattr(display_image, "width", 0) or 0)
    img_h = int(getattr(display_image, "height", 0) or 0)
    if not clip_rect or img_w <= 0 or img_h <= 0:
        return base_rect

    clip_x, clip_y, clip_w, clip_h = clip_rect
    if clip_w <= 0 or clip_h <= 0:
        return base_rect

    scale_x = base_rect.w / float(img_w)
    scale_y = base_rect.h / float(img_h)
    return Rect(
        int(round(base_rect.x + (clip_x * scale_x))),
        int(round(base_rect.y + (clip_y * scale_y))),
        max(1, int(round(clip_w * scale_x))),
        max(1, int(round(clip_h * scale_y))),
    )

def sync_widget_overlay_coords(presenter):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    geometry = vp.geometry_state
    image_state = vp.session_data.image_state
    image_label = presenter.ui.image_label

    if not view.use_magnifier or not image_state.image1 or geometry.pixmap_width <= 0:
        if hasattr(image_label, "set_overlay_coords"):
            image_label.set_overlay_coords(None, 0, [], 0)
        return

    pix_w, pix_h = geometry.pixmap_width, geometry.pixmap_height
    label_w, label_h = presenter.get_current_label_dimensions()

    offset_x = (label_w - pix_w) // 2
    offset_y = (label_h - pix_h) // 2

    from shared.image_processing.pipeline import _clamp_capture_position

    ref_dim = min(pix_w, pix_h)
    cap_size_px = view.capture_size_relative * ref_dim

    rel_x, rel_y = _clamp_capture_position(
        view.capture_position_relative.x,
        view.capture_position_relative.y,
        pix_w,
        pix_h,
        view.capture_size_relative,
    )

    cap_center_x = offset_x + (rel_x * pix_w)
    cap_center_y = offset_y + (rel_y * pix_h)
    capture_radius = cap_size_px / 2.0
    zoom_level = float(getattr(image_label, "zoom_level", 1.0) or 1.0)
    scaled_radius = capture_radius * zoom_level
    line_width_px = max(2.0, float(scaled_radius * 2.0) * 0.0105)
    stroke_margin = max(1.0, (line_width_px / 2.0) + CAPTURE_RING_AA_PX)
    capture_center_before = QPointF(cap_center_x, cap_center_y)
    capture_radius_before = capture_radius
    cap_center_x, cap_center_y, capture_radius = _clamp_capture_overlay_geometry(
        vp,
        image_label,
        cap_center_x,
        cap_center_y,
        capture_radius,
        stroke_margin=stroke_margin,
    )
    capture_center = QPointF(cap_center_x, cap_center_y)
    target_max_dim = float(max(pix_w, pix_h))
    offset_visual = view.magnifier_offset_relative_visual
    spacing_visual = view.magnifier_spacing_relative_visual

    mag_size_px = view.magnifier_size_relative * target_max_dim
    mag_radius = mag_size_px / 2.0

    if (
        view.freeze_magnifier
        and view.frozen_capture_point_relative
    ):
        base_x = offset_x + (view.frozen_capture_point_relative.x * pix_w)
        base_y = offset_y + (view.frozen_capture_point_relative.y * pix_h)
    else:
        base_x = cap_center_x
        base_y = cap_center_y

    base_mag_x = base_x + (offset_visual.x * target_max_dim)
    base_mag_y = base_y + (offset_visual.y * target_max_dim)

    mag_centers = []
    is_visual_diff = view.diff_mode in ("highlight", "grayscale", "ssim", "edges")

    if view.is_magnifier_combined:
        if is_visual_diff and view.magnifier_visible_center:
            if not view.magnifier_is_horizontal:
                if view.magnifier_visible_center:
                    mag_centers.append(QPointF(base_mag_x, base_mag_y - mag_radius - 4))
                if view.magnifier_visible_left or view.magnifier_visible_right:
                    mag_centers.append(QPointF(base_mag_x, base_mag_y + mag_radius + 4))
            else:
                if view.magnifier_visible_center:
                    mag_centers.append(QPointF(base_mag_x - mag_radius - 4, base_mag_y))
                if view.magnifier_visible_left or view.magnifier_visible_right:
                    mag_centers.append(QPointF(base_mag_x + mag_radius + 4, base_mag_y))
        else:
            mag_centers.append(QPointF(base_mag_x, base_mag_y))
    else:
        spacing_px = spacing_visual * target_max_dim
        dist = mag_radius + (spacing_px / 2.0)

        if not view.magnifier_is_horizontal:
            c1 = QPointF(base_mag_x - dist, base_mag_y)
            c2 = QPointF(base_mag_x + dist, base_mag_y)
        else:
            c1 = QPointF(base_mag_x, base_mag_y - dist)
            c2 = QPointF(base_mag_x, base_mag_y + dist)

        if is_visual_diff:
            offset_3 = max(mag_radius * 2, mag_radius * 2 + spacing_px)
            if not view.magnifier_is_horizontal:
                c1_diff = QPointF(base_mag_x - offset_3, base_mag_y)
                c2_diff = QPointF(base_mag_x + offset_3, base_mag_y)
            else:
                c1_diff = QPointF(base_mag_x, base_mag_y - offset_3)
                c2_diff = QPointF(base_mag_x, base_mag_y + offset_3)
            if view.magnifier_visible_left:
                mag_centers.append(c1_diff)
            if view.magnifier_visible_right:
                mag_centers.append(c2_diff)
            if view.magnifier_visible_center:
                mag_centers.append(QPointF(base_mag_x, base_mag_y))
        else:
            if view.magnifier_visible_left:
                mag_centers.append(c1)
            if view.magnifier_visible_right:
                mag_centers.append(c2)

    if hasattr(image_label, "set_overlay_coords"):
        if render.show_capture_area_on_main_image:
            image_label.set_overlay_coords(
                capture_center, capture_radius, mag_centers, mag_radius
            )
        else:
            image_label.set_overlay_coords(None, 0, mag_centers, mag_radius)

    if mag_radius > 0 and mag_centers:
        interactive_center = None
        if view.is_magnifier_combined:
            if is_visual_diff and view.magnifier_visible_center and len(mag_centers) >= 2:
                interactive_center = mag_centers[1]
            else:
                interactive_center = mag_centers[0]
        elif len(mag_centers) == 1:
            interactive_center = mag_centers[0]

        if interactive_center is not None:
            geometry.magnifier_screen_center = Point(
                float(interactive_center.x()), float(interactive_center.y())
            )
            geometry.magnifier_screen_size = int(round(mag_radius * 2.0))

    if hasattr(image_label, "set_guides_params"):
        image_label.set_guides_params(
            render.show_magnifier_guides,
            color_to_qcolor(render.magnifier_laser_color),
            render.magnifier_guides_thickness,
        )
    if hasattr(image_label, "set_capture_color"):
        image_label.set_capture_color(color_to_qcolor(render.capture_ring_color))
    if hasattr(image_label, "set_split_pos"):
        image_label.set_split_pos(view.split_position_visual)

def render_magnifier_gl_fast(presenter):
    vp = presenter.store.viewport
    view = vp.view_state
    render = vp.render_config
    geometry = vp.geometry_state
    session = vp.session_data
    image_label = presenter.ui.image_label
    if hasattr(image_label, "begin_update_batch"):
        image_label.begin_update_batch()
    try:
        source_ready = getattr(image_label, "_source_images_ready", False)

        sync_widget_overlay_coords(presenter)

        tex_img1 = None
        tex_img2 = None
        using_source_images = source_ready
        if using_source_images:
            if hasattr(image_label, "_source_pil_images") and len(image_label._source_pil_images) >= 2:
                tex_img1, tex_img2 = image_label._source_pil_images[:2]
        else:
            if hasattr(image_label, "_stored_pil_images") and len(image_label._stored_pil_images) >= 2:
                tex_img1, tex_img2 = image_label._stored_pil_images[:2]
        tex_img1 = tex_img1 or session.render_cache.scaled_image1_for_display or session.image_state.image1
        tex_img2 = tex_img2 or session.render_cache.scaled_image2_for_display or session.image_state.image2
        if not tex_img1 or not tex_img2:
            return

        from shared.image_processing.pipeline import _clamp_capture_position

        disp_w = max(1, int(geometry.pixmap_width or presenter.ui.image_label.width() or tex_img1.width))
        disp_h = max(1, int(geometry.pixmap_height or presenter.ui.image_label.height() or tex_img1.height))
        cap_x, cap_y = _clamp_capture_position(
            view.capture_position_relative.x,
            view.capture_position_relative.y,
            disp_w,
            disp_h,
            view.capture_size_relative,
        )
        cap_half_disp = view.capture_size_relative * min(disp_w, disp_h) / 2.0
        cap_half_u_img = cap_half_disp / disp_w
        cap_half_v_img = cap_half_disp / disp_h

        uv_rect1 = (
            cap_x - cap_half_u_img,
            cap_y - cap_half_v_img,
            cap_x + cap_half_u_img,
            cap_y + cap_half_v_img,
        )
        uv_rect2 = uv_rect1
        pix_w = geometry.pixmap_width or presenter.ui.image_label.width()
        pix_h = geometry.pixmap_height or presenter.ui.image_label.height()
        target_max = float(max(pix_w, pix_h))
        mag_px = int(view.magnifier_size_relative * target_max)
        if mag_px < 4:
            return

        diff_mode_str = getattr(vp.view_state, "diff_mode", "off")
        local_diff_source1 = (
            presenter.store.document.full_res_image1
            or presenter.store.document.original_image1
            or tex_img1
        )
        local_diff_source2 = (
            presenter.store.document.full_res_image2
            or presenter.store.document.original_image2
            or tex_img2
        )

        label_w, label_h = presenter.get_current_label_dimensions()
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        target_max = float(max(pix_w, pix_h))
        offset = view.magnifier_offset_relative_visual
        spacing_visual = view.magnifier_spacing_relative_visual
        if (
            view.freeze_magnifier
            and view.frozen_capture_point_relative
        ):
            clamped_bx, clamped_by = _clamp_capture_position(
                view.frozen_capture_point_relative.x,
                view.frozen_capture_point_relative.y,
                pix_w, pix_h,
                view.capture_size_relative,
            )
            base_x = offset_x + clamped_bx * pix_w
            base_y = offset_y + clamped_by * pix_h
        else:
            clamped_bx, clamped_by = _clamp_capture_position(
                view.capture_position_relative.x,
                view.capture_position_relative.y,
                pix_w, pix_h,
                view.capture_size_relative,
            )
            base_x = offset_x + clamped_bx * pix_w
            base_y = offset_y + clamped_by * pix_h
        cx = base_x + offset.x * target_max
        cy = base_y + offset.y * target_max
        radius = mag_px / 2.0

        border_color = (
            color_to_qcolor(render.magnifier_border_color)
        )
        show_left = view.magnifier_visible_left
        show_right = view.magnifier_visible_right
        show_center = view.magnifier_visible_center

        is_visual_diff = diff_mode_str in ("highlight", "grayscale", "ssim", "edges") and show_center
        effective_interactive = _is_effective_magnifier_interactive(vp)

        channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
            getattr(vp.view_state, "channel_view_mode", "RGB"), 0
        )
        if effective_interactive:
            interp_key = getattr(
                vp.render_config, "magnifier_movement_interpolation_method", "BILINEAR"
            )
        else:
            interp_key = _get_effective_main_interpolation_method(vp)
        interp_key = (interp_key or "BILINEAR").upper()
        interp_mode_int = {
            "NEAREST": 0,
            "BILINEAR": 1,
            "BICUBIC": 2,
            "LANCZOS": 3,
            "EWA_LANCZOS": 4,
        }.get(interp_key, 1)
        cached_diff_image = _ensure_cached_diff_image(
            presenter,
            tex_img1,
            tex_img2,
            local_source1=local_diff_source1,
            local_source2=local_diff_source2,
        )
        current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
        diff_image_for_magnifier = cached_diff_image or current_uploaded_diff
        render_visual_diff = (
            diff_mode_str in ("highlight", "grayscale", "ssim", "edges")
            and is_visual_diff
            and diff_image_for_magnifier is not None
        )
        diff_mode_int = 4 if render_visual_diff and diff_mode_str == "ssim" else 0

        if cached_diff_image is not None:
            image_label.upload_diff_source_pil_image(cached_diff_image)
        elif diff_mode_str not in ("highlight", "grayscale", "ssim", "edges"):
            image_label.upload_diff_source_pil_image(None)

        div_color_t = presenter.view.get_divider_color_tuple(vp)
        mag_px_f = float(mag_px)
        div_thickness_uv = (render.magnifier_divider_thickness / mag_px_f) * 0.5 if mag_px_f > 0 else 0.005

        slots = []

        def make_slot(center, source, is_combined=False):
            return {
                "center": center,
                "radius": radius,
                "uv_rect": uv_rect1,
                "uv_rect2": uv_rect2,
                "source": source,
                "is_combined": is_combined,
                "internal_split": view.magnifier_internal_split,
                "horizontal": view.magnifier_is_horizontal,
                "divider_visible": render.magnifier_divider_visible,
                "divider_color": div_color_t,
                "divider_thickness_px": render.magnifier_divider_thickness,
                "divider_thickness_uv": div_thickness_uv,
            }

        if view.is_magnifier_combined:
            if render_visual_diff:
                if not view.magnifier_is_horizontal:
                    diff_c = QPointF(cx, cy - radius - 4)
                    comb_c = QPointF(cx, cy + radius + 4)
                else:
                    diff_c = QPointF(cx - radius - 4, cy)
                    comb_c = QPointF(cx + radius + 4, cy)
                slots.append(make_slot(diff_c, 2) if show_center else None)
                if show_left and show_right:
                    slots.append(make_slot(comb_c, 0, is_combined=True))
                elif show_left:
                    slots.append(make_slot(comb_c, 0))
                elif show_right:
                    slots.append(make_slot(comb_c, 1))
                else:
                    slots.append(None)
                slots.append(None)
            else:
                if not show_left and not show_right:
                    slots = [None, None, None]
                elif show_left and show_right:
                    slots.extend([make_slot(QPointF(cx, cy), 0, is_combined=True), None, None])
                elif show_left:
                    slots.extend([make_slot(QPointF(cx, cy), 0), None, None])
                else:
                    slots.extend([make_slot(QPointF(cx, cy), 1), None, None])
        elif render_visual_diff:
            spacing_px = spacing_visual * target_max
            offset_3 = max(mag_px, mag_px + spacing_px)
            if not view.magnifier_is_horizontal:
                c_left = QPointF(cx - offset_3, cy)
                c_right = QPointF(cx + offset_3, cy)
            else:
                c_left = QPointF(cx, cy - offset_3)
                c_right = QPointF(cx, cy + offset_3)
            slots.append(make_slot(c_left, 0) if show_left else None)
            slots.append(make_slot(c_right, 1) if show_right else None)
            slots.append(make_slot(QPointF(cx, cy), 2) if show_center else None)
        else:
            if not show_left and not show_right:
                slots = [None, None, None]
            elif show_left and show_right:
                spacing_px = spacing_visual * target_max
                dist = radius + spacing_px / 2.0
                if not view.magnifier_is_horizontal:
                    c1 = QPointF(cx - dist, cy)
                    c2 = QPointF(cx + dist, cy)
                else:
                    c1 = QPointF(cx, cy - dist)
                    c2 = QPointF(cx, cy + dist)
                slots.extend([make_slot(c1, 0), make_slot(c2, 1), None])
            elif show_left:
                slots.extend([make_slot(QPointF(cx, cy), 0), None, None])
            else:
                slots.extend([make_slot(QPointF(cx, cy), 1), None, None])

        image_label.set_magnifier_gpu_params(
            slots, channel_mode_int, diff_mode_int, 20.0 / 255.0, border_color, 2.0, interp_mode_int
        )
    finally:
        if hasattr(image_label, "end_update_batch"):
            image_label.end_update_batch()

def render_magnifier_diff_fallback(
    presenter,
    vp,
    orig1,
    orig2,
    diff_mode,
    slots,
    mag_px,
    border_color,
    radius,
    interp_key,
):
    from shared.image_processing.pipeline import RenderingPipeline

    diff_result = None
    if orig1 is not None and (orig2 is not None or diff_mode == "edges"):
        try:
            drawer = RenderingPipeline().magnifier_drawer
            if orig2 is not None:
                crop_box1, crop_box2 = drawer._compute_crop_boxes_subpixel(
                    orig1, orig2, presenter.store
                )
            else:
                crop_box1 = drawer._compute_single_crop_box_subpixel(
                    orig1.width,
                    orig1.height,
                    presenter.store.viewport.view_state.capture_position_relative.x,
                    presenter.store.viewport.view_state.capture_position_relative.y,
                    presenter.store.viewport.view_state.capture_size_relative,
                )
                crop_box2 = crop_box1
            diff_result = drawer._build_diff_patch(
                store=presenter.store,
                diff_mode=diff_mode,
                magnifier_size=mag_px,
                image1_for_crop=orig1,
                image2_for_crop=orig2,
                crop_box1=crop_box1,
                crop_box2=crop_box2,
                interpolation_method=interp_key,
                is_interactive=_is_effective_magnifier_interactive(vp),
            )
            if diff_result is not None and diff_result.mode != "RGBA":
                diff_result = diff_result.convert("RGBA")
        except Exception:
            logger.exception("Failed to build diff magnifier patch via CPU fallback")

    diff_slot_index = None
    diff_slot = None
    for i, slot in enumerate(slots):
        if slot and slot.get("source") == 2:
            diff_slot_index = i
            diff_slot = slot
            slots[i] = None
            break

    channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(getattr(vp.view_state, "channel_view_mode", "RGB"), 0)
    interp_mode_int = {"NEAREST": 0, "BILINEAR": 1, "BICUBIC": 2, "LANCZOS": 3, "EWA_LANCZOS": 4}.get(interp_key, 1)
    presenter.ui.image_label.set_magnifier_gpu_params(
        slots, channel_mode_int, 0, 20.0 / 255.0, border_color, 2.0, interp_mode_int
    )

    if diff_slot is not None:
        if diff_result is not None:
            presenter.ui.image_label.upload_magnifier_crop(
                diff_result, diff_slot["center"], radius, border_color, 2.0, index=diff_slot_index
            )
        else:
            presenter.ui.image_label.upload_magnifier_crop(None, QPointF(0, 0), 0, index=diff_slot_index)

def render_magnifier_layer(presenter, sig):
    if not presenter._cached_base_pixmap:
        return False
    if presenter._is_magnifier_worker_running:
        presenter._magnifier_update_pending = True
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
            logger.warning("[RENDER] Invalid magnifier bbox in coordinates")
            return False
    except Exception as exc:
        logger.error(f"[RENDER] Geometry calculation failed: {exc}", exc_info=True)
        return False

    image1 = presenter.store.viewport.session_data.render_cache.scaled_image1_for_display or presenter.store.viewport.session_data.image_state.image1
    image2 = presenter.store.viewport.session_data.render_cache.scaled_image2_for_display or presenter.store.viewport.session_data.image_state.image2
    if not image1 or not image2:
        logger.warning("[RENDER] Missing images for magnifier rendering")
        return False

    render_params = presenter.store.viewport.get_render_params()
    render_params["is_interactive_mode"] = _is_effective_magnifier_interactive(
        presenter.store.viewport
    )
    render_params["optimize_magnifier_movement"] = getattr(
        presenter.store.viewport, "optimize_magnifier_movement", True
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
    priority = 0 if _is_effective_magnifier_interactive(presenter.store.viewport) else 2
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
        logger.error(f"Failed to start magnifier-only worker: {exc}", exc_info=True)

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
        logger.error(f"Failed to start capture-area-only worker: {exc}", exc_info=True)

def on_capture_patch_ready(presenter, result):
    if not result:
        return
    try:
        capture_patch_pil, patch_pos, task_id = result
        if task_id < presenter._last_displayed_task_id:
            return
        presenter._last_displayed_task_id = task_id
        if not capture_patch_pil:
            if presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull():
                presenter.ui.image_label.setPixmap(presenter._cached_base_pixmap)
            return

        from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

        capture_pixmap = pil_to_qpixmap_optimized(capture_patch_pil, copy=False)
        if capture_pixmap.isNull():
            return
        if presenter._cached_base_pixmap and not presenter._cached_base_pixmap.isNull():
            result_pixmap = presenter._cached_base_pixmap.copy()
            painter = QPainter(result_pixmap)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.drawPixmap(patch_pos, capture_pixmap)
            painter.end()
            presenter.ui.image_label.setPixmap(result_pixmap)
            presenter.current_displayed_pixmap = result_pixmap
    except Exception as exc:
        logger.error(f"Error displaying capture area patch: {exc}", exc_info=True)

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
    magnifier_patch, mag_pos = pipeline.render_magnifier_patch(ctx)
    return {"magnifier_patch": magnifier_patch, "magnifier_pos": mag_pos}, task_id

def on_magnifier_worker_error(presenter, error_tuple):
    presenter._is_magnifier_worker_running = False
    exctype, value, traceback_str = error_tuple
    error_msg = f"{exctype.__name__}: {value}"
    if traceback_str:
        logger.error(f"[RENDER] Magnifier worker error: {error_msg}\n{traceback_str}")
    else:
        logger.error(f"[RENDER] Magnifier worker error: {error_msg}")

def on_magnifier_layer_ready(presenter, result):
    presenter._is_magnifier_worker_running = False
    data, task_id = result
    if task_id < presenter._last_displayed_task_id:
        if presenter._magnifier_update_pending:
            presenter._magnifier_update_pending = False
            presenter._last_mag_signature = None
            presenter.update_comparison_if_needed()
        return
    presenter._last_displayed_task_id = task_id

    from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

    mag_patch = data.get("magnifier_patch")
    mag_pos = data.get("magnifier_pos")
    mag_pixmap = pil_to_qpixmap_optimized(mag_patch, copy=False) if mag_patch else None

    if not mag_pixmap or mag_pixmap.isNull() or not mag_pos:
        if hasattr(presenter.ui.image_label, "set_magnifier_content"):
            presenter.ui.image_label.set_magnifier_content(None, None)
    else:
        label_w, label_h = presenter.get_current_label_dimensions()
        pix_w, pix_h = presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        final_mag_pos_screen = QPoint(offset_x + mag_pos.x(), offset_y + mag_pos.y())
        if hasattr(presenter.ui.image_label, "set_magnifier_content"):
            presenter.ui.image_label.set_magnifier_content(mag_pixmap, final_mag_pos_screen)
        else:
            presenter.view.set_image_layers(
                presenter._cached_base_pixmap, mag_pixmap, final_mag_pos_screen
            )

    if presenter._magnifier_update_pending:
        presenter._magnifier_update_pending = False
        presenter._last_mag_signature = None
        presenter.update_comparison_if_needed()

def on_magnifier_patch_ready(presenter, result):
    if not result:
        return
    try:
        magnifier_patch_pil, mag_pos_on_image, task_id, used_coords = result
        if task_id < presenter._last_displayed_task_id:
            return
        presenter._last_displayed_task_id = task_id
        if not magnifier_patch_pil or not mag_pos_on_image:
            return

        from shared.image_processing.qt_conversion import pil_to_qpixmap_optimized

        magnifier_pixmap = pil_to_qpixmap_optimized(magnifier_patch_pil, copy=False)
        if magnifier_pixmap.isNull():
            return

        presenter.view.sync_widget_overlay_coords()
        label_w, label_h = presenter.get_current_label_dimensions()
        pix_w, pix_h = presenter.store.viewport.geometry_state.pixmap_width, presenter.store.viewport.geometry_state.pixmap_height
        offset_x = (label_w - pix_w) // 2
        offset_y = (label_h - pix_h) // 2
        mag_pos_on_label = QPoint(offset_x + mag_pos_on_image.x(), offset_y + mag_pos_on_image.y())

        if hasattr(presenter.ui.image_label, "set_magnifier_content"):
            presenter.ui.image_label.set_magnifier_content(magnifier_pixmap, mag_pos_on_label)
        elif hasattr(presenter.ui.image_label, "update_magnifier"):
            presenter.ui.image_label.update_magnifier(magnifier_pixmap, mag_pos_on_label)
        else:
            presenter.view.set_image_layers(
                presenter._cached_base_pixmap, magnifier_pixmap, mag_pos_on_label, used_coords
            )
    except Exception as exc:
        logger.error(f"Error displaying magnifier patch: {exc}", exc_info=True)

def update_widget_capture_area_geometry(presenter, magnifier_coords, w, h):
    presenter.view.sync_widget_overlay_coords()

def stop_interactive_movement(presenter, log_gate):
    presenter.store.viewport.interaction_state.is_interactive_mode = False
    presenter._cached_split_pos = -1.0
    presenter._last_mag_signature = None

    if not presenter.store.viewport.view_state.use_magnifier:
        if presenter.view.is_gl_canvas():
            if hasattr(presenter.ui.image_label, "clear_magnifier_gpu"):
                presenter.ui.image_label.clear_magnifier_gpu()
            if hasattr(presenter.ui.image_label, "set_magnifier_content"):
                presenter.ui.image_label.set_magnifier_content(None, None)
            if hasattr(presenter.ui.image_label, "set_overlay_coords"):
                presenter.ui.image_label.set_overlay_coords(None, 0, [], 0)
            if hasattr(presenter.ui.image_label, "set_capture_area"):
                presenter.ui.image_label.set_capture_area(None, 0)
        else:
            presenter.view.sync_widget_overlay_coords()
    else:
        presenter.view.sync_widget_overlay_coords()
    presenter.schedule_update()

def update_capture_area_display(presenter):
    if presenter.store.viewport.view_state.use_magnifier:
        presenter.view.sync_widget_overlay_coords()
