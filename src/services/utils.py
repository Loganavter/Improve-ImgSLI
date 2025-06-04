from typing import Callable, Tuple, Union
from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QPointF
from services.state_manager import AppState, AppConstants
FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]
TRUNCATE_TEXT_DEBUG_VERBOSE = False

def _find_longest_fit_core(raw_text: str, available_width: int, max_chars_for_base: int, ellipsis_symbol: str, font_instance: FontType, get_size_func: GetSizeFuncType, original_raw_text_for_debug: str) -> Union[str, None]:
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        print(f"[TT_CORE] ENTER: original='{original_raw_text_for_debug}', avail_w={available_width}, max_chars_base={max_chars_for_base}, ellipsis='{ellipsis_symbol}', font_size_attr={getattr(font_instance, 'size', 'N/A')}")
    best_fittable_text = None
    low = 0
    high = max_chars_for_base
    if max_chars_for_base == 0 and ellipsis_symbol:
        try:
            processed_text = ellipsis_symbol
            text_w, text_h = get_size_func(processed_text, font_instance)
            if TRUNCATE_TEXT_DEBUG_VERBOSE:
                print(f"[TT_CORE] QUICK_CHECK (base=0): '{processed_text}' -> width: {text_w} (avail: {available_width})")
            if text_w <= available_width:
                if TRUNCATE_TEXT_DEBUG_VERBOSE:
                    print(f"[TT_CORE] QUICK_CHECK EXIT (base=0): Returning '{processed_text}'")
                return processed_text
            else:
                if TRUNCATE_TEXT_DEBUG_VERBOSE:
                    print(f"[TT_CORE] QUICK_CHECK EXIT (base=0): Ellipsis '{ellipsis_symbol}' (width {text_w}) too wide for {available_width}. Returning None.")
                return None
        except Exception as e:
            print(f"[TT_CORE] !!! ERROR in get_size_func during QUICK_CHECK for '{ellipsis_symbol}': {e}")
            return None
    while low <= high:
        mid_base_len = (low + high) // 2
        current_base_text = raw_text[:mid_base_len]
        processed_text = current_base_text + ellipsis_symbol
        if TRUNCATE_TEXT_DEBUG_VERBOSE:
            print(f"[TT_CORE] TRYING (loop): '{processed_text}' (base_len={mid_base_len}, avail_w={available_width})")
        try:
            text_w, text_h = get_size_func(processed_text, font_instance)
            if TRUNCATE_TEXT_DEBUG_VERBOSE:
                print(f"[TT_CORE] MEASURED (loop): '{processed_text}' -> width: {text_w} (avail: {available_width}), height: {text_h}), height: {text_h}")
            if text_w <= available_width:
                best_fittable_text = processed_text
                low = mid_base_len + 1
            else:
                high = mid_base_len - 1
        except Exception as e:
            print(f"[TT_CORE] !!! ERROR in get_size_func for '{processed_text}' (original: '{original_raw_text_for_debug}', available_width: {available_width}): {e}")
            high = mid_base_len - 1
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        if best_fittable_text is None and ellipsis_symbol and (max_chars_for_base > 0):
            print(f"[TT_CORE] INFO: No fit found for base+'{ellipsis_symbol}' where base_len could be up to {max_chars_for_base}. Original: '{original_raw_text_for_debug}', avail_w: {available_width}")
        print(f"[TT_CORE] EXIT: For '{original_raw_text_for_debug}' with ellipsis '{ellipsis_symbol}', best_fit: '{best_fittable_text}'")
    return best_fittable_text

