from typing import Callable, Tuple, Union
from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QPointF, QRect
from services.state_manager import AppState
import logging
import sys
import os

logger = logging.getLogger("ImproveImgSLI")

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    return os.path.join(base_path, relative_path)

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]
TRUNCATE_TEXT_DEBUG_VERBOSE = False


def _find_longest_fit_core(raw_text: str, available_width: int, max_chars_for_base: int, ellipsis_symbol: str,
                           font_instance: FontType, get_size_func: GetSizeFuncType, original_raw_text_for_debug: str) -> Union[str, None]:
    best_fittable_text = None
    low = 0
    high = max_chars_for_base
    if max_chars_for_base == 0 and ellipsis_symbol:
        try:
            processed_text = ellipsis_symbol
            text_w, text_h = get_size_func(processed_text, font_instance)
            if text_w <= available_width:
                return processed_text
            else:
                return None
        except Exception:
            return None
    while low <= high:
        mid_base_len = (low + high) // 2
        current_base_text = raw_text[:mid_base_len]
        processed_text = current_base_text + ellipsis_symbol
        try:
            text_w, text_h = get_size_func(processed_text, font_instance)
            if text_w <= available_width:
                best_fittable_text = processed_text
                low = mid_base_len + 1
            else:
                high = mid_base_len - 1
        except Exception:
            high = mid_base_len - 1
    return best_fittable_text


def truncate_text(raw_text: str, available_width: int, max_len: int,
                  font_instance: FontType, get_size_func: GetSizeFuncType) -> str:
    original_len = len(raw_text)
    max_len = max(0, max_len)
    if original_len == 0:
        return ''
    if original_len <= max_len:
        try:
            text_w, _ = get_size_func(raw_text, font_instance)
            if text_w <= available_width:
                return raw_text
        except Exception:
            pass
    ellipsis_options = ['...', '..', '.']
    for ellipsis in ellipsis_options:
        if max_len < len(ellipsis):
            continue
        max_chars_for_base = min(original_len, max_len - len(ellipsis))
        fittable_text = _find_longest_fit_core(
            raw_text,
            available_width,
            max_chars_for_base,
            ellipsis,
            font_instance,
            get_size_func,
            raw_text)
        if fittable_text is not None:
            return fittable_text
    max_chars_for_base_no_ellipsis = min(original_len, max_len)
    fittable_text_no_ellipsis = _find_longest_fit_core(
        raw_text,
        available_width,
        max_chars_for_base_no_ellipsis,
        '',
        font_instance,
        get_size_func,
        raw_text)
    if fittable_text_no_ellipsis is not None:
        return fittable_text_no_ellipsis
    return ''


def get_scaled_pixmap_dimensions(
        source_image_pil: Image.Image, label_width: int, label_height: int) -> Tuple[int, int]:
    if not source_image_pil or not hasattr(source_image_pil, 'size'):
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
    drawing_width: int, drawing_height: int,
    container_width: int | None = None, container_height: int | None = None,
) -> Tuple[QPoint | None, QPoint | None, int, int, QPoint | None, int, int, QRect]:
    empty_result = (None, None, 0, 0, None, 0, 0, QRect())
    if not app_state.original_image1 or not app_state.original_image2:
        return empty_result

    try:
        orig1_width, orig1_height = app_state.original_image1.size
        orig2_width, orig2_height = app_state.original_image2.size
    except Exception:
        return empty_result

    raw_rel_x = app_state.capture_position_relative.x()
    raw_rel_y = app_state.capture_position_relative.y()

    orig1_ref_dim = min(orig1_width, orig1_height)
    orig2_ref_dim = min(orig2_width, orig2_height)
    capture_size_orig1 = max(
        10, int(
            round(
                app_state.capture_size_relative * orig1_ref_dim)))
    capture_size_orig2 = max(
        10, int(
            round(
                app_state.capture_size_relative * orig2_ref_dim)))
    cap_radius1 = capture_size_orig1 // 2
    cap_radius2 = capture_size_orig2 // 2

    raw_center_x1 = raw_rel_x * orig1_width
    raw_center_y1 = raw_rel_y * orig1_height
    raw_center_x2 = raw_rel_x * orig2_width
    raw_center_y2 = raw_rel_y * orig2_height

    clamped_center_x1 = max(cap_radius1, min(
        raw_center_x1, orig1_width - cap_radius1))
    clamped_center_y1 = max(cap_radius1, min(
        raw_center_y1, orig1_height - cap_radius1))
    clamped_center_x2 = max(cap_radius2, min(
        raw_center_x2, orig2_width - cap_radius2))
    clamped_center_y2 = max(cap_radius2, min(
        raw_center_y2, orig2_height - cap_radius2))

    capture_center_orig1 = QPoint(
        int(round(clamped_center_x1)), int(round(clamped_center_y1)))
    capture_center_orig2 = QPoint(
        int(round(clamped_center_x2)), int(round(clamped_center_y2)))

    final_rel_x = ((clamped_center_x1 / orig1_width) + (clamped_center_x2 /
                   orig2_width)) / 2 if orig1_width > 0 and orig2_width > 0 else 0
    final_rel_y = ((clamped_center_y1 / orig1_height) + (clamped_center_y2 /
                   orig2_height)) / 2 if orig1_height > 0 and orig2_height > 0 else 0
    
    magnifier_midpoint_on_image = QPoint()
    magnifier_bbox_on_image = QRect()
    magnifier_size_pixels = 0
    edge_spacing_pixels = 0
    
    use_container_dims = container_width is not None and container_height is not None

    if app_state.use_magnifier:
        target_max_dim_drawing = float(max(drawing_width, drawing_height))
        magnifier_size_pixels = max(
            10, int(round(app_state.magnifier_size_relative * target_max_dim_drawing)))
        edge_spacing_pixels = max(
            0, int(
                round(
                    app_state.magnifier_spacing_relative_visual * target_max_dim_drawing)))

        if app_state.freeze_magnifier and app_state.frozen_magnifier_absolute_pos:
            magnifier_midpoint_on_image = app_state.frozen_magnifier_absolute_pos
            
        else:
            capture_marker_center_on_screen = QPointF(
                final_rel_x * drawing_width,
                final_rel_y * drawing_height
            )
            offset_relative = app_state.magnifier_offset_relative_visual
            offset_pixels_x = offset_relative.x() * target_max_dim_drawing
            offset_pixels_y = offset_relative.y() * target_max_dim_drawing
            
            magnifier_midpoint_on_image = QPoint(
                int(round(capture_marker_center_on_screen.x() + offset_pixels_x)),
                int(round(capture_marker_center_on_screen.y() + offset_pixels_y))
            )
        
        radius = magnifier_size_pixels / 2.0
        if edge_spacing_pixels < 1.0:
            magnifier_bbox_on_image = QRect(
                int(magnifier_midpoint_on_image.x() - radius),
                int(magnifier_midpoint_on_image.y() - radius),
                magnifier_size_pixels,
                magnifier_size_pixels
            )
        else:
            total_width = magnifier_size_pixels * 2 + edge_spacing_pixels
            left_edge = int(
                magnifier_midpoint_on_image.x() -
                total_width /
                2.0)
            top_edge = int(magnifier_midpoint_on_image.y() - radius)
            magnifier_bbox_on_image = QRect(
                left_edge, top_edge,
                int(total_width), magnifier_size_pixels
            )

    return (
        capture_center_orig1, capture_center_orig2,
        capture_size_orig1, capture_size_orig2,
        magnifier_midpoint_on_image,
        magnifier_size_pixels,
        edge_spacing_pixels,
        magnifier_bbox_on_image
    )