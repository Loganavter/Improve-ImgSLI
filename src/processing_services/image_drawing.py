import time
from typing import Callable, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageChops
from services.state_manager import AppConstants
from services.utils import truncate_text
from processing_services.image_resize import get_pil_resampling_method
from PyQt6.QtCore import QPoint, QRect
import traceback
import math
import os
import sys
import logging

logger = logging.getLogger("ImproveImgSLI")

_mask_image_cache = None
_mask_path_checked = False
FontType = ImageFont.FreeTypeFont
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]
_font_cache = {}


def get_smooth_circular_mask(size: int) -> Image.Image | None:
    global _mask_image_cache, _mask_path_checked

    if not _mask_path_checked:
        _mask_path_checked = True
        app_main_script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        mask_path = os.path.join(
            app_main_script_dir,
            'assets',
            'circle_mask.png')
        
        if not os.path.exists(mask_path):
             mask_path = '/app/lib/Improve-ImgSLI/assets/circle_mask.png'

        if os.path.exists(mask_path):
            try:
                rgba_mask = Image.open(mask_path)
                if 'A' in rgba_mask.getbands():
                    _mask_image_cache = rgba_mask.getchannel('A')
                else:
                    _mask_image_cache = ImageOps.invert(rgba_mask.convert('L'))
            except Exception as e:
                logger.error(f"Failed to load/process circle_mask.png: {e}")
                _mask_image_cache = None
        else:
            logger.warning(
                f"circle_mask.png not found. Falling back to programmatic mask.")

    if size <= 0: return None

    if _mask_image_cache:
        return _mask_image_cache.resize((size, size), Image.Resampling.LANCZOS)

    scale = 4
    big_size = size * scale
    mask = Image.new('L', (big_size, big_size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, big_size, big_size), fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    return mask

def _get_cached_font(font_path: str, size: int,
                     use_antialiasing: bool = False) -> FontType:
    cache_key = (font_path, size, use_antialiasing)
    if cache_key not in _font_cache:
        try:
            if font_path:
                font = ImageFont.truetype(
                    font_path, size=size, layout_engine=ImageFont.Layout.BASIC)
            else:
                try:
                    font = ImageFont.load_default(size=size)
                except TypeError:
                    font = ImageFont.load_default()
            _font_cache[cache_key] = font
        except Exception as e:
            logger.warning(
                f'Failed to load font {font_path} with size {size}, AA={use_antialiasing}: {e}')
            try:
                _font_cache[cache_key] = ImageFont.load_default(size=size)
            except TypeError:
                _font_cache[cache_key] = ImageFont.load_default()
            except Exception as e_fallback:
                logger.critical(
                    f'Ultimate fallback to load_default failed: {e_fallback}')
                _font_cache[cache_key] = ImageFont.load_default()
    return _font_cache[cache_key]


_text_size_cache = {}


def _get_cached_text_size(text: str, font: FontType,
                          draw_context: ImageDraw.ImageDraw = None) -> Tuple[int, int]:
    cache_key = (text, id(font))
    time.perf_counter()
    if cache_key not in _text_size_cache:
        _text_size_cache[cache_key] = _internal_get_text_size(
            text, font, draw_context)
        time.perf_counter()
    else:
        time.perf_counter()
    return _text_size_cache[cache_key]


def draw_file_names_on_image(draw: ImageDraw.ImageDraw, image_rect_on_canvas: QRect, split_position_on_canvas: int, is_horizontal: bool, line_thickness_display: int,
                             font_path: str, font_size_percent: int, max_name_length: int, file_name1_text: str, file_name2_text: str, text_color_tuple: tuple, is_interactive_render: bool):
    reference_size = min(image_rect_on_canvas.height(), image_rect_on_canvas.width())
    base_font_size_px = max(10, int(reference_size * 0.04))
    font_size = int(base_font_size_px * (font_size_percent / 100.0))
    font_size = max(8, font_size)
    margin = max(5, int(font_size * 0.25))
    SAFETY_MARGIN = 5
    margin += SAFETY_MARGIN
    use_antialiasing = font_size >= 16 and (not is_interactive_render)
    logger.debug(f'draw_file_names: use_antialiasing={use_antialiasing} (font_size={font_size}, is_interactive_render={is_interactive_render})')
    font = _get_cached_font(font_path, font_size, use_antialiasing)
    if font is None:
        system_fonts = ['DejaVuSans.ttf', 'Arial.ttf', 'Helvetica.ttf', None]
        for font_name_candidate in system_fonts:
            try:
                font = _get_cached_font(
                    font_name_candidate, font_size, use_antialiasing)
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
                logger.critical(f'Could not load any font: {e}')
                return
    margin_int = int(round(margin))
    if not is_horizontal:
        available_width1 = max(
            10, int(
                round(
                    (split_position_on_canvas - image_rect_on_canvas.left()) - line_thickness_display // 2 - margin_int * 2)))
        available_width2 = max(10, int(round(
            (image_rect_on_canvas.right() - (split_position_on_canvas + (line_thickness_display + 1) // 2)) - margin_int * 2)))

        file_name1 = truncate_text(
            file_name1_text,
            available_width1,
            max_name_length,
            font,
            lambda t,
            f: _get_cached_text_size(
                t,
                f,
                draw))
        file_name2 = truncate_text(
            file_name2_text,
            available_width2,
            max_name_length,
            font,
            lambda t,
            f: _get_cached_text_size(
                t,
                f,
                draw))
    else:
        available_width = max(10, int(round(image_rect_on_canvas.width() - margin_int * 2)))
        MIN_RENDER_MARGIN = 0
        space_above_line = (split_position_on_canvas - line_thickness_display // 2) - image_rect_on_canvas.top()
        available_content_height1 = max(
            0, space_above_line - MIN_RENDER_MARGIN)
        space_below_line = image_rect_on_canvas.bottom() - (split_position_on_canvas + (line_thickness_display + 1) // 2)
        available_content_height2 = max(
            0, space_below_line - MIN_RENDER_MARGIN)

        def truncate_text_height(
                text_input, avail_w, avail_content_h, current_max_len, current_font, get_size_func):
            truncated_by_width = truncate_text(
                text_input, avail_w, current_max_len, current_font, get_size_func)
            if not truncated_by_width:
                return ''
            text_w, text_h = get_size_func(truncated_by_width, current_font)
            if text_h > avail_content_h:
                return ''
            return truncated_by_width
        file_name1 = truncate_text_height(
            file_name1_text,
            available_width,
            available_content_height1,
            max_name_length,
            font,
            lambda t,
            f: _get_cached_text_size(
                t,
                f,
                draw))
        file_name2 = truncate_text_height(
            file_name2_text,
            available_width,
            available_content_height2,
            max_name_length,
            font,
            lambda t,
            f: _get_cached_text_size(
                t,
                f,
                draw))
    text_color = text_color_tuple
    if not is_horizontal:
        _draw_vertical_filenames(
            draw,
            font,
            file_name1,
            file_name2,
            split_position_on_canvas,
            line_thickness_display,
            margin_int,
            image_rect_on_canvas,
            text_color,
            _get_cached_text_size)
    else:
        _draw_horizontal_filenames(
            draw,
            font,
            file_name1,
            file_name2,
            split_position_on_canvas,
            line_thickness_display,
            margin_int,
            image_rect_on_canvas,
            text_color,
            _get_cached_text_size)


def _internal_get_text_size(text: str, font_to_use: FontType,
                            draw_context: ImageDraw.ImageDraw = None) -> Tuple[int, int]:
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
            bbox = draw_context.textbbox(
                (0, 0), text, font=font_to_use, anchor='lt')
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
            logger.warning('Cannot determine text size accurately. Using approximation.')
            font_height_approx = font_to_use.size if hasattr(
                font_to_use, 'size') else 10
            char_width_approx = font_height_approx * 0.6
            return (int(round(len(text) * char_width_approx)),
                    int(round(font_height_approx)))
    except Exception as e:
        logger.error(f"Error getting text size for '{text[:20]}...': {e}")
        font_height_approx = font_to_use.size if hasattr(
            font_to_use, 'size') else 10
        char_width_approx = font_height_approx * 0.6
        return (int(round(len(text) * char_width_approx)),
                int(round(font_height_approx)))


def _draw_vertical_filenames(draw, font, file_name1, file_name2, split_position_on_canvas,
                             line_width, margin, image_rect: QRect, text_color, get_text_size_func):
    y_baseline = image_rect.bottom() - margin
    BOUNDARY_MARGIN = 5
    if file_name1:
        try:
            text_width1, text_height1 = get_text_size_func(
                file_name1, font, draw_context=draw)
            x1_draw_right_edge = split_position_on_canvas - line_width // 2 - margin
            x1_actual_left_edge = x1_draw_right_edge - text_width1
            condition_draw1 = x1_actual_left_edge >= image_rect.left() - BOUNDARY_MARGIN
            if condition_draw1:
                anchor1 = 'rs'
                draw.text((x1_draw_right_edge, y_baseline), file_name1,
                          fill=text_color, font=font, anchor=anchor1)
        except Exception as e:
            logger.error(f'Error processing or drawing filename 1 (vertical): {e}')
    if file_name2:
        try:
            text_width2, text_height2 = get_text_size_func(
                file_name2, font, draw_context=draw)
            x2_draw_left_edge = split_position_on_canvas + \
                (line_width + 1) // 2 + margin
            x2_actual_right_edge = x2_draw_left_edge + text_width2
            condition_draw2 = x2_actual_right_edge <= image_rect.right() + BOUNDARY_MARGIN 
            if condition_draw2:
                anchor2 = 'ls'
                draw.text((x2_draw_left_edge, y_baseline), file_name2,
                          fill=text_color, font=font, anchor=anchor2)
        except Exception as e:
            logger.error(f'Error processing or drawing filename 2 (vertical): {e}')


def _draw_horizontal_filenames(draw, font, file_name1, file_name2, split_position_on_canvas,
                               line_height, margin, image_rect: QRect, text_color, get_text_size_func):
    center_x = image_rect.left() + image_rect.width() // 2
    base_h_margin = max(3, margin * 3 // 8)
    min_margin = 0
    
    if file_name1:
        draw_text1 = True
        try:
            text_width1, text_height1 = get_text_size_func(
                file_name1, font, draw_context=draw)
            
            space_to_top_edge = (split_position_on_canvas - line_height // 2) - image_rect.top()
            actual_text_margin1 = base_h_margin
            if text_height1 + base_h_margin > space_to_top_edge:
                actual_text_margin1 = max(
                    min_margin, space_to_top_edge - text_height1)
                if space_to_top_edge - text_height1 < min_margin:
                    draw_text1 = False
            
            y1_draw_bottom_edge = split_position_on_canvas - \
                line_height // 2 - actual_text_margin1
            
            y1_actual_top_text_edge = y1_draw_bottom_edge - text_height1
            if y1_actual_top_text_edge < image_rect.top():
                draw_text1 = False

            if draw_text1:
                anchor1 = 'mb'
                draw.text((center_x, y1_draw_bottom_edge), file_name1,
                          fill=text_color, font=font, anchor=anchor1)
        except Exception as e:
            logger.error(f'Error processing or drawing filename 1 (horizontal): {e}')

    if file_name2:
        draw_text2 = True
        try:
            text_width2, text_height2 = get_text_size_func(
                file_name2, font, draw_context=draw)

            y_separator_bottom_edge = split_position_on_canvas + \
                (line_height + 1) // 2
            space_below_line = image_rect.bottom() - y_separator_bottom_edge
            
            actual_text_margin2 = base_h_margin
            if text_height2 + base_h_margin > space_below_line:
                if text_height2 + min_margin <= space_below_line:
                    actual_text_margin2 = min_margin
                else:
                    draw_text2 = False
            
            if draw_text2:
                y2_draw_coord_mb = y_separator_bottom_edge + actual_text_margin2 + text_height2
                if y2_draw_coord_mb > image_rect.bottom():
                    draw_text2 = False
                
                if draw_text2:
                    anchor2 = 'mb'
                    draw.text((center_x, y2_draw_coord_mb), file_name2,
                          fill=text_color, font=font, anchor=anchor2)
        except Exception as e:
            logger.error(f'Error processing or drawing filename 2 (horizontal): {e}')


def draw_split_line_pil(image_to_draw_on: Image.Image, split_position_ratio: float,
                        is_horizontal: bool, line_thickness: int = 3, blend_alpha: float = 0.5):
    if not isinstance(image_to_draw_on, Image.Image):
        return
    if image_to_draw_on.mode != 'RGBA':
        try:
            image_to_draw_on = image_to_draw_on.convert('RGBA')
        except Exception as e:
            logger.error(f'Error converting image_to_draw_on to RGBA: {e}')
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
            draw.rectangle([line_left, 0, line_right - 1,
                           height - 1], fill=line_color)
    else:
        split_y = int(round(height * split_position_ratio))
        line_top = max(0, split_y - line_thickness // 2)
        line_bottom = min(height, split_y + (line_thickness + 1) // 2)
        if line_bottom > line_top and line_thickness > 0:
            draw.rectangle(
                [0, line_top, width - 1, line_bottom - 1], fill=line_color)


MIN_CAPTURE_THICKNESS = AppConstants.MIN_CAPTURE_THICKNESS
MAX_CAPTURE_THICKNESS = AppConstants.MAX_CAPTURE_THICKNESS
CAPTURE_THICKNESS_FACTOR = 0.35
MIN_MAG_BORDER_THICKNESS = AppConstants.MIN_MAG_BORDER_THICKNESS
MAX_MAG_BORDER_THICKNESS = AppConstants.MAX_MAG_BORDER_THICKNESS
MAG_BORDER_THICKNESS_FACTOR = 0.15

def draw_magnifier_pil(draw: ImageDraw.ImageDraw, image_to_draw_on: Image.Image, image1_for_crop: Image.Image, image2_for_crop: Image.Image, capture_pos1: QPoint, capture_pos2: QPoint, capture_size_orig1: int,
                       capture_size_orig2: int, magnifier_midpoint_target: QPoint, magnifier_size_pixels: int, edge_spacing_pixels: int, interpolation_method: str, is_horizontal: bool, 
                       force_combine: bool, is_interactive_render: bool = False):
    if not image1_for_crop or not image2_for_crop or (not capture_pos1) or (
            not capture_pos2) or (not magnifier_midpoint_target):
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
        return
    if not isinstance(image_to_draw_on, Image.Image):
        return
    if image_to_draw_on.mode != 'RGBA':
        try:
            image_to_draw_on = image_to_draw_on.convert('RGBA')
        except Exception as e:
            logger.error(f'Error converting image_to_draw_on to RGBA: {e}')
            return
    
    should_combine = force_combine
    
    if should_combine:
        draw_combined_magnifier_circle_pil(
            target_image=image_to_draw_on,
            display_center_pos=magnifier_midpoint_target,
            capture_center1=capture_pos1, capture_center2=capture_pos2,
            capture_size1=capture_size_orig1, capture_size2=capture_size_orig2,
            magnifier_size_pixels=magnifier_size_pixels,
            image1_for_crop=image1_for_crop, image2_for_crop=image2_for_crop,
            interpolation_method=interpolation_method,
            is_horizontal=is_horizontal,
            is_interactive_render=is_interactive_render)
    else:
        radius = float(magnifier_size_pixels) / 2.0
        half_spacing = float(edge_spacing_pixels) / 2.0
        offset_from_midpoint = radius + half_spacing
        mid_x = float(magnifier_midpoint_target.x())
        mid_y = float(magnifier_midpoint_target.y())
        left_center = QPoint(int(round(mid_x - offset_from_midpoint)), int(round(mid_y)))
        right_center = QPoint(int(round(mid_x + offset_from_midpoint)), int(round(mid_y)))
        
        draw_single_magnifier_circle_pil(
            target_image=image_to_draw_on,
            display_center_pos=left_center,
            capture_center_orig=capture_pos1,
            capture_size_orig=capture_size_orig1,
            magnifier_size_pixels=magnifier_size_pixels,
            image_for_crop=image1_for_crop,
            interpolation_method=interpolation_method,
            is_interactive_render=is_interactive_render)
        draw_single_magnifier_circle_pil(
            target_image=image_to_draw_on,
            display_center_pos=right_center,
            capture_center_orig=capture_pos2,
            capture_size_orig=capture_size_orig2,
            magnifier_size_pixels=magnifier_size_pixels,
            image_for_crop=image2_for_crop,
            interpolation_method=interpolation_method,
            is_interactive_render=is_interactive_render)

def draw_capture_area_pil(image_to_draw_on: Image.Image,
                          center_pos: QPoint, size: int):
    if size <= 0 or center_pos is None or not isinstance(
            image_to_draw_on, Image.Image):
        return

    thickness_float = CAPTURE_THICKNESS_FACTOR * \
        math.sqrt(max(1.0, float(size)))
    thickness_clamped = max(
        float(MIN_CAPTURE_THICKNESS), min(
            float(MAX_CAPTURE_THICKNESS), thickness_float))
    thickness = max(2, int(round(thickness_clamped)))

    outer_size = size
    inner_size = size - thickness * 2
    if inner_size <= 0:
        return

    try:
        outer_mask = get_smooth_circular_mask(outer_size)
        if not outer_mask:
            return

        inner_mask_on_canvas = Image.new('L', (outer_size, outer_size), 0)
        inner_mask_small = get_smooth_circular_mask(inner_size)
        if not inner_mask_small:
            return
        inner_mask_on_canvas.paste(inner_mask_small, (thickness, thickness))

        donut_mask = ImageChops.subtract(outer_mask, inner_mask_on_canvas)
    except Exception as e:
        logger.error(f'Error creating donut mask for capture area: {e}')
        return

    ring_color = (255, 50, 100, 230)

    pastel_red_ring = Image.new('RGBA', (outer_size, outer_size), ring_color)

    paste_pos_x = center_pos.x() - outer_size // 2
    paste_pos_y = center_pos.y() - outer_size // 2

    try:
        image_to_draw_on.paste(
            pastel_red_ring, (paste_pos_x, paste_pos_y), donut_mask)
    except Exception as e:
        logger.error(f'Error in draw_capture_area_pil (pasting): {e}')

def draw_combined_magnifier_circle_pil(
    target_image: Image.Image,
    display_center_pos: QPoint,
    capture_center1: QPoint, capture_center2: QPoint,
    capture_size1: int, capture_size2: int,
    magnifier_size_pixels: int,
    image1_for_crop: Image.Image, image2_for_crop: Image.Image,
    interpolation_method: str, 
    is_horizontal: bool,
    is_interactive_render: bool = False
):
    if not all([image1_for_crop, image2_for_crop, capture_size1 > 0, capture_size2 > 0, magnifier_size_pixels > 0]):
        return

    try:
        resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)
        
        border_width = max(2, int(magnifier_size_pixels * 0.015))
        content_size = magnifier_size_pixels - border_width * 2
        if content_size <= 0: return

        thickness1_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(capture_size1)))
        thickness1 = max(2, int(round(max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness1_float)))))
        effective_capture_size1 = max(1, capture_size1 - thickness1 * 2)
        
        capture_radius1 = effective_capture_size1 // 2
        crop_box1 = (max(0, capture_center1.x() - capture_radius1), max(0, capture_center1.y() - capture_radius1),
                     min(image1_for_crop.width, capture_center1.x() + capture_radius1), min(image1_for_crop.height, capture_center1.y() + capture_radius1))
        scaled_content1 = image1_for_crop.crop(crop_box1).resize((content_size, content_size), resampling_method)

        thickness2_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(capture_size2)))
        thickness2 = max(2, int(round(max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness2_float)))))
        effective_capture_size2 = max(1, capture_size2 - thickness2 * 2)

        capture_radius2 = effective_capture_size2 // 2
        crop_box2 = (max(0, capture_center2.x() - capture_radius2), max(0, capture_center2.y() - capture_radius2),
                     min(image2_for_crop.width, capture_center2.x() + capture_radius2), min(image2_for_crop.height, capture_center2.y() + capture_radius2))
        scaled_content2 = image2_for_crop.crop(crop_box2).resize((content_size, content_size), resampling_method)
        
        content_mask = get_smooth_circular_mask(content_size)
        if not content_mask: return
        
        scaled_content1.putalpha(content_mask)
        scaled_content2.putalpha(content_mask)

        border_mask = get_smooth_circular_mask(magnifier_size_pixels)
        if not border_mask: return
        white_fill = Image.new('RGB', (magnifier_size_pixels, magnifier_size_pixels), (255, 255, 255))
        final_magnifier_widget = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
        final_magnifier_widget.paste(white_fill, (0, 0), border_mask)
        
        content_paste_pos = border_width
        
        if not is_horizontal:
            half_content_width = content_size // 2
            
            left_half = scaled_content1.crop((0, 0, half_content_width, content_size))
            right_half = scaled_content2.crop((half_content_width, 0, content_size, content_size))
            
            final_magnifier_widget.paste(left_half, (content_paste_pos, content_paste_pos), mask=left_half)
            final_magnifier_widget.paste(right_half, (content_paste_pos + half_content_width, content_paste_pos), mask=right_half)
            line_thickness = max(1, int(border_width / 2))
            center_x = magnifier_size_pixels // 2
            line_x_start = center_x - line_thickness // 2
            line_x_end = line_x_start + line_thickness
            
            line_image = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
            ImageDraw.Draw(line_image).rectangle(
                (line_x_start, 0, line_x_end - 1, magnifier_size_pixels),
                fill=(255, 255, 255, 230)
            )
        else:
            half_content_height = content_size // 2

            top_half = scaled_content1.crop((0, 0, content_size, half_content_height))
            bottom_half = scaled_content2.crop((0, half_content_height, content_size, content_size))

            final_magnifier_widget.paste(top_half, (content_paste_pos, content_paste_pos), mask=top_half)
            final_magnifier_widget.paste(bottom_half, (content_paste_pos, content_paste_pos + half_content_height), mask=bottom_half)

            line_thickness = max(1, int(border_width / 2))
            center_y = magnifier_size_pixels // 2
            line_y_start = center_y - line_thickness // 2
            line_y_end = line_y_start + line_thickness

            line_image = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0,0,0,0))
            ImageDraw.Draw(line_image).rectangle(
                (0, line_y_start, magnifier_size_pixels, line_y_end - 1),
                fill=(255, 255, 255, 230)
            )
            
        line_mask_canvas = Image.new('L', (magnifier_size_pixels, magnifier_size_pixels), 0)
        line_mask_canvas.paste(content_mask, (content_paste_pos, content_paste_pos))
        line_image.putalpha(ImageChops.multiply(line_image.getchannel('A'), line_mask_canvas))
        final_magnifier_widget.alpha_composite(line_image, (0,0))
        
        paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
        paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
        target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

    except Exception as e:
        logger.error(f'Error in draw_combined_magnifier_circle_pil: {e}')
        traceback.print_exc()


def draw_single_magnifier_circle_pil(
    target_image: Image.Image, 
    display_center_pos: QPoint, 
    capture_center_orig: QPoint,
    capture_size_orig: int, 
    magnifier_size_pixels: int, 
    image_for_crop: Image.Image, 
    interpolation_method: str, 
    is_interactive_render: bool = False
):
    if not isinstance(image_for_crop, Image.Image) or capture_size_orig <= 0 or magnifier_size_pixels <= 0:
        return

    try:
        resampling_method = get_pil_resampling_method(interpolation_method, is_interactive_render)

        border_width = max(2, int(magnifier_size_pixels * 0.015))
        content_size = magnifier_size_pixels - border_width * 2
        if content_size <= 0: return

        thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(capture_size_orig)))
        thickness = max(2, int(round(max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float)))))
        effective_capture_size = max(1, capture_size_orig - thickness * 2)
        
        capture_radius = effective_capture_size // 2
        crop_box = (
            max(0, capture_center_orig.x() - capture_radius), max(0, capture_center_orig.y() - capture_radius),
            min(image_for_crop.width, capture_center_orig.x() + capture_radius), min(image_for_crop.height, capture_center_orig.y() + capture_radius)
        )
        scaled_content = image_for_crop.crop(crop_box).resize((content_size, content_size), resampling_method)
        
        content_mask = get_smooth_circular_mask(content_size)
        if not content_mask: return
        scaled_content.putalpha(content_mask)

        border_mask = get_smooth_circular_mask(magnifier_size_pixels)
        if not border_mask: return
        white_fill = Image.new('RGB', (magnifier_size_pixels, magnifier_size_pixels), (255, 255, 255))
        final_magnifier_widget = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
        final_magnifier_widget.paste(white_fill, (0, 0), border_mask)
        
        content_paste_pos = border_width
        final_magnifier_widget.alpha_composite(scaled_content, (content_paste_pos, content_paste_pos))
        
        paste_x = display_center_pos.x() - (magnifier_size_pixels // 2)
        paste_y = display_center_pos.y() - (magnifier_size_pixels // 2)
        target_image.alpha_composite(final_magnifier_widget, (paste_x, paste_y))

    except Exception as e:
        logger.error(f'Error during single magnifier drawing: {e}')
        traceback.print_exc()
        return

def generate_comparison_image_with_canvas(
    app_state, image1_scaled: Image.Image, image2_scaled: Image.Image,
    original_image1: Image.Image, original_image2: Image.Image,
    magnifier_drawing_coords: tuple | None,
    font_path_absolute: str, file_name1_text: str, file_name2_text: str
) -> Tuple[Image.Image | None, int, int]:
    if not image1_scaled or not image2_scaled:
        return None, 0, 0

    img_w, img_h = image1_scaled.size

    padding_left, padding_right, padding_top, padding_bottom = 0, 0, 0, 0
    if app_state.use_magnifier and magnifier_drawing_coords:
        magnifier_bbox = magnifier_drawing_coords[-1]
        if not magnifier_bbox.isNull() and magnifier_bbox.isValid():
            if magnifier_bbox.left() < 0:
                padding_left = abs(magnifier_bbox.left())
            if magnifier_bbox.right() > img_w:
                padding_right = magnifier_bbox.right() - img_w
            if magnifier_bbox.top() < 0:
                padding_top = abs(magnifier_bbox.top())
            if magnifier_bbox.bottom() > img_h:
                padding_bottom = magnifier_bbox.bottom() - img_h

    canvas_w = img_w + padding_left + padding_right
    canvas_h = img_h + padding_top + padding_bottom
    final_canvas = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    image_paste_pos_on_canvas = (padding_left, padding_top)

    base_image_pil = create_base_split_image_pil(
        image1_scaled, image2_scaled,
        app_state.split_position_visual,
        app_state.is_horizontal
    )

    if not base_image_pil:
        return None, 0, 0
    final_canvas.paste(base_image_pil, image_paste_pos_on_canvas)

    if app_state.use_magnifier and magnifier_drawing_coords and app_state.show_capture_area_on_main_image:
        cap_center1, cap_center2, cap_size1, cap_size2, magn_mid_on_img, magn_size_pix, magn_spacing_pix, _ = magnifier_drawing_coords

        orig_w, orig_h = original_image1.size
        scale_ratio = min(img_w, img_h) / min(orig_w, orig_h) if min(orig_w, orig_h) > 0 else 0
        cap_marker_size = max(5, int(round(cap_size1 * scale_ratio)))
        cap_marker_radius = cap_marker_size // 2
        
        raw_cap_marker_x_on_canvas = padding_left + \
            int(round(app_state.capture_position_relative.x() * img_w))
        raw_cap_marker_y_on_canvas = padding_top + \
            int(round(app_state.capture_position_relative.y() * img_h))

        min_x = padding_left + cap_marker_radius
        max_x = padding_left + img_w - cap_marker_radius
        min_y = padding_top + cap_marker_radius
        max_y = padding_top + img_h - cap_marker_radius

        clamped_x = max(min_x, min(raw_cap_marker_x_on_canvas, max_x))
        clamped_y = max(min_y, min(raw_cap_marker_y_on_canvas, max_y))
        
        draw_capture_area_pil(
            final_canvas,
            QPoint(
                clamped_x,
                clamped_y),
            cap_marker_size)

    canvas_draw = ImageDraw.Draw(final_canvas)
    
    line_thickness = max(1, int(min(img_w, img_h) * 0.005))
    line_thickness = min(line_thickness, 7)

    if not app_state.is_horizontal:
        split_x_on_canvas = padding_left + \
            int(round(img_w * app_state.split_position_visual))
        canvas_draw.rectangle([split_x_on_canvas -
                               line_thickness //
                               2, padding_top, split_x_on_canvas +
                               (line_thickness +
                                1) //
                               2 -
                               1, padding_top +
                               img_h -
                               1], fill=(255, 255, 255, 255))
    else:
        split_y_on_canvas = padding_top + \
            int(round(img_h * app_state.split_position_visual))
        canvas_draw.rectangle([padding_left,
                               split_y_on_canvas - line_thickness // 2,
                               padding_left + img_w - 1,
                               split_y_on_canvas + (line_thickness + 1) // 2 - 1],
                              fill=(255,
                                    255,
                                    255,
                                    255))
    
    if app_state.include_file_names_in_saved:
        image_rect_on_canvas = QRect(padding_left, padding_top, img_w, img_h)
        split_pos_abs_on_canvas = (padding_left + int(round(img_w * app_state.split_position_visual))
                                   if not app_state.is_horizontal
                                   else padding_top + int(round(img_h * app_state.split_position_visual)))
        draw_file_names_on_image(
            canvas_draw, image_rect_on_canvas,
            split_pos_abs_on_canvas,
            app_state.is_horizontal, line_thickness, font_path_absolute, app_state.font_size_percent, app_state.max_name_length,
            file_name1_text, file_name2_text, app_state.file_name_color.getRgb(
            ), app_state.is_interactive_mode
        )

    if app_state.use_magnifier and magnifier_drawing_coords:
        cap_center1, cap_center2, cap_size1, cap_size2, magn_mid_on_img, magn_size_pix, magn_spacing_pix, _ = magnifier_drawing_coords

        magn_mid_on_canvas = QPoint(
            magn_mid_on_img.x() + padding_left,
            magn_mid_on_img.y() + padding_top)

        should_combine_decision = app_state.magnifier_spacing_relative_visual < 0.001

        draw_magnifier_pil(
            canvas_draw, final_canvas,
            original_image1, original_image2,
            cap_center1, cap_center2, cap_size1, cap_size2,
            magn_mid_on_canvas, magn_size_pix, magn_spacing_pix,
            app_state.interpolation_method, 
            app_state.is_horizontal,
            should_combine_decision,
            app_state.is_interactive_mode
        )

    return final_canvas, padding_left, padding_top

def create_base_split_image_pil(image1_processed: Image.Image, image2_processed: Image.Image,
                                split_position_visual: float, is_horizontal: bool) -> Image.Image | None:
    if not image1_processed or not image2_processed:
        return None
    if image1_processed.mode != 'RGBA':
        image1_processed = image1_processed.convert('RGBA')
    if image2_processed.mode != 'RGBA':
        image2_processed = image2_processed.convert('RGBA')
    if image1_processed.size != image2_processed.size:
        min_w = min(image1_processed.size[0], image2_processed.size[0])
        min_h = min(image1_processed.size[1], image2_processed.size[1])
        if min_w <= 0 or min_h <= 0:
            return None
        if image1_processed.size != (min_w, min_h):
            image1_processed = image1_processed.resize(
                (min_w, min_h), Image.Resampling.BILINEAR)
        if image2_processed.size != (min_w, min_h):
            image2_processed = image2_processed.resize(
                (min_w, min_h), Image.Resampling.BILINEAR)
        if image1_processed.size != image2_processed.size:
            return None
    width, height = image1_processed.size
    if width <= 0 or height <= 0:
        return None
    result = Image.new('RGBA', (width, height))
    try:
        if not is_horizontal:
            split_pos_abs = max(
                0, min(
                    width, int(
                        round(
                            width * split_position_visual))))
            if split_pos_abs > 0:
                result.paste(
                    image1_processed.crop(
                        (0, 0, split_pos_abs, height)), (0, 0))
            if split_pos_abs < width:
                result.paste(
                    image2_processed.crop(
                        (split_pos_abs, 0, width, height)), (split_pos_abs, 0))
        else:
            split_pos_abs = max(
                0, min(
                    height, int(
                        round(
                            height * split_position_visual))))
            if split_pos_abs > 0:
                result.paste(
                    image1_processed.crop(
                        (0, 0, width, split_pos_abs)), (0, 0))
            if split_pos_abs < height:
                result.paste(
                    image2_processed.crop(
                        (0, split_pos_abs, width, height)), (0, split_pos_abs))
    except Exception as e:
        logger.error(f'Error in create_base_split_image_pil during paste: {e}')
        traceback.print_exc()
        return None
    return result