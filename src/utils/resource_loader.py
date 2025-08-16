from typing import Callable, Tuple, Union
import math
from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QPointF, QRect
from core.app_state import AppState
import logging
import sys
import os
from utils.paths import resource_path as _resolve_resource_path
from image_processing.drawing.magnifier_drawer import (
    CAPTURE_THICKNESS_FACTOR,
    MIN_CAPTURE_THICKNESS,
    MAX_CAPTURE_THICKNESS
)

logger = logging.getLogger("ImproveImgSLI")

def resource_path(relative_path: str) -> str:
    return _resolve_resource_path(relative_path)

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
    if final_attempt_text is not None:
        return final_attempt_text

    return ""

def get_scaled_pixmap_dimensions(
    source_image_pil: Image.Image, label_width: int, label_height: int
) -> Tuple[int, int]:
    if not source_image_pil or not hasattr(source_image_pil, "size"):
        return (0, 0)
    if label_width <= 0 or label_height <= 0:
        return (0, 0)
    try:
        orig_width, orig_height = source_image_pil.size
    except Exception:
        return (0, 0)
    if orig_height == 0 or orig_width == 0:
        return (0, 0)
    aspect_ratio = orig_width / orig_height
    label_aspect_ratio = label_width / label_height
    if aspect_ratio > label_aspect_ratio:
        scaled_width = label_width
        scaled_height = int(label_width / aspect_ratio)
    else:
        scaled_height = label_height
        scaled_width = int(label_height * aspect_ratio)
    scaled_width = max(1, scaled_width)
    scaled_height = max(1, scaled_height)
    return (scaled_width, scaled_height)

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

    crop_width1 = capture_frac_w * full1_width
    crop_height1 = capture_frac_h * full1_height
    crop_radius_w1 = crop_width1 / 2.0
    crop_radius_h1 = crop_height1 / 2.0

    crop_box1 = (
        capture_center_full1_x - crop_radius_w1,
        capture_center_full1_y - crop_radius_h1,
        capture_center_full1_x + crop_radius_w1,
        capture_center_full1_y + crop_radius_h1,
    )

    crop_width2 = capture_frac_w * full2_width
    crop_height2 = capture_frac_h * full2_height
    crop_radius_w2 = crop_width2 / 2.0
    crop_radius_h2 = crop_height2 / 2.0

    crop_box2 = (
        capture_center_full2_x - crop_radius_w2,
        capture_center_full2_y - crop_radius_h2,
        capture_center_full2_x + crop_radius_w2,
        capture_center_full2_y + crop_radius_h2,
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

        radius = magnifier_size_pixels / 2.0
        if edge_spacing_pixels < 1.0:
            magnifier_bbox_on_image = QRect(
                int(magnifier_midpoint_on_image.x() - radius),
                int(magnifier_midpoint_on_image.y() - radius),
                magnifier_size_pixels,
                magnifier_size_pixels,
            )
        else:
            total_width = magnifier_size_pixels * 2 + edge_spacing_pixels
            left_edge = int(magnifier_midpoint_on_image.x() - total_width / 2.0)
            top_edge = int(magnifier_midpoint_on_image.y() - radius)
            magnifier_bbox_on_image = QRect(
                left_edge, top_edge, int(total_width), magnifier_size_pixels
            )

    return (
        crop_box1,
        crop_box2,
        magnifier_midpoint_on_image,
        magnifier_size_pixels,
        edge_spacing_pixels,
        magnifier_bbox_on_image,
    )
