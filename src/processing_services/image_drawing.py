import time
from typing import Callable, Tuple
from PIL import Image, ImageDraw, ImageFont
from services.state_manager import AppConstants
from services.utils import truncate_text
from processing_services.image_resize import get_pil_resampling_method
from PyQt6.QtCore import QPoint, QPointF
import traceback
import math
FontType = ImageFont.FreeTypeFont
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]
_font_cache = {}

def _get_cached_font(font_path: str, size: int, use_antialiasing: bool=False) -> FontType:
    cache_key = (font_path, size, use_antialiasing)
    if cache_key not in _font_cache:
        try:
            if font_path:
                font = ImageFont.truetype(font_path, size=size, layout_engine=ImageFont.Layout.BASIC)
            else:
                try:
                    font = ImageFont.load_default(size=size)
                except TypeError:
                    font = ImageFont.load_default()
            _font_cache[cache_key] = font
        except Exception as e:
            print(f'Warning: Failed to load font {font_path} with size {size}, AA={use_antialiasing}: {e}')
            try:
                _font_cache[cache_key] = ImageFont.load_default(size=size)
            except TypeError:
                _font_cache[cache_key] = ImageFont.load_default()
            except Exception as e_fallback:
                print(f'DEBUG_FONT: Ultimate fallback to load_default failed: {e_fallback}')
                _font_cache[cache_key] = ImageFont.load_default()
    return _font_cache[cache_key]
_text_size_cache = {}

def _get_cached_text_size(text: str, font: FontType, draw_context: ImageDraw.ImageDraw=None) -> Tuple[int, int]:
    cache_key = (text, id(font))
    _DEBUG_TIMER_START = time.perf_counter()
    if cache_key not in _text_size_cache:
        _text_size_cache[cache_key] = _internal_get_text_size(text, font, draw_context)
        _DEBUG_TIMER_END = time.perf_counter()
    else:
        _DEBUG_TIMER_END = time.perf_counter()
    return _text_size_cache[cache_key]
from processing_services.image_resize import get_pil_resampling_method

