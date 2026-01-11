import sys
from pathlib import Path
from typing import Callable, Tuple, Union

from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QPointF, QRect

from core.store import Store

MIN_CAPTURE_THICKNESS = 2.0

def resource_path(relative_path: str) -> str:
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:

        current_file = Path(__file__).resolve()
        base_path = current_file.parent.parent
    return (base_path / relative_path).as_posix()

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]

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
    store: Store,
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

    full_res_img1 = store.document.full_res_image1 or store.document.original_image1
    full_res_img2 = store.document.full_res_image2 or store.document.original_image2

    if not full_res_img1 or not full_res_img2:
        return empty_result

    unified_width, unified_height = drawing_width, drawing_height
    full1_width, full1_height = full_res_img1.size
    full2_width, full2_height = full_res_img2.size

    if not all([
        unified_width > 0, unified_height > 0,
        full1_width > 0, full1_height > 0,
        full2_width > 0, full2_height > 0,
    ]):
        return empty_result

    unified_ref_dim = min(unified_width, unified_height)
    capture_size_on_unified = store.viewport.capture_size_relative * unified_ref_dim

    drawing_ref_dim = max(1, min(drawing_width, drawing_height))
    thickness_on_unified = max(int(MIN_CAPTURE_THICKNESS), int(round(drawing_ref_dim * 0.003)))

    inner_capture_size_on_unified = capture_size_on_unified - thickness_on_unified
    if inner_capture_size_on_unified <= 0:
        inner_capture_size_on_unified = max(1, int(round(capture_size_on_unified - thickness_on_unified))) or 1

    radius_rel_x = (capture_size_on_unified / 2.0) / unified_width if unified_width > 0 else 0.0
    radius_rel_y = (capture_size_on_unified / 2.0) / unified_height if unified_height > 0 else 0.0

    raw_pos = store.viewport.capture_position_relative

    eff_rel_x = max(radius_rel_x, min(raw_pos.x(), 1.0 - radius_rel_x))
    eff_rel_y = max(radius_rel_y, min(raw_pos.y(), 1.0 - radius_rel_y))

    capture_center_full1_x = eff_rel_x * full1_width
    capture_center_full1_y = eff_rel_y * full1_height

    capture_center_full2_x = eff_rel_x * full2_width
    capture_center_full2_y = eff_rel_y * full2_height

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

    crop_box1 = (left1, top1, left1 + crop_width1, top1 + crop_height1)
    crop_box2 = (left2, top2, left2 + crop_width2, top2 + crop_height2)

    magnifier_midpoint_on_image = QPoint()
    magnifier_bbox_on_image = QRect()
    magnifier_size_pixels = 0
    edge_spacing_pixels = 0

    if store.viewport.use_magnifier:
        target_max_dim_drawing = float(max(drawing_width, drawing_height))
        magnifier_size_pixels = max(10, int(round(store.viewport.magnifier_size_relative * target_max_dim_drawing)))

        edge_spacing_pixels = max(
            0,
            int(round(store.viewport.magnifier_spacing_relative_visual * target_max_dim_drawing))
        )

        if store.viewport.freeze_magnifier:
            base_pos = store.viewport.frozen_capture_point_relative
        else:
            base_pos = QPointF(eff_rel_x, eff_rel_y)

        offset_visual = store.viewport.magnifier_offset_relative_visual

        mid_x = int(round(base_pos.x() * drawing_width + offset_visual.x() * target_max_dim_drawing))
        mid_y = int(round(base_pos.y() * drawing_height + offset_visual.y() * target_max_dim_drawing))
        magnifier_midpoint_on_image = QPoint(mid_x, mid_y)

        r = magnifier_size_pixels // 2

        rect_center = QRect(mid_x - r, mid_y - r, magnifier_size_pixels, magnifier_size_pixels)
        magnifier_bbox_on_image = rect_center

        is_visual_diff = store.viewport.diff_mode in ('highlight', 'grayscale', 'ssim', 'edges')

        if is_visual_diff:
            show_left = getattr(store.viewport, "magnifier_visible_left", True)
            show_right = getattr(store.viewport, "magnifier_visible_right", True)

            if store.viewport.is_magnifier_combined:

                shift = magnifier_size_pixels + 8
                if not store.viewport.is_horizontal:

                    rect_combined = QRect(mid_x - r, mid_y + shift - r, magnifier_size_pixels, magnifier_size_pixels)
                else:

                    rect_combined = QRect(mid_x + shift - r, mid_y - r, magnifier_size_pixels, magnifier_size_pixels)

                magnifier_bbox_on_image = rect_center.united(rect_combined)

            else:
                spacing_f = float(edge_spacing_pixels)
                offset_dist = max(magnifier_size_pixels, magnifier_size_pixels + spacing_f)

                if not store.viewport.is_horizontal:

                    center_left = QPoint(int(round(mid_x - offset_dist)), int(round(mid_y)))
                    center_right = QPoint(int(round(mid_x + offset_dist)), int(round(mid_y)))
                else:

                    center_left = QPoint(int(round(mid_x)), int(round(mid_y - offset_dist)))
                    center_right = QPoint(int(round(mid_x)), int(round(mid_y + offset_dist)))

                rect_left = QRect(center_left.x() - r, center_left.y() - r, magnifier_size_pixels, magnifier_size_pixels)
                rect_right = QRect(center_right.x() - r, center_right.y() - r, magnifier_size_pixels, magnifier_size_pixels)

                if show_left:
                    magnifier_bbox_on_image = magnifier_bbox_on_image.united(rect_left)
                if show_right:
                    magnifier_bbox_on_image = magnifier_bbox_on_image.united(rect_right)

        else:
            if store.viewport.is_magnifier_combined:

                magnifier_bbox_on_image = rect_center
            else:

                dist = r + int(round(edge_spacing_pixels / 2.0))

                if not store.viewport.magnifier_is_horizontal:
                    rect1 = QRect(mid_x - dist - r, mid_y - r, magnifier_size_pixels, magnifier_size_pixels)
                    rect2 = QRect(mid_x + dist - r, mid_y - r, magnifier_size_pixels, magnifier_size_pixels)
                else:
                    rect1 = QRect(mid_x - r, mid_y - dist - r, magnifier_size_pixels, magnifier_size_pixels)
                    rect2 = QRect(mid_x - r, mid_y + dist - r, magnifier_size_pixels, magnifier_size_pixels)

                magnifier_bbox_on_image = rect1.united(rect2)

    return (
        crop_box1,
        crop_box2,
        magnifier_midpoint_on_image,
        magnifier_size_pixels,
        edge_spacing_pixels,
        magnifier_bbox_on_image,
    )
