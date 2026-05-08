import math
from dataclasses import replace

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor

from ui.canvas_features.magnifier import (
    DEFAULT_MAGNIFIER_ID,
    compute_magnifier_padding,
    iter_magnifier_models,
)
from ui.canvas_features.magnifier.store import active_magnifier_id

def clamp_capture_position(
    rel_x: float, rel_y: float, width: int, height: int, capture_size: float
):
    radius_x = (capture_size * min(width, height) / 2.0) / max(1.0, float(width))
    radius_y = (capture_size * min(width, height) / 2.0) / max(1.0, float(height))
    return (
        max(radius_x, min(rel_x, 1.0 - radius_x)),
        max(radius_y, min(rel_y, 1.0 - radius_y)),
    )

def compute_canvas_plan(store, image_width: int, image_height: int, magnifier_drawing_coords=None) -> dict:
    pad_left, pad_right, pad_top, pad_bottom = compute_magnifier_padding(
        store,
        drawing_width=image_width,
        drawing_height=image_height,
    )

    return {
        "image_width": image_width,
        "image_height": image_height,
        "canvas_width": image_width + pad_left + pad_right,
        "canvas_height": image_height + pad_top + pad_bottom,
        "padding_left": pad_left,
        "padding_top": pad_top,
        "padding_right": pad_right,
        "padding_bottom": pad_bottom,
        "magnifier_coords": magnifier_drawing_coords,
    }

def scale_export_stroke(value: int, scale: float) -> int:
    if value <= 0:
        return 0
    return max(1, int(round(float(value) * max(1.0, float(scale)))))

def compute_export_stroke_scales(
    viewport_state: dict | None, width: int, height: int
) -> tuple[float, float, float]:
    if not viewport_state:
        return 1.0, 1.0, 1.0
    display_w = max(1, int(viewport_state.get("pixmap_width", 0) or 0))
    display_h = max(1, int(viewport_state.get("pixmap_height", 0) or 0))
    scale_x = float(width) / float(display_w) if display_w > 0 else 1.0
    scale_y = float(height) / float(display_h) if display_h > 0 else 1.0
    return scale_x, scale_y, min(scale_x, scale_y)