def draw_file_names_on_image(draw: ImageDraw.ImageDraw, image_width: int, image_height: int, split_position_abs: int, is_horizontal: bool, line_thickness_display: int, font_path: str, font_size_percent: int, max_name_length: int, file_name1_text: str, file_name2_text: str, text_color_tuple: tuple, is_interactive_render: bool):
    _DEBUG_TIMER_START = time.perf_counter()
    reference_size = min(image_height, image_width)
    base_font_size_px = max(10, int(reference_size * 0.04))
    font_size = int(base_font_size_px * (font_size_percent / 100.0))
    font_size = max(8, font_size)
    margin = max(5, int(font_size * 0.25))
    SAFETY_MARGIN = 5
    margin += SAFETY_MARGIN
    use_antialiasing = font_size >= 16 and (not is_interactive_render)
    _DEBUG_LOG_ANTIALIASING = f'_DEBUG_LOG_: draw_file_names: use_antialiasing={use_antialiasing} (font_size={font_size}, is_interactive_render={is_interactive_render})'
    print(_DEBUG_LOG_ANTIALIASING)
    font = _get_cached_font(font_path, font_size, use_antialiasing)
    if font is None:
        system_fonts = ['DejaVuSans.ttf', 'Arial.ttf', 'Helvetica.ttf', None]
        for font_name_candidate in system_fonts:
            try:
                font = _get_cached_font(font_name_candidate, font_size, use_antialiasing)
                if font:
                    break
            except Exception:
                continue
        if font is None:
            try:
                font = ImageFont.load_default(size=font_size)
            except TypeError:
                font = ImageFont.load_default()
            except Exception as e:
                print(f'FATAL: Could not load any font: {e}')
                return
    margin_int = int(round(margin))
    truncate_start_time = time.perf_counter()
    if not is_horizontal:
        available_width1 = max(10, int(round(split_position_abs - line_thickness_display // 2 - margin_int * 2)))
        available_width2 = max(10, int(round(image_width - (split_position_abs + (line_thickness_display + 1) // 2) - margin_int * 2)))
        file_name1 = truncate_text(file_name1_text, available_width1, max_name_length, font, lambda t, f: _get_cached_text_size(t, f, draw))
        file_name2 = truncate_text(file_name2_text, available_width2, max_name_length, font, lambda t, f: _get_cached_text_size(t, f, draw))
    else:
        available_width = max(10, int(round(image_width - margin_int * 2)))
        MIN_RENDER_MARGIN = 0
        space_above_line = split_position_abs - line_thickness_display // 2
        available_content_height1 = max(0, space_above_line - MIN_RENDER_MARGIN)
        space_below_line = image_height - (split_position_abs + (line_thickness_display + 1) // 2)
        available_content_height2 = max(0, space_below_line - MIN_RENDER_MARGIN)

        def truncate_text_height(text_input, avail_w, avail_content_h, current_max_len, current_font, get_size_func):
            truncated_by_width = truncate_text(text_input, avail_w, current_max_len, current_font, get_size_func)
            if not truncated_by_width:
                return ''
            text_w, text_h = get_size_func(truncated_by_width, current_font)
            if text_h > avail_content_h:
                return ''
            return truncated_by_width
        file_name1 = truncate_text_height(file_name1_text, available_width, available_content_height1, max_name_length, font, lambda t, f: _get_cached_text_size(t, f, draw))
        file_name2 = truncate_text_height(file_name2_text, available_width, available_content_height2, max_name_length, font, lambda t, f: _get_cached_text_size(t, f, draw))
    print(f'_DEBUG_TIMER_: Truncating text for drawing took {(time.perf_counter() - truncate_start_time) * 1000:.2f} ms')
    text_color = text_color_tuple
    text_drawing_start_time = time.perf_counter()
    if not is_horizontal:
        _draw_vertical_filenames(draw, font, file_name1, file_name2, split_position_abs, line_thickness_display, margin_int, image_width, image_height, text_color, _get_cached_text_size)
    else:
        _draw_horizontal_filenames(draw, font, file_name1, file_name2, split_position_abs, line_thickness_display, margin_int, image_width, image_height, text_color, _get_cached_text_size)
    print(f"_DEBUG_TIMER_: Text drawing (relying on Pillow's native AA) took {(time.perf_counter() - text_drawing_start_time) * 1000:.2f} ms")
    _DEBUG_TIMER_END = time.perf_counter()
    print(f'_DEBUG_TIMER_: draw_file_names_on_image total took {(_DEBUG_TIMER_END - _DEBUG_TIMER_START) * 1000:.2f} ms')

def _internal_get_text_size(text: str, font_to_use: FontType, draw_context: ImageDraw.ImageDraw=None) -> Tuple[int, int]:
    if not text or not font_to_use:
        return (0, 0)
    try:
        if not text.strip():
            try:
                ascent, descent = font_to_use.getmetrics()
                approx_height = ascent + descent
            except AttributeError:
                approx_height = getattr(font_to_use, 'size', 10) * 1.2
            return (0, int(round(approx_height)))
        if draw_context and hasattr(draw_context, 'textbbox'):
            bbox = draw_context.textbbox((0, 0), text, font=font_to_use, anchor='lt')
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            return (int(round(width)), int(round(height)))
        elif hasattr(font_to_use, 'getbbox'):
            bbox = font_to_use.getbbox(text)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        elif hasattr(font_to_use, 'getsize'):
            width, height = font_to_use.getsize(text)
            return (int(round(width)), int(round(height)))
        else:
            print('Warning: Cannot determine text size accurately. Using approximation.')
            font_height_approx = font_to_use.size if hasattr(font_to_use, 'size') else 10
            char_width_approx = font_height_approx * 0.6
            return (int(round(len(text) * char_width_approx)), int(round(font_height_approx)))
    except Exception as e:
        print(f"Error getting text size for '{text[:20]}...': {e}")
        font_height_approx = font_to_use.size if hasattr(font_to_use, 'size') else 10
        char_width_approx = font_height_approx * 0.6
        return (int(round(len(text) * char_width_approx)), int(round(font_height_approx)))

def _draw_vertical_filenames(draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size_func):
    y_baseline = orig_height - margin
    BOUNDARY_MARGIN = 5
    if file_name1:
        try:
            text_width1, text_height1 = get_text_size_func(file_name1, font, draw_context=draw)
            x1_draw_right_edge = split_position_abs - line_width // 2 - margin
            x1_actual_left_edge = x1_draw_right_edge - text_width1
            condition_draw1 = x1_actual_left_edge >= 0 - BOUNDARY_MARGIN
            if condition_draw1:
                anchor1 = 'rs'
                draw.text((x1_draw_right_edge, y_baseline), file_name1, fill=text_color, font=font, anchor=anchor1)
                print(f"_DEBUG_LOG_: Drawn text 1: '{file_name1}' at {x1_draw_right_edge},{y_baseline} (width {text_width1}, height {text_height1})")
        except Exception as e:
            print(f'!!! ERROR processing or drawing filename 1 (vertical): {e}')
    if file_name2:
        try:
            text_width2, text_height2 = get_text_size_func(file_name2, font, draw_context=draw)
            x2_draw_left_edge = split_position_abs + (line_width + 1) // 2 + margin
            x2_actual_right_edge = x2_draw_left_edge + text_width2
            condition_draw2 = x2_actual_right_edge <= orig_width + BOUNDARY_MARGIN
            if condition_draw2:
                anchor2 = 'ls'
                draw.text((x2_draw_left_edge, y_baseline), file_name2, fill=text_color, font=font, anchor=anchor2)
                print(f"_DEBUG_LOG_: Drawn text 2: '{file_name2}' at {x2_draw_left_edge},{y_baseline} (width {text_width2}, height {text_height2})")
        except Exception as e:
            print(f'!!! ERROR processing or drawing filename 2 (vertical): {e}')

def _draw_horizontal_filenames(draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size_func):
    center_x = orig_width // 2
    base_h_margin = max(3, margin * 3 // 8)
    min_margin = 0
    if file_name1:
        draw_text1 = True
        try:
            text_width1, text_height1 = get_text_size_func(file_name1, font, draw_context=draw)
            space_to_top_edge = split_position_abs - line_height // 2
            actual_text_margin1 = base_h_margin
            if text_height1 + base_h_margin > space_to_top_edge:
                actual_text_margin1 = max(min_margin, space_to_top_edge - text_height1)
                if space_to_top_edge - text_height1 < min_margin:
                    draw_text1 = False
            y1_draw_bottom_edge = split_position_abs - line_height // 2 - actual_text_margin1
            y1_actual_top_text_edge = y1_draw_bottom_edge - text_height1
            if y1_actual_top_text_edge < 0:
                draw_text1 = False
            if draw_text1:
                anchor1 = 'mb'
                draw.text((center_x, y1_draw_bottom_edge), file_name1, fill=text_color, font=font, anchor=anchor1)
                print(f"_DEBUG_LOG_: Drawn text 1: '{file_name1}' at {center_x},{y1_draw_bottom_edge} (width {text_width1}, height {text_height1})")
        except Exception as e:
            print(f'!!! ERROR processing or drawing filename 1 (horizontal): {e}')
    if file_name2:
        draw_text2 = True
        try:
            text_width2, text_height2 = get_text_size_func(file_name2, font, draw_context=draw)
            y_separator_bottom_edge = split_position_abs + (line_height + 1) // 2
            space_below_line = orig_height - y_separator_bottom_edge
            actual_text_margin2 = base_h_margin
            if text_height2 + base_h_margin > space_below_line:
                if text_height2 + min_margin <= space_below_line:
                    actual_text_margin2 = min_margin
                else:
                    draw_text2 = False
            if draw_text2:
                y2_draw_coord_mb = y_separator_bottom_edge + actual_text_margin2 + text_height2
                y2_actual_top_text_edge = y2_draw_coord_mb - text_height2
                if y2_draw_coord_mb > orig_height:
                    draw_text2 = False
                if draw_text2:
                    anchor2 = 'mb'
                    draw.text((center_x, y2_draw_coord_mb), file_name2, fill=text_color, font=font, anchor=anchor2)
                    print(f"_DEBUG_LOG_: Drawn text 2: '{file_name2}' at {center_x},{y2_draw_coord_mb} (width {text_width2}, height {text_height2})")
        except Exception as e:
            print(f'!!! ERROR processing or drawing filename 2 (horizontal): {e}')

def draw_split_line_pil(image_to_draw_on: Image.Image, split_position_ratio: float, is_horizontal: bool, line_thickness: int=3, blend_alpha: float=0.5):
    _DEBUG_TIMER_START = time.perf_counter()
    if not isinstance(image_to_draw_on, Image.Image):
        return
    if image_to_draw_on.mode != 'RGBA':
        print(f'_DEBUG_LOG_: draw_split_line_pil requires image_to_draw_on to be RGBA, converting from {image_to_draw_on.mode}.')
        try:
            image_to_draw_on = image_to_draw_on.convert('RGBA')
        except Exception as e:
            print(f'Error converting image_to_draw_on to RGBA: {e}')
            return
    width, height = image_to_draw_on.size
    if width <= 0 or height <= 0:
        return
    draw = ImageDraw.Draw(image_to_draw_on)
    line_color = (255, 255, 255, 255)
    if not is_horizontal:
        split_x = int(round(width * split_position_ratio))
        line_left = max(0, split_x - line_thickness // 2)
        line_right = min(width, split_x + (line_thickness + 1) // 2)
        if line_right > line_left and line_thickness > 0:
            draw.rectangle([line_left, 0, line_right - 1, height - 1], fill=line_color)
    else:
        split_y = int(round(height * split_position_ratio))
        line_top = max(0, split_y - line_thickness // 2)
        line_bottom = min(height, split_y + (line_thickness + 1) // 2)
        if line_bottom > line_top and line_thickness > 0:
            draw.rectangle([0, line_top, width - 1, line_bottom - 1], fill=line_color)
    print(f'_DEBUG_TIMER_: draw_split_line_pil took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')
MIN_CAPTURE_THICKNESS = AppConstants.MIN_CAPTURE_THICKNESS
MAX_CAPTURE_THICKNESS = AppConstants.MAX_CAPTURE_THICKNESS
CAPTURE_THICKNESS_FACTOR = 0.35
MIN_MAG_BORDER_THICKNESS = AppConstants.MIN_MAG_BORDER_THICKNESS
MAX_MAG_BORDER_THICKNESS = AppConstants.MAX_MAG_BORDER_THICKNESS
MAG_BORDER_THICKNESS_FACTOR = 0.15

def draw_magnifier_pil(draw: ImageDraw.ImageDraw, image_to_draw_on: Image.Image, image1_for_crop: Image.Image, image2_for_crop: Image.Image, capture_pos1: QPoint, capture_pos2: QPoint, capture_size_orig1: int, capture_size_orig2: int, magnifier_midpoint_target: QPoint, magnifier_size_pixels: int, edge_spacing_pixels: int, interpolation_method: str, is_interactive_render: bool=False):
    _DEBUG_TIMER_START = time.perf_counter()
    print(f'DEBUG_DRAW_MAG: Entry. cap_pos1={capture_pos1}, cap_pos2={capture_pos2}, magn_mid={magnifier_midpoint_target}, cap_size1={capture_size_orig1}, cap_size2={capture_size_orig2}, magn_pix={magnifier_size_pixels}')
    if not image1_for_crop or not image2_for_crop or (not capture_pos1) or (not capture_pos2) or (not magnifier_midpoint_target):
        print('DEBUG_DRAW_MAG: Missing required inputs for draw_magnifier_pil. Returning.')
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
        print('DEBUG_DRAW_MAG: Invalid sizes for draw_magnifier_pil. Returning.')
        return
    if not isinstance(image_to_draw_on, Image.Image):
        print('draw_magnifier_pil: image_to_draw_on is not a PIL Image. Returning.')
        return
    if image_to_draw_on.mode != 'RGBA':
        print(f'_DEBUG_LOG_: draw_magnifier_pil requires image_to_draw_on to be RGBA, converting from {image_to_draw_on.mode}.')
        try:
            image_to_draw_on = image_to_draw_on.convert('RGBA')
        except Exception as e:
            print(f'Error converting image_to_draw_on to RGBA: {e}')
            return
    result_width, result_height = image_to_draw_on.size
    if result_width <= 0 or result_height <= 0:
        return
    radius = float(magnifier_size_pixels) / 2.0
    half_spacing = float(edge_spacing_pixels) / 2.0
    offset_from_midpoint = radius + half_spacing
    mid_x = float(magnifier_midpoint_target.x())
    mid_y = float(magnifier_midpoint_target.y())
    left_center_x = mid_x - offset_from_midpoint
    right_center_x = mid_x + offset_from_midpoint
    center_y = mid_y
    left_center = QPoint(int(round(left_center_x)), int(round(center_y)))
    right_center = QPoint(int(round(right_center_x)), int(round(center_y)))
    should_combine = edge_spacing_pixels < 1.0
    if should_combine:
        draw_combined_magnifier_circle_pil(draw, image_to_draw_on, magnifier_midpoint_target, capture_pos1, capture_pos2, capture_size_orig1, capture_size_orig2, magnifier_size_pixels, image1_for_crop, image2_for_crop, interpolation_method, is_interactive_render=is_interactive_render)
    else:
        draw_single_magnifier_circle_pil(draw, image_to_draw_on, left_center, capture_pos1, capture_size_orig1, magnifier_size_pixels, image1_for_crop, interpolation_method, is_interactive_render=is_interactive_render)
        draw_single_magnifier_circle_pil(draw, image_to_draw_on, right_center, capture_pos2, capture_size_orig2, magnifier_size_pixels, image2_for_crop, interpolation_method, is_interactive_render=is_interactive_render)
    print(f'_DEBUG_TIMER_: draw_magnifier_pil total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')

def draw_capture_area_pil(draw: ImageDraw.ImageDraw, center_pos: QPoint, size: int):
    _DEBUG_TIMER_START = time.perf_counter()
    if size <= 0 or center_pos is None:
        return
    radius = size // 2
    if radius <= 0:
        return
    bbox = [center_pos.x() - radius, center_pos.y() - radius, center_pos.x() + radius, center_pos.y() + radius]
    thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(size)))
    thickness_clamped = max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float))
    thickness = max(1, int(round(thickness_clamped)))
    try:
        bbox_int = [int(round(c)) for c in bbox]
        draw.ellipse([bbox_int[0], bbox_int[1], bbox_int[2], bbox_int[3]], outline=(255, 0, 0, 155), width=thickness)
    except Exception as e:
        print(f'ERROR in draw_capture_area_pil: {e}. Bbox={bbox}, thickness={thickness}')
    print(f'_DEBUG_TIMER_: draw_capture_area_pil took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')

def create_circular_mask(size: int):
    if size <= 0:
        return None
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask

def draw_single_magnifier_circle_pil(draw: ImageDraw.ImageDraw, target_image: Image.Image, display_center_pos: QPoint, capture_center_orig: QPoint, capture_size_orig: int, magnifier_size_pixels: int, image_for_crop: Image.Image, interpolation_method: str, is_interactive_render: bool=False):
    _DEBUG_TIMER_START = time.perf_counter()
    if not isinstance(image_for_crop, Image.Image) or not hasattr(image_for_crop, 'size'):
        print('draw_single_magnifier: Invalid source image.')
        return
    if not isinstance(target_image, Image.Image):
        print('draw_single_magnifier: Invalid target image.')
        return
    if capture_size_orig <= 0 or magnifier_size_pixels <= 0:
        print('DEBUG_DRAW_MAG: Invalid capture_size_orig or magnifier_size_pixels in draw_single_magnifier_circle_pil.')
        return
    source_width, source_height = image_for_crop.size
    if source_width <= 0 or source_height <= 0:
        print('DEBUG_DRAW_MAG: Invalid source image dimensions in draw_single_magnifier_circle_pil.')
        return
    if image_for_crop.mode != 'RGBA':
        print(f'_DEBUG_LOG_: Converting image_for_crop from {image_for_crop.mode} to RGBA before cropping for single magnifier.')
        image_for_crop = image_for_crop.convert('RGBA')
    captured_area = None
    crop_start_time = time.perf_counter()
    try:
        capture_radius_orig = capture_size_orig // 2
        crop_x1 = max(0, capture_center_orig.x() - capture_radius_orig)
        crop_y1 = max(0, capture_center_orig.y() - capture_radius_orig)
        crop_x2 = min(source_width, crop_x1 + capture_size_orig)
        crop_y2 = min(source_height, crop_y1 + capture_size_orig)
        if crop_x2 - crop_x1 < capture_size_orig:
            crop_x1 = max(0, crop_x2 - capture_size_orig)
        if crop_y2 - crop_y1 < capture_size_orig:
            crop_y1 = max(0, crop_y2 - capture_size_orig)
        crop_x1 = max(0, crop_x1)
        crop_y1 = max(0, crop_y1)
        crop_x2 = min(source_width, crop_x1 + capture_size_orig)
        crop_y2 = min(source_height, crop_y1 + capture_size_orig)
        crop_box = (crop_x1, crop_y1, crop_x2, crop_y2)
        print(f'_DEBUG_LOG_: Cropping original image {image_for_crop.size} with box {crop_box}')
        captured_area = image_for_crop.crop(crop_box)
        print(f'_DEBUG_LOG_: Cropped area size={captured_area.size}, mode={captured_area.mode}')
    except Exception as e:
        print(f'Error cropping single magnifier source: {e}')
        return
    print(f'_DEBUG_TIMER_: Single magnifier crop took {(time.perf_counter() - crop_start_time) * 1000:.2f} ms')
    scaled_capture = None
    resize_start_time = time.perf_counter()
    try:
        resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)
        print(f"_DEBUG_LOG_: Resizing single magnifier capture from {captured_area.size} to ({magnifier_size_pixels}, {magnifier_size_pixels}) with method {(resampling_method.value if hasattr(resampling_method, 'value') else resampling_method)} (is_interactive_render={is_interactive_render})")
        scaled_capture = captured_area.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e:
        print(f'Error resizing single magnifier capture: {e}')
        return
    print(f'_DEBUG_TIMER_: Single magnifier resize took {(time.perf_counter() - resize_start_time) * 1000:.2f} ms')
    if scaled_capture.mode != 'RGBA':
        try:
            print(f'_DEBUG_LOG_: Converting scaled_capture from {scaled_capture.mode} to RGBA.')
            scaled_capture = scaled_capture.convert('RGBA')
        except Exception as e:
            print(f'Error converting scaled capture to RGBA: {e}')
            return
    mask_apply_start_time = time.perf_counter()
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        if mask:
            scaled_capture.putalpha(mask)
        else:
            print('Warning: Failed to create circular mask.')
    except Exception as e:
        print(f'Error applying mask to single magnifier: {e}')
    print(f'_DEBUG_TIMER_: Single magnifier mask apply took {(time.perf_counter() - mask_apply_start_time) * 1000:.2f} ms')
    radius_float = float(magnifier_size_pixels) / 2.0
    center_x_float = float(display_center_pos.x())
    center_y_float = float(display_center_pos.y())
    paste_x_float = center_x_float - radius_float
    paste_y_float = center_y_float - radius_float
    paste_x = int(round(paste_x_float))
    paste_y = int(round(paste_y_float))
    paste_start_time = time.perf_counter()
    try:
        target_image.paste(scaled_capture, (paste_x, paste_y), scaled_capture)
        print(f'_DEBUG_LOG_: Pasted single magnifier at ({paste_x},{paste_y}) on target image.')
    except Exception as e:
        print(f'Error pasting single magnifier onto target: {e}')
        return
    print(f'_DEBUG_TIMER_: Single magnifier paste took {(time.perf_counter() - paste_start_time) * 1000:.2f} ms')
    border_draw_start_time = time.perf_counter()
    try:
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size_pixels - 1, paste_y + magnifier_size_pixels - 1]
        thickness_float = MAG_BORDER_THICKNESS_FACTOR * math.sqrt(max(1.0, float(magnifier_size_pixels)))
        thickness_clamped = max(float(MIN_MAG_BORDER_THICKNESS), min(float(MAX_MAG_BORDER_THICKNESS), thickness_float))
        border_thickness = max(1, int(round(thickness_clamped)))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception as e:
        print(f'Error drawing border for single magnifier: {e}')
    print(f'_DEBUG_TIMER_: Single magnifier border draw took {(time.perf_counter() - border_draw_start_time) * 1000:.2f} ms')
    print(f'_DEBUG_TIMER_: draw_single_magnifier_circle_pil total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')

def draw_combined_magnifier_circle_pil(draw: ImageDraw.ImageDraw, target_image: Image.Image, display_center_pos: QPoint, capture_center_orig1: QPoint, capture_center_orig2: QPoint, capture_size_orig1: int, capture_size_orig2: int, magnifier_size_pixels: int, image1_for_crop: Image.Image, image2_for_crop: Image.Image, interpolation_method: str, is_interactive_render: bool=False):
    _DEBUG_TIMER_START = time.perf_counter()
    if not image1_for_crop or not image2_for_crop or (not capture_center_orig1) or (not capture_center_orig2):
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
        return
    if not isinstance(target_image, Image.Image) or target_image.mode != 'RGBA':
        return
    source1_width, source1_height = image1_for_crop.size
    source2_width, source2_height = image2_for_crop.size
    if source1_width <= 0 or source1_height <= 0 or source2_width <= 0 or (source2_height <= 0):
        return
    if image1_for_crop.mode != 'RGBA':
        print(f'_DEBUG_LOG_: Converting image1_for_crop from {image1_for_crop.mode} to RGBA before cropping for combined magnifier.')
        image1_for_crop = image1_for_crop.convert('RGBA')
    if image2_for_crop.mode != 'RGBA':
        print(f'_DEBUG_LOG_: Converting image2_for_crop from {image2_for_crop.mode} to RGBA before cropping for combined magnifier.')
        image2_for_crop = image2_for_crop.convert('RGBA')
    captured_area1 = captured_area2 = None
    cap_radius_orig1 = capture_size_orig1 // 2
    cap_radius_orig2 = capture_size_orig2 // 2
    crop_start_time = time.perf_counter()
    try:
        crop1_x1 = max(0, capture_center_orig1.x() - cap_radius_orig1)
        crop1_y1 = max(0, capture_center_orig1.y() - cap_radius_orig1)
        crop1_x2 = min(source1_width, crop1_x1 + capture_size_orig1)
        crop1_y2 = min(source1_height, crop1_y1 + capture_size_orig1)
        if crop1_x2 - crop1_x1 < capture_size_orig1:
            crop1_x1 = max(0, crop1_x2 - capture_size_orig1)
        if crop1_y2 - crop1_y1 < capture_size_orig1:
            crop1_y1 = max(0, crop1_y2 - capture_size_orig1)
        crop_box1 = (max(0, crop1_x1), max(0, crop1_y1), min(source1_width, crop1_x1 + capture_size_orig1), min(source1_height, crop1_y1 + capture_size_orig1))
        print(f'_DEBUG_LOG_: Cropping original image 1 {image1_for_crop.size} with box {crop_box1}')
        captured_area1 = image1_for_crop.crop(crop_box1)
        print(f'_DEBUG_LOG_: Cropped area 1 size={captured_area1.size}, mode={captured_area1.mode}')
    except Exception as e:
        print(f'Error cropping img1 for combined magnifier: {e}')
        return
    try:
        crop2_x1 = max(0, capture_center_orig2.x() - cap_radius_orig2)
        crop2_y1 = max(0, capture_center_orig2.y() - cap_radius_orig2)
        crop2_x2 = min(source2_width, crop2_x1 + capture_size_orig2)
        crop2_y2 = min(source2_height, crop2_y1 + capture_size_orig2)
        if crop2_x2 - crop2_x1 < capture_size_orig2:
            crop2_x1 = max(0, crop2_x2 - capture_size_orig2)
        if crop2_y2 - crop2_y1 < capture_size_orig2:
            crop2_y1 = max(0, crop2_y2 - capture_size_orig2)
        crop_box2 = (max(0, crop2_x1), max(0, crop2_y1), min(source2_width, crop2_x1 + capture_size_orig2), min(source2_height, crop2_y1 + capture_size_orig2))
        print(f'_DEBUG_LOG_: Cropping original image 2 {image2_for_crop.size} with box {crop_box2}')
        captured_area2 = image2_for_crop.crop(crop_box2)
        print(f'_DEBUG_LOG_: Cropped area 2 size={captured_area2.size}, mode={captured_area2.mode}')
    except Exception as e:
        print(f'Error cropping img2 for combined magnifier: {e}')
        return
    print(f'_DEBUG_TIMER_: Combined magnifier crops took {(time.perf_counter() - crop_start_time) * 1000:.2f} ms')
    scaled_capture1 = scaled_capture2 = None
    resize_start_time = time.perf_counter()
    try:
        resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)
        print(f"_DEBUG_LOG_: Resizing combined magnifier capture 1 from {captured_area1.size} to ({magnifier_size_pixels}, {magnifier_size_pixels}) with method {(resampling_method.value if hasattr(resampling_method, 'value') else resampling_method)} (is_interactive_render={is_interactive_render})")
        scaled_capture1 = captured_area1.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
        print(f"_DEBUG_LOG_: Resizing combined magnifier capture 2 from {captured_area2.size} to ({magnifier_size_pixels}, {magnifier_size_pixels}) with method {(resampling_method.value if hasattr(resampling_method, 'value') else resampling_method)} (is_interactive_render={is_interactive_render})")
        scaled_capture2 = captured_area2.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e:
        print(f'Error resizing combined magnifier parts: {e}')
        return
    print(f'_DEBUG_TIMER_: Combined magnifier resizes took {(time.perf_counter() - resize_start_time) * 1000:.2f} ms')
    magnifier_img = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
    half_width = max(0, magnifier_size_pixels // 2)
    right_half_start = half_width
    right_half_width = magnifier_size_pixels - right_half_start
    paste_halves_start_time = time.perf_counter()
    try:
        left_half = scaled_capture1.crop((0, 0, min(half_width, scaled_capture1.width), scaled_capture1.height))
        if right_half_start < scaled_capture2.width and right_half_width > 0:
            right_half = scaled_capture2.crop((right_half_start, 0, min(right_half_start + right_half_width, scaled_capture2.width), scaled_capture2.height))
        else:
            right_half = Image.new('RGBA', (max(0, right_half_width), magnifier_size_pixels), (0, 0, 0, 0))
        magnifier_img.paste(left_half, (0, 0))
        if right_half.width > 0:
            magnifier_img.paste(right_half, (right_half_start, 0))
    except Exception as paste_err:
        print(f'Error pasting halves for combined magnifier: {paste_err}')
        return
    print(f'_DEBUG_TIMER_: Combined magnifier paste halves took {(time.perf_counter() - paste_halves_start_time) * 1000:.2f} ms')
    mask_apply_start_time = time.perf_counter()
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        if mask:
            magnifier_img.putalpha(mask)
        else:
            print('Warning: Failed to create mask for combined magnifier.')
    except Exception as mask_err:
        print(f'Error applying mask to combined magnifier: {mask_err}')
        return
    print(f'_DEBUG_TIMER_: Combined magnifier mask apply took {(time.perf_counter() - mask_apply_start_time) * 1000:.2f} ms')
    radius_float = float(magnifier_size_pixels) / 2.0
    center_x_float = float(display_center_pos.x())
    center_y_float = float(display_center_pos.y())
    paste_x_float = center_x_float - radius_float
    paste_y_float = center_y_float - radius_float
    paste_x = int(round(paste_x_float))
    paste_y = int(round(paste_y_float))
    final_paste_start_time = time.perf_counter()
    try:
        target_image.paste(magnifier_img, (paste_x, paste_y), magnifier_img)
        print(f'_DEBUG_LOG_: Pasted combined magnifier at ({paste_x},{paste_y}) on target image.')
    except Exception as final_err:
        print(f'Error pasting combined magnifier onto target: {final_err}')
        return
    print(f'_DEBUG_TIMER_: Combined magnifier final paste took {(time.perf_counter() - final_paste_start_time) * 1000:.2f} ms')
    border_draw_start_time = time.perf_counter()
    try:
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size_pixels - 1, paste_y + magnifier_size_pixels - 1]
        thickness_float = MAG_BORDER_THICKNESS_FACTOR * math.sqrt(max(1.0, float(magnifier_size_pixels)))
        thickness_clamped = max(float(MIN_MAG_BORDER_THICKNESS), min(float(MAX_MAG_BORDER_THICKNESS), thickness_float))
        dynamic_thickness = max(1, int(round(thickness_clamped)))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=dynamic_thickness)
        line_x = paste_x + half_width
        draw.rectangle([line_x - dynamic_thickness // 2, paste_y, line_x + (dynamic_thickness + 1) // 2 - 1, paste_y + magnifier_size_pixels - 1], fill=(255, 255, 255, 200))
    except Exception as draw_err:
        print(f'Error drawing border/line for combined magnifier: {draw_err}')
    print(f'_DEBUG_TIMER_: Combined magnifier border draw took {(time.perf_counter() - border_draw_start_time) * 1000:.2f} ms')
    print(f'_DEBUG_TIMER_: draw_combined_magnifier_circle_pil total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')

def create_base_split_image_pil(image1_processed: Image.Image, image2_processed: Image.Image, split_position_visual: float, is_horizontal: bool) -> Image.Image | None:
    _DEBUG_TIMER_START = time.perf_counter()
    if not image1_processed or not image2_processed:
        return None
    if image1_processed.mode != 'RGBA':
        print(f'_DEBUG_LOG_: create_base_split_image_pil: Converting image1_processed from {image1_processed.mode} to RGBA.')
        image1_processed = image1_processed.convert('RGBA')
    if image2_processed.mode != 'RGBA':
        print(f'_DEBUG_LOG_: create_base_split_image_pil: Converting image2_processed from {image2_processed.mode} to RGBA.')
        image2_processed = image2_processed.convert('RGBA')
    if image1_processed.size != image2_processed.size:
        print(f'_DEBUG_LOG_: create_base_split_image_pil: Mismatched sizes: {image1_processed.size} vs {image2_processed.size}. Attempting to resize to common min size.')
        min_w = min(image1_processed.size[0], image2_processed.size[0])
        min_h = min(image1_processed.size[1], image2_processed.size[1])
        if min_w <= 0 or min_h <= 0:
            print('ERROR: One of the processed images has zero or negative dimension. Cannot create base split image.')
            return None
        if image1_processed.size != (min_w, min_h):
            image1_processed = image1_processed.resize((min_w, min_h), Image.Resampling.BILINEAR)
        if image2_processed.size != (min_w, min_h):
            image2_processed = image2_processed.resize((min_w, min_h), Image.Resampling.BILINEAR)
        if image1_processed.size != image2_processed.size:
            print('ERROR: Failed to match image sizes for base split image. Aborting.')
            return None
    width, height = image1_processed.size
    if width <= 0 or height <= 0:
        return None
    result = Image.new('RGBA', (width, height))
    try:
        if not is_horizontal:
            split_pos_abs = max(0, min(width, int(round(width * split_position_visual))))
            if split_pos_abs > 0:
                result.paste(image1_processed.crop((0, 0, split_pos_abs, height)), (0, 0))
            if split_pos_abs < width:
                result.paste(image2_processed.crop((split_pos_abs, 0, width, height)), (split_pos_abs, 0))
        else:
            split_pos_abs = max(0, min(height, int(round(height * split_position_visual))))
            if split_pos_abs > 0:
                result.paste(image1_processed.crop((0, 0, width, split_pos_abs)), (0, 0))
            if split_pos_abs < height:
                result.paste(image2_processed.crop((0, split_pos_abs, width, height)), (0, split_pos_abs))
        print(f'_DEBUG_LOG_: Base split image created with split position {split_position_visual}. Size: {result.size}')
    except Exception as e:
        print(f'ERROR in create_base_split_image_pil during paste: {e}')
        traceback.print_exc()
        return None
    print(f'_DEBUG_TIMER_: create_base_split_image_pil took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')
    return result

def draw_all_overlays_on_base_image_pil(base_image: Image.Image, app_state, split_position_visual: float, is_horizontal: bool, use_magnifier: bool, show_capture_area_on_main_image: bool, capture_position_relative: QPointF, original_image1: Image.Image | None, original_image2: Image.Image | None, magnifier_drawing_coords: Tuple[QPoint, QPoint, int, int, QPoint, int, int] | Tuple[None, ...], include_file_names: bool, font_path_absolute: str, font_size_percent: int, max_name_length: int, file_name1_text: str, file_name2_text: str, file_name_color_rgb: tuple, interpolation_method: str) -> Image.Image | None:
    _DEBUG_TIMER_START = time.perf_counter()
    if not base_image:
        return None
    if base_image.mode != 'RGBA':
        print(f'_DEBUG_LOG_: draw_all_overlays_on_base_image_pil received base_image in mode {base_image.mode}, converting to RGBA.')
        base_image = base_image.convert('RGBA')
    width, height = base_image.size
    if width <= 0 or height <= 0:
        return None
    if include_file_names:
        draw_names_start = time.perf_counter()
        split_pos_abs = int(round(width * split_position_visual)) if not is_horizontal else int(round(height * split_position_visual))
        line_thickness_display_for_names = max(1, int(min(width, height) * 0.005))
        line_thickness_display_for_names = min(line_thickness_display_for_names, 7)
        text_render_is_interactive = app_state.is_interactive_mode
        print(f'_DEBUG_LOG_: Text drawing interactive state from app_state.is_interactive_mode: {text_render_is_interactive}')
        draw_file_names_on_image(ImageDraw.Draw(base_image), width, height, split_pos_abs, is_horizontal, line_thickness_display_for_names, font_path_absolute, font_size_percent, max_name_length, file_name1_text, file_name2_text, file_name_color_rgb, text_render_is_interactive)
        print(f'_DEBUG_TIMER_: draw_all_overlays: draw_file_names_on_image (on base_image) took {(time.perf_counter() - draw_names_start) * 1000:.2f} ms')
    combined_overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    combined_overlay_draw = ImageDraw.Draw(combined_overlay)
    line_thickness_display = max(1, int(min(width, height) * 0.005))
    line_thickness_display = min(line_thickness_display, 7)
    draw_split_line_start = time.perf_counter()
    draw_split_line_pil(combined_overlay, split_position_visual, is_horizontal, line_thickness=line_thickness_display)
    print(f"DEBUG_MAG_CONDITION_CHECK: use_magnifier={use_magnifier}, magnifier_drawing_coords={magnifier_drawing_coords}, first_coord={(magnifier_drawing_coords[0] if magnifier_drawing_coords and len(magnifier_drawing_coords) > 0 else 'N/A')}")
    if use_magnifier and magnifier_drawing_coords and (magnifier_drawing_coords[0] is not None):
        print('DEBUG_MAG_RENDER_BLOCK_ENTERED: Magnifier rendering logic is executing.')
        magnifier_draw_start = time.perf_counter()
        cap_center1, cap_center2, cap_size1, cap_size2, magn_mid, magn_size_pix, magn_spacing_pix = magnifier_drawing_coords
        is_interactive_render_for_magnifier = app_state.is_interactive_mode
        magnifier_cache_key_parts = [id(original_image1), id(original_image2), app_state.magnifier_offset_relative_visual.x(), app_state.magnifier_offset_relative_visual.y(), app_state.magnifier_spacing_relative_visual, app_state.magnifier_size_relative, app_state.capture_size_relative, interpolation_method, app_state.freeze_magnifier, app_state.frozen_magnifier_position_relative.x() if app_state.freeze_magnifier and app_state.frozen_magnifier_position_relative else None, app_state.frozen_magnifier_position_relative.y() if app_state.freeze_magnifier and app_state.frozen_magnifier_position_relative else None, app_state.is_interactive_mode, width, height]
        magnifier_cache_key = tuple(magnifier_cache_key_parts)
        cached_magnifier_layer = app_state.magnifier_cache.get(magnifier_cache_key)
        print(f'_DEBUG_LOG_: Magnifier cache hit: {cached_magnifier_layer is not None}')
        if cached_magnifier_layer:
            combined_overlay.alpha_composite(cached_magnifier_layer)
        else:
            magnifier_layer_temp = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            magnifier_layer_draw = ImageDraw.Draw(magnifier_layer_temp)
            if show_capture_area_on_main_image and cap_center1 and (cap_size1 > 0):
                cap_marker_center_draw_x = int(round(capture_position_relative.x() * float(width)))
                cap_marker_center_draw_y = int(round(capture_position_relative.y() * float(height)))
                capture_marker_center_drawing = QPoint(cap_marker_center_draw_x, cap_marker_center_draw_y)
                current_drawing_min_dim = min(width, height)
                capture_marker_size_drawing = max(5, int(round(app_state.capture_size_relative * current_drawing_min_dim)))
                draw_capture_area_pil(magnifier_layer_draw, capture_marker_center_drawing, capture_marker_size_drawing)
            if magn_mid:
                draw_magnifier_pil(magnifier_layer_draw, magnifier_layer_temp, image1_for_crop=original_image1, image2_for_crop=original_image2, capture_pos1=cap_center1, capture_pos2=cap_center2, capture_size_orig1=cap_size1, capture_size_orig2=cap_size2, magnifier_midpoint_target=magn_mid, magnifier_size_pixels=magn_size_pix, edge_spacing_pixels=magn_spacing_pix, interpolation_method=interpolation_method, is_interactive_render=is_interactive_render_for_magnifier)
            app_state.magnifier_cache[magnifier_cache_key] = magnifier_layer_temp.copy()
            combined_overlay.alpha_composite(magnifier_layer_temp)
        print(f'_DEBUG_TIMER_: draw_all_overlays: magnifier rendering took {(time.perf_counter() - magnifier_draw_start) * 1000:.2f} ms')
    else:
        print('DEBUG_MAG_RENDER_BLOCK_SKIPPED: Condition for magnifier drawing was FALSE.')
    alpha_composite_start = time.perf_counter()
    try:
        final_image_result = Image.alpha_composite(base_image, combined_overlay)
    except Exception as e_composite:
        print(f'ERROR during alpha_composite (overlays): {e_composite}')
        traceback.print_exc()
        return None
    print(f'_DEBUG_TIMER_: draw_all_overlays: alpha_composite took {(time.perf_counter() - alpha_composite_start) * 1000:.2f} ms')
    print(f'_DEBUG_TIMER_: draw_all_overlays_on_base_image_pil total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')
    return final_image_result

def generate_comparison_image_pil(app_state, base_image: Image.Image | None, image1_processed: Image.Image, image2_processed: Image.Image, split_position_visual: float, is_horizontal: bool, use_magnifier: bool, show_capture_area_on_main_image: bool, capture_position_relative: QPointF, original_image1: Image.Image | None, original_image2: Image.Image | None, magnifier_drawing_coords: Tuple[QPoint, QPoint, int, int, QPoint, int, int] | Tuple[None, ...], include_file_names: bool, font_path_absolute: str, font_size_percent: int, max_name_length: int, file_name1_text: str, file_name2_text: str, file_name_color_rgb: tuple, interpolation_method: str) -> Image.Image | None:
    _DEBUG_TIMER_START = time.perf_counter()
    if base_image is None:
        print('ERROR: generate_comparison_image_pil received None for base_image. This should not happen.')
        return None
    final_image = draw_all_overlays_on_base_image_pil(base_image=base_image, app_state=app_state, split_position_visual=split_position_visual, is_horizontal=is_horizontal, use_magnifier=use_magnifier, show_capture_area_on_main_image=show_capture_area_on_main_image, capture_position_relative=capture_position_relative, original_image1=original_image1, original_image2=original_image2, magnifier_drawing_coords=magnifier_drawing_coords, include_file_names=include_file_names, font_path_absolute=font_path_absolute, font_size_percent=font_size_percent, max_name_length=max_name_length, file_name1_text=file_name1_text, file_name2_text=file_name2_text, file_name_color_rgb=file_name_color_rgb, interpolation_method=interpolation_method)
    print(f'_DEBUG_TIMER_: generate_comparison_image_pil total took {(time.perf_counter() - _DEBUG_TIMER_START) * 1000:.2f} ms')
    return final_image
