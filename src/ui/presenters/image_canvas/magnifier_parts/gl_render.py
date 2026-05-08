import logging

from PyQt6.QtCore import QPointF
from domain.qt_adapters import color_to_qcolor
from ui.canvas_infra.scene.apply import apply_scene_to_canvas
from ui.canvas_infra.scene.builder import build_canvas_scene
from ui.canvas_features.magnifier.scene_objects import MagnifierSceneObject
from ui.canvas_features.magnifier.store import active_or_default_border_color

from .common import (
    get_active_magnifier_model,
    get_effective_main_interpolation_method,
    get_live_image_label,
    is_effective_magnifier_interactive,
)
from .diff_cache import ensure_cached_diff_image

logger = logging.getLogger("ImproveImgSLI")

def _build_and_apply_scene_snapshot(presenter, image_label, geometry):
    label_width, label_height = presenter.get_current_label_dimensions()
    scene = build_canvas_scene(
        presenter.store,
        image_label=image_label,
        label_width=label_width,
        label_height=label_height,
    )
    runtime_state = getattr(image_label, "runtime_state", None)
    if runtime_state is not None:
        runtime_state._canvas_scene_graph = scene
    apply_scene_to_canvas(
        scene,
        image_label,
        geometry,
        use_quick_overlay=False,
    )
    return scene

def sync_widget_overlay_coords(presenter):
    geometry = presenter.store.viewport.geometry_state
    image_label = get_live_image_label(presenter)
    if image_label is None:
        return
    _build_and_apply_scene_snapshot(presenter, image_label, geometry)

def _circle_source(role: str) -> int:
    if role in ("center", "diff"):
        return 2
    if role == "right":
        return 1
    return 0

def _uv_rect_from_object(obj: MagnifierSceneObject, bounds) -> tuple[float, float, float, float]:
    pix_w = max(1.0, float(bounds.w))
    pix_h = max(1.0, float(bounds.h))
    cap_x = float(obj.source_position.x)
    cap_y = float(obj.source_position.y)
    radius = max(0.0, float(obj.source_radius))
    cap_half_u = radius / pix_w
    cap_half_v = radius / pix_h
    return (
        cap_x - cap_half_u,
        cap_y - cap_half_v,
        cap_x + cap_half_u,
        cap_y + cap_half_v,
    )