def build_export_magnifier_layout(
    vp,
    *,
    width: int,
    height: int,
    canvas_width: int,
    canvas_height: int,
    content_offset_x: float = 0.0,
    content_offset_y: float = 0.0,
    divider_thickness_px: int,
    render_scale: float = 1.0,
):
    view = vp.view_state
    render = vp.render_config
    visible_models = [model for model in iter_magnifier_models(view, render) if model.visible]
    if not visible_models:
        return {
            "slots": [],
            "magnifier_centers": [],
            "capture_center": None,
            "capture_radius": 0.0,
            "mag_radius": 0.0,
            "channel_mode_int": {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(view.channel_view_mode, 0),
            "interp_mode_int": {
                "NEAREST": 0,
                "BILINEAR": 1,
                "BICUBIC": 2,
                "LANCZOS": 3,
                "EWA_LANCZOS": 4,
            }.get(str(render.interpolation_method or "BILINEAR").upper(), 1),
            "diff_mode_int": 0,
        }

    diff_mode = str(view.diff_mode or "off")
    diff_enabled = diff_mode in ("highlight", "grayscale", "ssim", "edges")
    target_max = float(max(width, height))
    active_id = active_magnifier_id(view) or DEFAULT_MAGNIFIER_ID
    active_model = next((model for model in visible_models if model.id == active_id), visible_models[0])

    def _capture_geometry(model):
        cap_x, cap_y = clamp_capture_position(
            model.position.x,
            model.position.y,
            width,
            height,
            model.capture_size_relative,
        )
        capture_ref = float(min(width, height))
        center_x = float(content_offset_x) + (cap_x * width)
        center_y = float(content_offset_y) + (cap_y * height)
        radius = (model.capture_size_relative * capture_ref) / 2.0
        uv_half_w = (model.capture_size_relative * capture_ref / 2.0) / max(1.0, float(canvas_width))
        uv_half_h = (model.capture_size_relative * capture_ref / 2.0) / max(1.0, float(canvas_height))
        return cap_x, cap_y, center_x, center_y, radius, uv_half_w, uv_half_h

    _active_cap_x, _active_cap_y, active_center_x, active_center_y, active_capture_radius, _, _ = _capture_geometry(active_model)

    def _make_slot(model, center_xy, source, radius, uv_rect, *, is_combined=False):
        local_x = center_xy[0] / render_scale
        local_y = center_xy[1] / render_scale
        local_radius = radius / render_scale
        local_mag_px = max(1.0, local_radius * 2.0)
        return {
            "center": QPointF(local_x, local_y),
            "radius": local_radius,
            "uv_rect": uv_rect,
            "uv_rect2": uv_rect,
            "source": source,
            "is_combined": is_combined,
            "internal_split": model.internal_split,
            "horizontal": model.is_horizontal,
            "divider_visible": model.divider_visible,
            "divider_color": (
                model.divider_color.r / 255.0,
                model.divider_color.g / 255.0,
                model.divider_color.b / 255.0,
                model.divider_color.a / 255.0,
            ),
            "divider_thickness_px": divider_thickness_px,
            "divider_thickness_uv": (divider_thickness_px / local_mag_px) * 0.5,
            "border_color": QColor(
                model.border_color.r,
                model.border_color.g,
                model.border_color.b,
                model.border_color.a,
            ),
            "border_width": float(getattr(model, "border_thickness", 2)),
        }

    slots = []
    magnifier_centers = []
    capture_circles = []
    guide_sets = []
    mag_radius = 0.0
    for model in visible_models:
        _cap_x, _cap_y, cap_center_x, cap_center_y, _cap_radius, uv_half_w, uv_half_h = _capture_geometry(model)
        capture_circles.append(
            (
                QPointF(cap_center_x / render_scale, cap_center_y / render_scale),
                _cap_radius / render_scale,
                QColor(
                    model.capture_ring_color.r,
                    model.capture_ring_color.g,
                    model.capture_ring_color.b,
                    model.capture_ring_color.a,
                ),
            )
        )
        uv_rect = (
            (cap_center_x / canvas_width) - uv_half_w,
            (cap_center_y / canvas_height) - uv_half_h,
            (cap_center_x / canvas_width) + uv_half_w,
            (cap_center_y / canvas_height) + uv_half_h,
        )
        radius = (model.size_relative * target_max) / 2.0
        mag_radius = max(mag_radius, radius)
        spacing_px = model.spacing_relative * target_max
        if model.freeze and model.frozen_position is not None:
            frozen_x, frozen_y = clamp_capture_position(
                model.frozen_position.x,
                model.frozen_position.y,
                width,
                height,
                model.capture_size_relative,
            )
            base_x = float(content_offset_x) + (frozen_x * width)
            base_y = float(content_offset_y) + (frozen_y * height)
        else:
            base_x = cap_center_x
            base_y = cap_center_y
        cx = base_x + (model.offset_relative.x * target_max)
        cy = base_y + (model.offset_relative.y * target_max)
        show_left = bool(model.visible_left)
        show_right = bool(model.visible_right)
        show_center = bool(model.visible_center)
        render_visual_diff = diff_enabled and show_center
        is_combined = show_left and show_right and float(model.spacing_relative) <= 0.02 + 1e-5

        if is_combined:
            if render_visual_diff:
                if not model.is_horizontal:
                    diff_center = (cx, cy - radius - 4.0)
                    comb_center = (cx, cy + radius + 4.0)
                else:
                    diff_center = (cx - radius - 4.0, cy)
                    comb_center = (cx + radius + 4.0, cy)
                if show_center:
                    slots.append(_make_slot(model, diff_center, 2, radius, uv_rect))
                    magnifier_centers.append(diff_center)
                if show_left and show_right:
                    slots.append(_make_slot(model, comb_center, 0, radius, uv_rect, is_combined=True))
                    magnifier_centers.append(comb_center)
                elif show_left:
                    slots.append(_make_slot(model, comb_center, 0, radius, uv_rect))
                    magnifier_centers.append(comb_center)
                elif show_right:
                    slots.append(_make_slot(model, comb_center, 1, radius, uv_rect))
                    magnifier_centers.append(comb_center)
            else:
                center = (cx, cy)
                if show_left and show_right:
                    slots.append(_make_slot(model, center, 0, radius, uv_rect, is_combined=True))
                    magnifier_centers.append(center)
                elif show_left:
                    slots.append(_make_slot(model, center, 0, radius, uv_rect))
                    magnifier_centers.append(center)
                elif show_right:
                    slots.append(_make_slot(model, center, 1, radius, uv_rect))
                    magnifier_centers.append(center)
        elif render_visual_diff:
            offset_3 = max(radius * 2.0, radius * 2.0 + spacing_px)
            if not model.is_horizontal:
                left_center = (cx - offset_3, cy)
                right_center = (cx + offset_3, cy)
            else:
                left_center = (cx, cy - offset_3)
                right_center = (cx, cy + offset_3)
            if show_left:
                slots.append(_make_slot(model, left_center, 0, radius, uv_rect))
                magnifier_centers.append(left_center)
            if show_right:
                slots.append(_make_slot(model, right_center, 1, radius, uv_rect))
                magnifier_centers.append(right_center)
            if show_center:
                center = (cx, cy)
                slots.append(_make_slot(model, center, 2, radius, uv_rect))
                magnifier_centers.append(center)
        else:
            dist = radius + (spacing_px / 2.0)
            if not model.is_horizontal:
                left_center = (cx - dist, cy)
                right_center = (cx + dist, cy)
            else:
                left_center = (cx, cy - dist)
                right_center = (cx, cy + dist)
            if show_left and show_right:
                slots.append(_make_slot(model, left_center, 0, radius, uv_rect))
                slots.append(_make_slot(model, right_center, 1, radius, uv_rect))
                magnifier_centers.extend([left_center, right_center])
            elif show_left:
                center = (cx, cy)
                slots.append(_make_slot(model, center, 0, radius, uv_rect))
                magnifier_centers.append(center)
            elif show_right:
                center = (cx, cy)
                slots.append(_make_slot(model, center, 1, radius, uv_rect))
                magnifier_centers.append(center)

        local_target_centers = []
        if is_combined:
            if render_visual_diff:
                if show_center:
                    local_target_centers.append(diff_center)
                if show_left or show_right:
                    local_target_centers.append(comb_center)
            else:
                if show_left or show_right:
                    local_target_centers.append((cx, cy))
        elif render_visual_diff:
            if show_left:
                local_target_centers.append(left_center)
            if show_center:
                local_target_centers.append((cx, cy))
            if show_right:
                local_target_centers.append(right_center)
        else:
            if show_left and show_right:
                local_target_centers.extend([left_center, right_center])
            elif show_left:
                local_target_centers.append((cx, cy))
            elif show_right:
                local_target_centers.append((cx, cy))
        if local_target_centers:
            guide_sets.append(
                (
                    QPointF(cap_center_x / render_scale, cap_center_y / render_scale),
                    _cap_radius / render_scale,
                    [QPointF(x / render_scale, y / render_scale) for x, y in local_target_centers],
                    radius / render_scale,
                    QColor(
                        model.laser_color.r,
                        model.laser_color.g,
                        model.laser_color.b,
                        model.laser_color.a,
                    ),
                )
            )

    result = {
        "slots": slots,
        "magnifier_centers": magnifier_centers,
        "capture_circles": capture_circles,
        "guide_sets": guide_sets,
        "capture_center": QPointF(active_center_x / render_scale, active_center_y / render_scale),
        "capture_radius": active_capture_radius / render_scale,
        "mag_radius": mag_radius / render_scale,
        "channel_mode_int": {"RGB": 0, "R": 1, "G": 2, "B": 3, "L": 4}.get(view.channel_view_mode, 0),
        "interp_mode_int": {
            "NEAREST": 0,
            "BILINEAR": 1,
            "BICUBIC": 2,
            "LANCZOS": 3,
            "EWA_LANCZOS": 4,
        }.get(str(render.interpolation_method or "BILINEAR").upper(), 1),
        "diff_mode_int": 4 if diff_mode == "ssim" else {"off": 0, "highlight": 1, "grayscale": 2, "edges": 3, "ssim": 4}.get(diff_mode, 0),
    }
    return result
