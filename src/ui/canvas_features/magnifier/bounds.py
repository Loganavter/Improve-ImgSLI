from __future__ import annotations
import math

from core.constants import AppConstants
from .store import iter_magnifier_models

def _clamp_capture_position(
    rel_x: float,
    rel_y: float,
    width: int,
    height: int,
    capture_size_relative: float,
) -> tuple[float, float]:
    capture_ref = float(min(width, height))
    radius_x = ((capture_size_relative * capture_ref) / 2.0) / max(1.0, float(width))
    radius_y = ((capture_size_relative * capture_ref) / 2.0) / max(1.0, float(height))
    return (
        max(radius_x, min(float(rel_x), 1.0 - radius_x)),
        max(radius_y, min(float(rel_y), 1.0 - radius_y)),
    )

def _union_rect(
    current: tuple[float, float, float, float] | None,
    rect: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if current is None:
        return rect
    return (
        min(current[0], rect[0]),
        min(current[1], rect[1]),
        max(current[2], rect[2]),
        max(current[3], rect[3]),
    )

def compute_magnifier_union_bbox(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
    content_offset_x: float = 0.0,
    content_offset_y: float = 0.0,
) -> tuple[float, float, float, float] | None:
    view = store.viewport.view_state
    render = store.viewport.render_config

    visible_models = [
        model for model in iter_magnifier_models(view, render) if bool(model.visible)
    ]
    if not visible_models or drawing_width <= 0 or drawing_height <= 0:
        return None

    diff_mode = str(getattr(view, "diff_mode", "off") or "off")
    diff_enabled = diff_mode in ("highlight", "grayscale", "ssim", "edges")
    combine_threshold = AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
    target_max = float(max(drawing_width, drawing_height))
    bounds: tuple[float, float, float, float] | None = None

    for model in visible_models:
        cap_x, cap_y = _clamp_capture_position(
            model.position.x,
            model.position.y,
            drawing_width,
            drawing_height,
            model.capture_size_relative,
        )
        if model.freeze and model.frozen_position is not None:
            frozen_x, frozen_y = _clamp_capture_position(
                model.frozen_position.x,
                model.frozen_position.y,
                drawing_width,
                drawing_height,
                model.capture_size_relative,
            )
            base_x = float(content_offset_x) + (frozen_x * drawing_width)
            base_y = float(content_offset_y) + (frozen_y * drawing_height)
        else:
            base_x = float(content_offset_x) + (cap_x * drawing_width)
            base_y = float(content_offset_y) + (cap_y * drawing_height)

        cx = base_x + (float(model.offset_relative.x) * target_max)
        cy = base_y + (float(model.offset_relative.y) * target_max)
        radius = (float(model.size_relative) * target_max) / 2.0
        spacing_px = float(model.spacing_relative) * target_max
        show_left = bool(model.visible_left)
        show_right = bool(model.visible_right)
        show_center = bool(model.visible_center)
        render_visual_diff = diff_enabled and show_center
        is_combined = (
            show_left
            and show_right
            and float(model.spacing_relative) <= combine_threshold + 1e-5
        )

        def add_circle(center_x: float, center_y: float) -> None:
            nonlocal bounds
            bounds = _union_rect(
                bounds,
                (
                    center_x - radius,
                    center_y - radius,
                    center_x + radius,
                    center_y + radius,
                ),
            )

        if is_combined:
            if render_visual_diff:
                if not model.is_horizontal:
                    diff_center = (cx, cy - radius - 4.0)
                    comb_center = (cx, cy + radius + 4.0)
                else:
                    diff_center = (cx - radius - 4.0, cy)
                    comb_center = (cx + radius + 4.0, cy)
                if show_center:
                    add_circle(*diff_center)
                if show_left and show_right:
                    add_circle(*comb_center)
                elif show_left or show_right:
                    add_circle(*comb_center)
            else:
                center = (cx, cy)
                if show_left or show_right or show_center:
                    add_circle(*center)
        elif render_visual_diff:
            offset_3 = max(radius * 2.0, radius * 2.0 + spacing_px)
            if not model.is_horizontal:
                left_center = (cx - offset_3, cy)
                right_center = (cx + offset_3, cy)
            else:
                left_center = (cx, cy - offset_3)
                right_center = (cx, cy + offset_3)
            if show_left:
                add_circle(*left_center)
            if show_right:
                add_circle(*right_center)
            if show_center:
                add_circle(cx, cy)
        else:
            dist = radius + (spacing_px / 2.0)
            if not model.is_horizontal:
                left_center = (cx - dist, cy)
                right_center = (cx + dist, cy)
            else:
                left_center = (cx, cy - dist)
                right_center = (cx, cy + dist)
            if show_left and show_right:
                add_circle(*left_center)
                add_circle(*right_center)
            elif show_left or show_right or show_center:
                add_circle(cx, cy)

    return bounds

def compute_magnifier_padding(
    store,
    *,
    drawing_width: int,
    drawing_height: int,
) -> tuple[int, int, int, int]:
    bbox = compute_magnifier_union_bbox(
        store,
        drawing_width=drawing_width,
        drawing_height=drawing_height,
    )
    if bbox is None:
        return (0, 0, 0, 0)

    left, top, right, bottom = bbox
    pad_left = max(0, int(math.ceil(-left)))
    pad_top = max(0, int(math.ceil(-top)))
    pad_right = max(0, int(math.ceil(right - drawing_width)))
    pad_bottom = max(0, int(math.ceil(bottom - drawing_height)))
    return (pad_left, pad_right, pad_top, pad_bottom)