def render_magnifier_gl_fast(presenter):
    vp = presenter.store.viewport
    geometry = vp.geometry_state
    session = vp.session_data
    image_label = get_live_image_label(presenter)
    if image_label is None:
        return
    if get_active_magnifier_model(presenter) is None:
        image_label.clear_magnifier_gpu()
        return
    image_label.begin_update_batch()
    try:
        source_ready = getattr(image_label, "_source_images_ready", False)

        scene = _build_and_apply_scene_snapshot(presenter, image_label, geometry)

        tex_img1 = None
        tex_img2 = None
        if source_ready:
            source_pil_images = getattr(image_label, "_source_pil_images", ())
            if len(source_pil_images) >= 2:
                tex_img1, tex_img2 = source_pil_images[:2]
        else:
            stored_pil_images = getattr(image_label, "_stored_pil_images", ())
            if len(stored_pil_images) >= 2:
                tex_img1, tex_img2 = stored_pil_images[:2]
        tex_img1 = tex_img1 or session.render_cache.scaled_image1_for_display or session.image_state.image1
        tex_img2 = tex_img2 or session.render_cache.scaled_image2_for_display or session.image_state.image2
        if not tex_img1 or not tex_img2:
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

        effective_interactive = is_effective_magnifier_interactive(vp)

        channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
            getattr(vp.view_state, "channel_view_mode", "RGB"), 0
        )
        interp_key = (
            getattr(vp.render_config, "magnifier_movement_interpolation_method", "BILINEAR")
            if effective_interactive
            else get_effective_main_interpolation_method(vp)
        )
        interp_key = (interp_key or "BILINEAR").upper()
        interp_mode_int = {
            "NEAREST": 0,
            "BILINEAR": 1,
            "BICUBIC": 2,
            "LANCZOS": 3,
            "EWA_LANCZOS": 4,
        }.get(interp_key, 1)
        cached_diff_image = ensure_cached_diff_image(
            presenter,
            tex_img1,
            tex_img2,
            local_source1=local_diff_source1,
            local_source2=local_diff_source2,
        )
        current_uploaded_diff = getattr(image_label, "_diff_source_pil_image", None)
        diff_image_for_magnifier = cached_diff_image or current_uploaded_diff
        diff_mode_int = 4 if diff_mode_str == "ssim" and diff_image_for_magnifier is not None else 0

        if cached_diff_image is not None:
            image_label.upload_diff_source_pil_image(cached_diff_image)
        elif diff_mode_str not in ("highlight", "grayscale", "ssim", "edges"):
            image_label.upload_diff_source_pil_image(None)

        slots = []

        def make_slot(
            *,
            center,
            source,
            radius,
            uv_rect1,
            uv_rect2,
            magnifier,
            border_color,
            is_combined=False,
        ):
            div_color_t = (
                magnifier.divider_color.r / 255.0,
                magnifier.divider_color.g / 255.0,
                magnifier.divider_color.b / 255.0,
                magnifier.divider_color.a / 255.0,
            )
            mag_px_f = float(radius * 2.0)
            div_thickness_uv = (
                (magnifier.divider_thickness / mag_px_f) * 0.5 if mag_px_f > 0 else 0.005
            )
            return {
                "center": center,
                "radius": radius,
                "uv_rect": uv_rect1,
                "uv_rect2": uv_rect2,
                "source": source,
                "is_combined": is_combined,
                "internal_split": magnifier.internal_split,
                "horizontal": magnifier.is_horizontal,
                "divider_visible": magnifier.divider_visible,
                "divider_color": div_color_t,
                "divider_thickness_px": magnifier.divider_thickness,
                "divider_thickness_uv": div_thickness_uv,
                "border_color": border_color,
                "border_width": float(magnifier.border_thickness),
            }

        visible_magnifiers = [
            obj
            for obj in scene.iter_objects(kind="magnifier")
            if isinstance(obj, MagnifierSceneObject) and obj.visible
        ]
        if not visible_magnifiers:
            image_label.clear_magnifier_gpu()
            return
        for magnifier in visible_magnifiers:
            uv_rect = _uv_rect_from_object(magnifier, scene.bounds)
            for circle in magnifier.circles:
                if not circle.visible or circle.radius < 2:
                    continue
                source = _circle_source(circle.role)
                if source == 2 and diff_image_for_magnifier is None:
                    continue
                border_color = color_to_qcolor(magnifier.border_color)
                slots.append(
                    make_slot(
                        center=QPointF(circle.center.x, circle.center.y),
                        source=source,
                        radius=float(circle.radius),
                        uv_rect1=uv_rect,
                        uv_rect2=uv_rect,
                        magnifier=magnifier,
                        border_color=border_color,
                        is_combined=bool(magnifier.is_combined and circle.role == "combined"),
                    )
                )
        image_label.set_magnifier_gpu_params(
            slots,
            channel_mode_int,
            diff_mode_int,
            20.0 / 255.0,
            color_to_qcolor(active_or_default_border_color(vp.view_state)),
            2.0,
            interp_mode_int,
        )
    finally:
        image_label.end_update_batch()
        image_label._request_update()

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

    magnifier = get_active_magnifier_model(presenter)
    if magnifier is None:
        return

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
                    magnifier.position.x,
                    magnifier.position.y,
                    magnifier.capture_size_relative,
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
                is_interactive=is_effective_magnifier_interactive(vp),
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

    channel_mode_int = {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(
        getattr(vp.view_state, "channel_view_mode", "RGB"),
        0,
    )
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
