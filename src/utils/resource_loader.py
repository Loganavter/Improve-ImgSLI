import logging
import sys
from pathlib import Path
from typing import Callable, Tuple, Union

from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QPointF, QRect

from core.app_state import AppState
from core.constants import AppConstants

logger = logging.getLogger("ImproveImgSLI")

CAPTURE_THICKNESS_FACTOR = 0.1
MIN_CAPTURE_THICKNESS = 2.0
MAX_CAPTURE_THICKNESS = 8.0

def resource_path(relative_path: str) -> str:
    from shared_toolkit.utils.paths import resource_path as shared_resource_path
    return shared_resource_path(relative_path)

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]
TRUNCATE_TEXT_DEBUG_VERBOSE = False

def _find_longest_prefix(
    text_to_fit: str,
    max_available_width: int,
    max_chars_limit: int,
    font_instance: FontType,
    get_size_func: GetSizeFuncType,
) -> Union[str, None]:
    best_fit = None
    low = 0
    high = min(len(text_to_fit), max_chars_limit)

    while low <= high:
        mid = (low + high) // 2
        prefix = text_to_fit[:mid]
        try:
            width, _ = get_size_func(prefix, font_instance)
            if width <= max_available_width:
                best_fit = prefix
                low = mid + 1
            else:
                high = mid - 1
        except Exception:
            high = mid - 1

    return best_fit

def truncate_text(
    raw_text: str,
    available_width: int,
    max_len: int,
    font_instance: FontType,
    get_size_func: GetSizeFuncType,
) -> str:
    if not raw_text or available_width <= 5:
        return ""

    if len(raw_text) <= max_len:
        try:
            text_w, _ = get_size_func(raw_text, font_instance)
            if text_w <= available_width:
                return raw_text
        except Exception:
            pass

    for ellipsis in ["...", "..", "."]:
        if max_len < len(ellipsis):
            continue

        try:
            ellipsis_width, _ = get_size_func(ellipsis, font_instance)

            if ellipsis_width > available_width:
                continue

            available_width_for_text = available_width - ellipsis_width
            max_chars_for_text = max_len - len(ellipsis)

            base_text = _find_longest_prefix(
                raw_text,
                available_width_for_text,
                max_chars_for_text,
                font_instance,
                get_size_func
            )

            if base_text is not None:
                return base_text + ellipsis
        except Exception:
            continue

    final_attempt_text = _find_longest_prefix(
        raw_text,
        available_width,
        max_len,
        font_instance,
        get_size_func
    )

    return final_attempt_text or ""

def get_scaled_pixmap_dimensions(
    image1: Image.Image,
    image2: Image.Image,
    target_width: int,
    target_height: int,
) -> Tuple[int, int]:
    if not image1 or not image2:
        return target_width, target_height

    img1_w, img1_h = image1.size
    img2_w, img2_h = image2.size

    if img1_w <= 0 or img1_h <= 0 or img2_w <= 0 or img2_h <= 0:
        return target_width, target_height

    scale1 = min(target_width / img1_w, target_height / img1_h)
    scale2 = min(target_width / img2_w, target_height / img2_h)
    scale = min(scale1, scale2)

    scaled_w = int(round(img1_w * scale))
    scaled_h = int(round(img1_h * scale))

    return scaled_w, scaled_h