def truncate_text(raw_text: str, available_width: int, max_len: int, font_instance: FontType, get_size_func: GetSizeFuncType) -> str:
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        print(f'[TRUNCATE] ENTER =====================================================')
        print(f"[TRUNCATE] raw_text='{raw_text}', available_width={available_width}, max_len={max_len}, font_size_attr={getattr(font_instance, 'size', 'N/A')}")
    original_len = len(raw_text)
    max_len = max(0, max_len)
    if original_len == 0:
        if TRUNCATE_TEXT_DEBUG_VERBOSE:
            print(f"[TRUNCATE] '{raw_text}' (len 0) -> RETURN ''")
        return ''
    if original_len <= max_len:
        try:
            text_w, _ = get_size_func(raw_text, font_instance)
            if TRUNCATE_TEXT_DEBUG_VERBOSE:
                print(f"[TRUNCATE] Full text ('{raw_text}', len {original_len}) measured width: {text_w} vs avail_w: {available_width}")
            if text_w <= available_width:
                if TRUNCATE_TEXT_DEBUG_VERBOSE:
                    print(f"[TRUNCATE] '{raw_text}' (full text fits by width and max_len) -> RETURN '{raw_text}'")
                return raw_text
        except Exception as e:
            print(f"[TRUNCATE] !!! ERROR measuring initial full text '{raw_text}': {e}")
    ellipsis_options = ['...', '..', '.']
    for ellipsis in ellipsis_options:
        if TRUNCATE_TEXT_DEBUG_VERBOSE:
            print(f"[TRUNCATE] Trying with ellipsis: '{ellipsis}'")
        if max_len < len(ellipsis):
            if TRUNCATE_TEXT_DEBUG_VERBOSE:
                print(f"[TRUNCATE] Ellipsis '{ellipsis}' (len {len(ellipsis)}) too long for max_len {max_len}, skipping.")
            continue
        max_chars_for_base = min(original_len, max_len - len(ellipsis))
        if TRUNCATE_TEXT_DEBUG_VERBOSE:
            print(f"[TRUNCATE] Max_chars_for_base for '{ellipsis}': {max_chars_for_base} (original_len: {original_len}, max_len: {max_len})")
        fittable_text = _find_longest_fit_core(raw_text, available_width, max_chars_for_base, ellipsis, font_instance, get_size_func, raw_text)
        if fittable_text is not None:
            if TRUNCATE_TEXT_DEBUG_VERBOSE:
                print(f"[TRUNCATE] '{raw_text}' -> RETURN '{fittable_text}' (using ellipsis '{ellipsis}')")
            return fittable_text
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        print(f'[TRUNCATE] Trying NO ellipsis.')
    max_chars_for_base_no_ellipsis = min(original_len, max_len)
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        print(f'[TRUNCATE] Max_chars_for_base for NO_ellipsis: {max_chars_for_base_no_ellipsis}')
    fittable_text_no_ellipsis = _find_longest_fit_core(raw_text, available_width, max_chars_for_base_no_ellipsis, '', font_instance, get_size_func, raw_text)
    if fittable_text_no_ellipsis is not None:
        if TRUNCATE_TEXT_DEBUG_VERBOSE:
            print(f"[TRUNCATE] '{raw_text}' -> RETURN '{fittable_text_no_ellipsis}' (no ellipsis fallback)")
        return fittable_text_no_ellipsis
    if TRUNCATE_TEXT_DEBUG_VERBOSE:
        print(f"[TRUNCATE] '{raw_text}' (all attempts failed, avail_w {available_width}) -> RETURN ''")
    return ''

def get_scaled_pixmap_dimensions(source_image_pil: Image.Image, label_width: int, label_height: int) -> Tuple[int, int]:
    if not source_image_pil or not hasattr(source_image_pil, 'size'):
        return (0, 0)
    if label_width <= 0 or label_height <= 0:
        return (0, 0)
    try:
        orig_width, orig_height = source_image_pil.size
    except Exception as e:
        print(f'Error getting source image size in utils.get_scaled_pixmap_dimensions: {e}')
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