def get_magnifier_drawing_coords(
    app_state: AppState,
    drawing_width: int,
    drawing_height: int,
    container_width: int | None = None,
    container_height: int | None = None,
) -> Tuple[
    Tuple[float, float, float, float] | None,
    Tuple[float, float, float, float] | None,
    QPoint | None,
    int,
    int,
    QRect,
]:
    empty_result = (None, None, None, 0, 0, QRect())

    if not all([
        app_state.image1, app_state.image2
    ]):
        return empty_result

    full_res_img1 = app_state.full_res_image1 or app_state.original_image1
    full_res_img2 = app_state.full_res_image2 or app_state.original_image2

    if not full_res_img1 or not full_res_img2:
        return empty_result

    unified_width, unified_height = app_state.image1.size
    full1_width, full1_height = full_res_img1.size
    full2_width, full2_height = full_res_img2.size

    if not all([
        unified_width > 0, unified_height > 0,
        full1_width > 0, full1_height > 0,
        full2_width > 0, full2_height > 0,
    ]):
        return empty_result

    capture_center_full1_x = app_state.capture_position_relative.x() * full1_width
    capture_center_full1_y = app_state.capture_position_relative.y() * full1_height

    capture_center_full2_x = app_state.capture_position_relative.x() * full2_width
    capture_center_full2_y = app_state.capture_position_relative.y() * full2_height

    unified_ref_dim = min(unified_width, unified_height)
    capture_size_on_unified = app_state.capture_size_relative * unified_ref_dim

    drawing_ref_dim = max(1, min(drawing_width, drawing_height))
    thickness_display = max(int(MIN_CAPTURE_THICKNESS), int(round(drawing_ref_dim * 0.003)))
    unified_ref_dim = min(unified_width, unified_height)
    thickness_on_unified = int(round(thickness_display * (unified_ref_dim / drawing_ref_dim)))
    thickness_on_unified = max(1, thickness_on_unified)

    inner_capture_size_on_unified = capture_size_on_unified - thickness_on_unified
    if inner_capture_size_on_unified <= 0:
        inner_capture_size_on_unified = max(1, int(round(capture_size_on_unified - thickness_on_unified))) or 1

    capture_frac_w = inner_capture_size_on_unified / unified_width
    capture_frac_h = inner_capture_size_on_unified / unified_height

    crop_width1 = int(round(capture_frac_w * full1_width))
    crop_height1 = int(round(capture_frac_h * full1_height))
    crop_width2 = int(round(capture_frac_w * full2_width))
    crop_height2 = int(round(capture_frac_h * full2_height))

    if crop_width1 % 2 != 0: crop_width1 += 1
    if crop_height1 % 2 != 0: crop_height1 += 1
    if crop_width2 % 2 != 0: crop_width2 += 1
    if crop_height2 % 2 != 0: crop_height2 += 1

    left1 = int(round(capture_center_full1_x - crop_width1 / 2.0))
    top1 = int(round(capture_center_full1_y - crop_height1 / 2.0))
    left2 = int(round(capture_center_full2_x - crop_width2 / 2.0))
    top2 = int(round(capture_center_full2_y - crop_height2 / 2.0))

    crop_box1 = (
        left1,
        top1,
        left1 + crop_width1,
        top1 + crop_height1,
    )
    crop_box2 = (
        left2,
        top2,
        left2 + crop_width2,
        top2 + crop_height2,
    )

    magnifier_midpoint_on_image = QPoint()
    magnifier_bbox_on_image = QRect()
    magnifier_size_pixels = 0
    edge_spacing_pixels = 0

    if app_state.use_magnifier:
        target_max_dim_drawing = float(max(drawing_width, drawing_height))
        magnifier_size_pixels = max(
            10, int(round(app_state.magnifier_size_relative * target_max_dim_drawing))
        )
        edge_spacing_pixels = max(
            0,
            int(
                round(
                    app_state.magnifier_spacing_relative_visual * target_max_dim_drawing
                )
            ),
        )

        base_capture_pos_relative = (
            app_state.frozen_capture_point_relative
            if app_state.freeze_magnifier and app_state.frozen_capture_point_relative is not None
            else app_state.capture_position_relative
        )

        capture_marker_center_on_screen = QPointF(
            base_capture_pos_relative.x() * drawing_width,
            base_capture_pos_relative.y() * drawing_height,
        )
        offset_relative = app_state.magnifier_offset_relative_visual
        offset_pixels_x = offset_relative.x() * target_max_dim_drawing
        offset_pixels_y = offset_relative.y() * target_max_dim_drawing

        magnifier_midpoint_on_image = QPoint(
            int(round(capture_marker_center_on_screen.x() + offset_pixels_x)),
            int(round(capture_marker_center_on_screen.y() + offset_pixels_y)),
        )

        spacing_threshold = AppConstants.MIN_MAGNIFIER_SPACING_RELATIVE_FOR_COMBINE
        spacing_small = app_state.magnifier_spacing_relative_visual < spacing_threshold
        is_visual_diff = app_state.diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')
        both_halves = getattr(app_state, "magnifier_visible_left", True) and getattr(app_state, "magnifier_visible_right", True)
        show_left = getattr(app_state, "magnifier_visible_left", True)
        show_center = getattr(app_state, "magnifier_visible_center", True)
        show_right = getattr(app_state, "magnifier_visible_right", True)

        mid_x = magnifier_midpoint_on_image.x()
        mid_y = magnifier_midpoint_on_image.y()
        r = int(round(float(magnifier_size_pixels) / 2.0))

        centers: list[tuple[int, int]] = []

        if is_visual_diff and not spacing_small:

            offset = max(magnifier_size_pixels, magnifier_size_pixels + edge_spacing_pixels)
            if not app_state.is_horizontal:
                if show_left: centers.append((mid_x - offset, mid_y))
                if show_center: centers.append((mid_x, mid_y))
                if show_right: centers.append((mid_x + offset, mid_y))
            else:
                if show_left: centers.append((mid_x, mid_y - offset))
                if show_center: centers.append((mid_x, mid_y))
                if show_right: centers.append((mid_x, mid_y + offset))

        elif is_visual_diff and spacing_small:

            if show_center and both_halves:
                combined_offset = magnifier_size_pixels + 8
                centers.append((mid_x, mid_y))
                if not app_state.is_horizontal:
                    centers.append((mid_x, mid_y + combined_offset))
                else:
                    centers.append((mid_x + combined_offset, mid_y))
            else:

                offset = max(magnifier_size_pixels, magnifier_size_pixels + edge_spacing_pixels)
                if show_center: centers.append((mid_x, mid_y))
                if not app_state.is_horizontal:
                    if show_left: centers.append((mid_x - offset, mid_y))
                    if show_right: centers.append((mid_x + offset, mid_y))
                else:
                    if show_left: centers.append((mid_x, mid_y - offset))
                    if show_right: centers.append((mid_x, mid_y + offset))

        elif not is_visual_diff and spacing_small and both_halves:

            centers.append((mid_x, mid_y))

        else:

            offset_two = int(round(r + (edge_spacing_pixels / 2.0)))
            if not app_state.magnifier_is_horizontal:
                if show_left: centers.append((mid_x - offset_two, mid_y))
                if show_right: centers.append((mid_x + offset_two, mid_y))
            else:
                if show_left: centers.append((mid_x, mid_y - offset_two))
                if show_right: centers.append((mid_x, mid_y + offset_two))

            if len(centers) == 0:
                centers.append((mid_x, mid_y))

        if centers:
            if len(centers) == 1:
                cx, cy = centers[0]
                magnifier_bbox_on_image = QRect(int(cx - r), int(cy - r), magnifier_size_pixels, magnifier_size_pixels)
            else:
                left_edge = min(cx - r for cx, _ in centers)
                right_edge = max(cx + r for cx, _ in centers)
                top_edge = min(cy - r for _, cy in centers)
                bottom_edge = max(cy + r for _, cy in centers)
                magnifier_bbox_on_image = QRect(int(left_edge), int(top_edge), int(right_edge - left_edge), int(bottom_edge - top_edge))

    return (
        crop_box1,
        crop_box2,
        magnifier_midpoint_on_image,
        magnifier_size_pixels,
        edge_spacing_pixels,
        magnifier_bbox_on_image,
    )