def get_magnifier_drawing_coords(app_state: AppState, drawing_width: int, drawing_height: int, display_width: int, display_height: int) -> Tuple[QPoint, QPoint, int, int, QPoint, int, int] | Tuple[None, ...]:
    if not app_state.original_image1 or not app_state.original_image2:
        print(f'DEBUG_GET_MAG_COORDS_FAIL: Original images are None. img1={app_state.original_image1 is None}, img2={app_state.original_image2 is None}')
        return (None,) * 7
    if drawing_width <= 0 or drawing_height <= 0 or display_width <= 0 or (display_height <= 0):
        print(f'DEBUG_GET_MAG_COORDS_FAIL: Dimensions are invalid. draw_wh={drawing_width}x{drawing_height}, display_wh={display_width}x{display_height}')
        return (None,) * 7
    try:
        orig1_width, orig1_height = app_state.original_image1.size
        orig2_width, orig2_height = app_state.original_image2.size
    except Exception as e:
        print(f'Error getting original image sizes in utils.get_magnifier_drawing_coords: {e}')
        return (None,) * 7
    if orig1_width <= 0 or orig1_height <= 0 or orig2_width <= 0 or (orig2_height <= 0):
        print(f'DEBUG_GET_MAG_COORDS_FAIL: Original image dimensions are invalid. orig1={orig1_width}x{orig1_height}, orig2={orig2_width}x{orig2_height}')
        return (None,) * 7
    capture_rel_x = app_state.capture_position_relative.x()
    capture_rel_y = app_state.capture_position_relative.y()
    orig1_min_dim = min(orig1_width, orig1_height) if orig1_width > 0 and orig1_height > 0 else 1
    orig2_min_dim = min(orig2_width, orig2_height) if orig2_width > 0 and orig2_height > 0 else 1
    capture_size_orig1_int = max(10, int(round(app_state.capture_size_relative * orig1_min_dim)))
    capture_size_orig2_int = max(10, int(round(app_state.capture_size_relative * orig2_min_dim)))
    cap1_center_orig_x = max(0, min(orig1_width - 1, int(capture_rel_x * orig1_width)))
    cap1_center_orig_y = max(0, min(orig1_height - 1, int(capture_rel_y * orig1_height)))
    capture_center_orig1 = QPoint(cap1_center_orig_x, cap1_center_orig_y)
    cap2_center_orig_x = max(0, min(orig2_width - 1, int(capture_rel_x * orig2_width)))
    cap2_center_orig_y = max(0, min(orig2_height - 1, int(capture_rel_y * orig2_height)))
    capture_center_orig2 = QPoint(cap2_center_orig_x, cap2_center_orig_y)
    magnifier_midpoint_drawing = None
    magnifier_size_pixels_drawing = 0
    edge_spacing_pixels_drawing = 0
    if app_state.use_magnifier:
        cap_center_drawing_x = max(0.0, min(float(drawing_width - 1), capture_rel_x * float(drawing_width)))
        cap_center_drawing_y = max(0.0, min(float(drawing_height - 1), capture_rel_y * float(drawing_height)))
        cap_center_drawing = QPointF(cap_center_drawing_x, cap_center_drawing_y)
        target_min_dim_drawing = float(min(drawing_width, drawing_height))
        magnifier_size_pixels_drawing = max(10, int(round(app_state.magnifier_size_relative * target_min_dim_drawing)))
        spacing_relative = app_state.magnifier_spacing_relative_visual
        edge_spacing_pixels_drawing = max(0, int(round(spacing_relative * magnifier_size_pixels_drawing)))
        if app_state.freeze_magnifier:
            if app_state.frozen_magnifier_position_relative is not None:
                frozen_rel_x = max(0.0, min(1.0, app_state.frozen_magnifier_position_relative.x()))
                frozen_rel_y = max(0.0, min(1.0, app_state.frozen_magnifier_position_relative.y()))
                magn_center_drawing_x = max(0.0, min(float(drawing_width - 1), frozen_rel_x * float(drawing_width)))
                magn_center_drawing_y = max(0.0, min(float(drawing_height - 1), frozen_rel_y * float(drawing_height)))
                magnifier_midpoint_drawing = QPoint(int(round(magn_center_drawing_x)), int(round(magn_center_drawing_y)))
            else:
                magnifier_midpoint_drawing = QPoint(int(round(cap_center_drawing.x())), int(round(cap_center_drawing.y())))
        else:
            offset_relative = app_state.magnifier_offset_relative_visual
            offset_pixels_drawing_x = offset_relative.x() * target_min_dim_drawing
            offset_pixels_drawing_y = offset_relative.y() * target_min_dim_drawing
            magn_center_drawing_x_float = cap_center_drawing.x() + offset_pixels_drawing_x
            magn_center_drawing_y_float = cap_center_drawing.y() + offset_pixels_drawing_y
            magn_center_drawing_x_clamped = max(0.0, min(float(drawing_width - 1), magn_center_drawing_x_float))
            magn_center_drawing_y_clamped = max(0.0, min(float(drawing_height - 1), magn_center_drawing_y_float))
            magnifier_midpoint_drawing = QPoint(int(round(magn_center_drawing_x_clamped)), int(round(magn_center_drawing_y_clamped)))
    else:
        cap_center_drawing_x = max(0, min(drawing_width - 1, int(round(capture_rel_x * drawing_width))))
        cap_center_drawing_y = max(0, min(drawing_height - 1, int(round(capture_rel_y * drawing_height))))
        magnifier_midpoint_drawing = QPoint(cap_center_drawing_x, cap_center_drawing_y)
        magnifier_size_pixels_drawing = 0
        edge_spacing_pixels_drawing = 0
    print(f'DEBUG_GET_MAG_COORDS_SUCCESS: Calculated magnifier_midpoint_drawing={magnifier_midpoint_drawing}, capture_center_orig1={capture_center_orig1}, etc.')
    return (capture_center_orig1, capture_center_orig2, capture_size_orig1_int, capture_size_orig2_int, magnifier_midpoint_drawing, magnifier_size_pixels_drawing, edge_spacing_pixels_drawing)