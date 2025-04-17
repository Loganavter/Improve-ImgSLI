import os
import math
import traceback
from typing import Callable, Tuple, Union
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QPoint, QPointF, QSize
try:
    from translations import tr
except ImportError:
    print("Warning: 'translations.py' not found. Using fallback translation.")

    def tr(text, lang='en', *args, **kwargs):
        return text
MIN_CAPTURE_THICKNESS = 1
MAX_CAPTURE_THICKNESS = 4
CAPTURE_THICKNESS_FACTOR = 0.35
MIN_MAG_BORDER_THICKNESS = 1
MAX_MAG_BORDER_THICKNESS = 4
MAG_BORDER_THICKNESS_FACTOR = 0.15
FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]

def truncate_text(raw_text: str, available_width: int, max_len: int, font_instance: FontType, get_size_func: GetSizeFuncType) -> str:
    original_len = len(raw_text)
    max_len = max(1, max_len)
    if original_len == 0:
        return ''
    if original_len <= max_len:
        try:
            text_w, _ = get_size_func(raw_text, font_instance)
            if text_w <= available_width:
                return raw_text
        except Exception as e:
            print(f"Error measuring initial text '{raw_text}': {e}")
    current_len_base = min(original_len, max_len - 1)
    while current_len_base >= 0:
        current_base_text = raw_text[:current_len_base]
        chars_removed_total = original_len - current_len_base
        if chars_removed_total <= 0:
            ellipsis_symbol = ''
        elif chars_removed_total == 1:
            ellipsis_symbol = '.'
        elif chars_removed_total == 2:
            ellipsis_symbol = '..'
        else:
            ellipsis_symbol = '...'
        processed_text = current_base_text + ellipsis_symbol
        if len(processed_text) > max_len:
            base_chars_allowed = max(0, max_len - len(ellipsis_symbol))
            current_base_text = raw_text[:base_chars_allowed]
            processed_text = current_base_text + ellipsis_symbol
            current_len_base = len(current_base_text)
            if current_len_base == 0 and len(ellipsis_symbol) > max_len:
                if max_len >= 1:
                    ellipsis_symbol = '.'
                    processed_text = ellipsis_symbol
                else:
                    return ''
        try:
            text_w, _ = get_size_func(processed_text, font_instance)
        except Exception as e:
            print(f"Error in get_size_func for '{processed_text}': {e}")
            text_w = available_width + 1
        if text_w <= available_width:
            return processed_text
        else:
            current_len_base -= 1
    return ''

def get_scaled_pixmap_dimensions(app):
    source_image = app.result_image if app.result_image else app.original_image1
    if not source_image or not hasattr(source_image, 'size'):
        return (0, 0)
    label_width = app.image_label.width()
    label_height = app.image_label.height()
    if label_width <= 0 or label_height <= 0:
        return (0, 0)
    try:
        orig_width, orig_height = source_image.size
    except Exception as e:
        print(f'Error getting source image size: {e}')
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

def get_original_coords(app, drawing_width, drawing_height, display_width, display_height, use_visual_offset):
    if not app.original_image1 or not app.original_image2:
        return (None,) * 7
    if drawing_width <= 0 or drawing_height <= 0 or display_width <= 0 or (display_height <= 0):
        return (None,) * 7
    try:
        orig1_width, orig1_height = app.original_image1.size
        orig2_width, orig2_height = app.original_image2.size
    except Exception as e:
        print(f'Error getting original image sizes: {e}')
        return (None,) * 7
    if orig1_width <= 0 or orig1_height <= 0 or orig2_width <= 0 or (orig2_height <= 0):
        return (None,) * 7
    capture_rel_x = app.capture_position_relative.x()
    capture_rel_y = app.capture_position_relative.y()
    cap1_center_orig_x = max(0, min(orig1_width - 1, int(capture_rel_x * orig1_width)))
    cap1_center_orig_y = max(0, min(orig1_height - 1, int(capture_rel_y * orig1_height)))
    capture_center_orig1 = QPoint(cap1_center_orig_x, cap1_center_orig_y)
    cap2_center_orig_x = max(0, min(orig2_width - 1, int(capture_rel_x * orig2_width)))
    cap2_center_orig_y = max(0, min(orig2_height - 1, int(capture_rel_y * orig2_height)))
    capture_center_orig2 = QPoint(cap2_center_orig_x, cap2_center_orig_y)
    orig1_min_dim = min(orig1_width, orig1_height) if orig1_width > 0 and orig1_height > 0 else 1
    orig2_min_dim = min(orig2_width, orig2_height) if orig2_width > 0 and orig2_height > 0 else 1
    capture_size_orig1_int = max(10, int(round(app.capture_size_relative * orig1_min_dim)))
    capture_size_orig2_int = max(10, int(round(app.capture_size_relative * orig2_min_dim)))
    magnifier_midpoint_drawing = None
    magnifier_size_pixels_drawing = 0
    edge_spacing_pixels_drawing = 0
    if app.use_magnifier:
        cap_center_drawing_x = max(0.0, min(float(drawing_width - 1), capture_rel_x * float(drawing_width)))
        cap_center_drawing_y = max(0.0, min(float(drawing_height - 1), capture_rel_y * float(drawing_height)))
        cap_center_drawing = QPointF(cap_center_drawing_x, cap_center_drawing_y)
        target_min_dim_display = float(min(display_width, display_height))
        magnifier_size_pixels_display = max(10.0, app.magnifier_size_relative * target_min_dim_display)
        spacing_relative = app.magnifier_spacing_relative_visual if use_visual_offset else app.magnifier_spacing_relative
        edge_spacing_pixels_display = max(0.0, spacing_relative * magnifier_size_pixels_display)
        scale_factor_w = float(drawing_width) / float(display_width) if display_width > 0 else 1.0
        scale_factor_h = float(drawing_height) / float(display_height) if display_height > 0 else 1.0
        scale_factor_for_size = min(scale_factor_w, scale_factor_h)
        magnifier_size_pixels_drawing = max(10, int(round(magnifier_size_pixels_display * scale_factor_for_size)))
        edge_spacing_pixels_drawing = max(0, int(round(edge_spacing_pixels_display * scale_factor_for_size)))
        if app.freeze_magnifier:
            if app.frozen_magnifier_position_relative is not None:
                frozen_rel_x = max(0.0, min(1.0, app.frozen_magnifier_position_relative.x()))
                frozen_rel_y = max(0.0, min(1.0, app.frozen_magnifier_position_relative.y()))
                magn_center_drawing_x = max(0.0, min(float(drawing_width - 1), frozen_rel_x * float(drawing_width)))
                magn_center_drawing_y = max(0.0, min(float(drawing_height - 1), frozen_rel_y * float(drawing_height)))
                magnifier_midpoint_drawing = QPoint(int(round(magn_center_drawing_x)), int(round(magn_center_drawing_y)))
            else:
                magnifier_midpoint_drawing = QPoint(int(round(cap_center_drawing.x())), int(round(cap_center_drawing.y())))
        else:
            offset_relative = app.magnifier_offset_relative_visual if use_visual_offset else app.magnifier_offset_relative
            REFERENCE_MAGNIFIER_RELATIVE_SIZE = app.DEFAULT_MAGNIFIER_SIZE_RELATIVE
            reference_magnifier_size_display = max(10.0, REFERENCE_MAGNIFIER_RELATIVE_SIZE * target_min_dim_display)
            offset_pixels_display_ref_x = offset_relative.x() * reference_magnifier_size_display
            offset_pixels_display_ref_y = offset_relative.y() * reference_magnifier_size_display
            offset_pixels_drawing_x = offset_pixels_display_ref_x * scale_factor_w
            offset_pixels_drawing_y = offset_pixels_display_ref_y * scale_factor_h
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
    return (capture_center_orig1, capture_center_orig2, capture_size_orig1_int, capture_size_orig2_int, magnifier_midpoint_drawing, magnifier_size_pixels_drawing, edge_spacing_pixels_drawing)

def resize_images_processor(app):
    if not app.original_image1 or not app.original_image2:
        app.image1 = None
        app.image2 = None
        return
    try:
        orig1_w, orig1_h = app.original_image1.size
        orig2_w, orig2_h = app.original_image2.size
    except Exception as e:
        print(f'Error getting original image sizes in resize: {e}')
        app.image1 = None
        app.image2 = None
        return
    max_width = max(orig1_w, orig2_w)
    max_height = max(orig1_h, orig2_h)
    need_resize1 = app.original_image1.size != (max_width, max_height)
    need_resize2 = app.original_image2.size != (max_width, max_height)
    need_convert1 = app.original_image1.mode != 'RGBA'
    need_convert2 = app.original_image2.mode != 'RGBA'
    try:
        img1_temp = app.original_image1
        if need_resize1:
            img1_temp = img1_temp.resize((max_width, max_height), Image.Resampling.LANCZOS)
        if need_convert1 or (need_resize1 and img1_temp.mode != 'RGBA'):
            img1_temp = img1_temp.convert('RGBA')
        app.image1 = img1_temp.copy() if need_resize1 or need_convert1 else img1_temp
        img2_temp = app.original_image2
        if need_resize2:
            img2_temp = img2_temp.resize((max_width, max_height), Image.Resampling.LANCZOS)
        if need_convert2 or (need_resize2 and img2_temp.mode != 'RGBA'):
            img2_temp = img2_temp.convert('RGBA')
        app.image2 = img2_temp.copy() if need_resize2 or need_convert2 else img2_temp
    except Exception as e:
        app.image1 = None
        app.image2 = None
        print(f'ERROR during resize_images_processor: {e}')
        traceback.print_exc()

def update_comparison_processor(app):
    print('DEBUG: update_comparison_processor called.')
    if not app.image1 or not app.image2:
        print('DEBUG: update_comp: One or both app.image1/2 are None. Clearing label.')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.result_image = None
        app.pixmap_width = 0
        app.pixmap_height = 0
        return
    if app.image1.size != app.image2.size:
        print(f'ERROR: Mismatched image sizes in update_comparison_processor: {app.image1.size} vs {app.image2.size}. Retrying resize.')
        resize_images_processor(app)
        if not app.image1 or not app.image2 or app.image1.size != app.image2.size:
            print('ERROR: Mismatched sizes persist after resize attempt. Aborting update.')
            if hasattr(app.image_label, 'clear'):
                app.image_label.clear()
            app.result_image = None
            app.pixmap_width = 0
            app.pixmap_height = 0
            return
    img1_rgba = app.image1
    img2_rgba = app.image2
    width, height = img1_rgba.size
    result = Image.new('RGBA', (width, height))
    split_pos_abs = 0
    try:
        print(f'DEBUG: update_comp: Split pos = {app.split_position:.4f}, Horizontal = {app.is_horizontal}, Size = {width}x{height}')
        if not app.is_horizontal:
            split_pos_abs = max(0, min(width, int(round(width * app.split_position))))
            if split_pos_abs > 0:
                result.paste(img1_rgba.crop((0, 0, split_pos_abs, height)), (0, 0))
            if split_pos_abs < width:
                result.paste(img2_rgba.crop((split_pos_abs, 0, width, height)), (split_pos_abs, 0))
        else:
            split_pos_abs = max(0, min(height, int(round(height * app.split_position))))
            if split_pos_abs > 0:
                result.paste(img1_rgba.crop((0, 0, width, split_pos_abs)), (0, 0))
            if split_pos_abs < height:
                result.paste(img2_rgba.crop((0, split_pos_abs, width, height)), (0, split_pos_abs))
        app.result_image = result
        print('DEBUG: update_comp: app.result_image created successfully.')
        display_result_processor(app)
    except ValueError as ve:
        print(f'ERROR in update_comparison_processor during paste (ValueError): {ve}')
        print(f'  is_horizontal={app.is_horizontal}, size={width}x{height}, split_pos_ratio={app.split_position:.3f}, split_pos_abs={split_pos_abs}')
        app.result_image = None
        print('DEBUG: update_comp: app.result_image set to None due to paste error.')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width = 0
        app.pixmap_height = 0
    except Exception as e:
        print(f'ERROR in update_comparison_processor: {e}')
        traceback.print_exc()
        app.result_image = None
        print('DEBUG: update_comp: app.result_image set to None due to general error.')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width = 0
        app.pixmap_height = 0

def draw_split_line_pil(image_to_draw_on, image1_param, image2_param, split_position_ratio, is_horizontal, line_thickness=3, blend_alpha=0.5):
    if not image_to_draw_on or not image1_param or (not image2_param):
        print('Warning: draw_split_line_pil received None image.')
        return
    if not hasattr(image_to_draw_on, 'size') or not hasattr(image1_param, 'size') or (not hasattr(image2_param, 'size')):
        print('Warning: draw_split_line_pil received non-Image object.')
        return
    if image1_param.size != image2_param.size or image1_param.size != image_to_draw_on.size:
        print(f'Warning: Mismatched sizes in draw_split_line_pil: target={image_to_draw_on.size}, img1={image1_param.size}, img2={image2_param.size}')
        return
    image1 = image1_param
    if image1.mode != 'RGBA':
        try:
            image1 = image1.convert('RGBA')
        except Exception as e:
            print(f'Error converting image1 to RGBA for blend: {e}')
            return
    image2 = image2_param
    if image2.mode != 'RGBA':
        try:
            image2 = image2.convert('RGBA')
        except Exception as e:
            print(f'Error converting image2 to RGBA for blend: {e}')
            return
    if image_to_draw_on.mode != 'RGBA':
        print('Warning: draw_split_line_pil - image_to_draw_on is not RGBA. Attempting conversion.')
        try:
            image_to_draw_on.putalpha(255)
            if image_to_draw_on.mode != 'RGBA':
                temp_copy = image_to_draw_on.convert('RGBA')
                image_to_draw_on.paste(temp_copy)
                print('Warning: Converted target image to RGBA in draw_split_line_pil.')
        except Exception as e:
            print(f'ERROR converting target image to RGBA in draw_split_line_pil: {e}')
            return
    width, height = image_to_draw_on.size
    if width <= 0 or height <= 0:
        print(f'Warning: image_to_draw_on has zero dimension ({width}x{height}) in draw_split_line_pil.')
        return
    line_thickness = max(1, int(round(line_thickness)))
    half_thickness_floor = line_thickness // 2
    half_thickness_ceil = (line_thickness + 1) // 2
    line_x0, line_y0, line_x1, line_y1 = (0, 0, 0, 0)
    paste_pos = (0, 0)
    bbox = (0, 0, 0, 0)
    try:
        if not is_horizontal:
            split_x = int(round(width * split_position_ratio))
            split_x = max(half_thickness_floor, min(width - half_thickness_ceil, split_x))
            line_x0 = split_x - half_thickness_floor
            line_x1 = split_x + half_thickness_ceil
            line_y0 = 0
            line_y1 = height
            bbox = (line_x0, line_y0, line_x1, line_y1)
            paste_pos = (line_x0, line_y0)
        else:
            split_y = int(round(height * split_position_ratio))
            split_y = max(half_thickness_floor, min(height - half_thickness_ceil, split_y))
            line_y0 = split_y - half_thickness_floor
            line_y1 = split_y + half_thickness_ceil
            line_x0 = 0
            line_x1 = width
            bbox = (line_x0, line_y0, line_x1, line_y1)
            paste_pos = (line_x0, line_y0)
        if bbox[0] >= bbox[2] or bbox[1] >= bbox[3]:
            print(f'Warning: Invalid bbox calculated in draw_split_line_pil: {bbox}. Skipping blend.')
            return
        crop1 = image1.crop(bbox)
        crop2 = image2.crop(bbox)
        blended_crop = Image.blend(crop1, crop2, alpha=blend_alpha)
        image_to_draw_on.paste(blended_crop, paste_pos, mask=blended_crop)
    except ValueError as ve:
        print(f'ERROR in draw_split_line_pil blending (ValueError): {ve}')
        print(f'  bbox: {bbox}, paste_pos: {paste_pos}, image_size: {width}x{height}, line_thickness: {line_thickness}, is_horizontal={is_horizontal}')
    except IndexError as ie:
        print(f'ERROR in draw_split_line_pil blending (IndexError - often related to crop): {ie}')
        print(f'  bbox: {bbox}, image1 size: {image1.size}, image2 size: {image2.size}')
    except Exception as e:
        print(f'ERROR in draw_split_line_pil blending: {e}')
        traceback.print_exc()

def display_result_processor(app):
    if not app.image1 or not app.image2:
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.result_image = None
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    if app.image1.size != app.image2.size:
        print(f'ERROR in display_result_processor: Mismatched sizes: {app.image1.size} vs {app.image2.size}. Aborting display.')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.result_image = None
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    img1_rgba = app.image1
    img2_rgba = app.image2
    width, height = img1_rgba.size
    result = Image.new('RGBA', (width, height))
    split_pos_abs = 0
    try:
        if not app.is_horizontal:
            split_pos_abs = max(0, min(width, int(round(width * app.split_position))))
            if split_pos_abs > 0:
                result.paste(img1_rgba.crop((0, 0, split_pos_abs, height)), (0, 0))
            if split_pos_abs < width:
                result.paste(img2_rgba.crop((split_pos_abs, 0, width, height)), (split_pos_abs, 0))
        else:
            split_pos_abs = max(0, min(height, int(round(height * app.split_position))))
            if split_pos_abs > 0:
                result.paste(img1_rgba.crop((0, 0, width, split_pos_abs)), (0, 0))
            if split_pos_abs < height:
                result.paste(img2_rgba.crop((0, split_pos_abs, width, height)), (0, split_pos_abs))
        app.result_image = result
    except ValueError as ve:
        print(f'ERROR in display_result_processor during paste (ValueError): {ve}')
        print(f'  is_horizontal={app.is_horizontal}, size={width}x{height}, split_pos_ratio={app.split_position:.3f}, split_pos_abs={split_pos_abs}')
        app.result_image = None
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    except Exception as e:
        print(f'ERROR in display_result_processor during paste (General): {e}')
        traceback.print_exc()
        app.result_image = None
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    try:
        image_to_display = app.result_image.copy()
        if image_to_display.mode != 'RGBA':
            print('Warning: display_result: Copied result_image is not RGBA, converting.')
            image_to_display = image_to_display.convert('RGBA')
    except Exception as e_copy:
        print(f'ERROR: Failed to copy/convert app.result_image: {e_copy}')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    orig_width, orig_height = image_to_display.size
    display_width, display_height = get_scaled_pixmap_dimensions(app)
    if display_width <= 0 or display_height <= 0:
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    target_display_size = QSize(display_width, display_height)
    app.pixmap_width = display_width
    app.pixmap_height = display_height
    overlay = Image.new('RGBA', (orig_width, orig_height), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)
    base_thickness_v = orig_width * 0.0035
    base_thickness_h = orig_height * 0.005
    line_thickness = max(1, min(10, int(round(base_thickness_v)))) if not app.is_horizontal else max(1, min(10, int(round(base_thickness_h))))
    line_color = (255, 255, 255, 70)
    half_thickness_floor = line_thickness // 2
    half_thickness_ceil = (line_thickness + 1) // 2
    try:
        if not app.is_horizontal:
            split_x = int(round(orig_width * app.split_position))
            split_x = max(half_thickness_floor, min(orig_width - half_thickness_ceil, split_x))
            line_x0 = split_x - half_thickness_floor
            line_y0 = 0
            line_x1_inc = split_x + half_thickness_ceil - 1
            line_y1_inc = orig_height - 1
            draw_overlay.rectangle([line_x0, line_y0, line_x1_inc, line_y1_inc], fill=line_color)
        else:
            split_y = int(round(orig_height * app.split_position))
            split_y = max(half_thickness_floor, min(orig_height - half_thickness_ceil, split_y))
            line_x0 = 0
            line_y0 = split_y - half_thickness_floor
            line_x1_inc = orig_width - 1
            line_y1_inc = split_y + half_thickness_ceil - 1
            draw_overlay.rectangle([line_x0, line_y0, line_x1_inc, line_y1_inc], fill=line_color)
    except Exception as e_line:
        print(f'Error drawing split line on overlay: {e_line}')
    if app.use_magnifier and app.original_image1 and app.original_image2:
        coords = get_original_coords(app, drawing_width=orig_width, drawing_height=orig_height, display_width=display_width, display_height=display_height, use_visual_offset=True)
        if coords and coords[0] is not None:
            capture_center_orig1, capture_center_orig2, capture_size_orig1, capture_size_orig2, magnifier_midpoint_drawing, magnifier_size_pixels_drawing, edge_spacing_pixels_drawing = coords
            cap_center_draw_x = int(round(app.capture_position_relative.x() * float(orig_width)))
            cap_center_draw_y = int(round(app.capture_position_relative.y() * float(orig_height)))
            capture_marker_center_drawing = QPoint(cap_center_draw_x, cap_center_draw_y)
            capture_marker_size_drawing = 10
            try:
                if app.original_image1 and app.original_image1.size[0] > 0 and (orig_width > 0):
                    scale_orig1_to_draw_w = float(orig_width) / float(app.original_image1.size[0])
                    capture_marker_size_drawing = max(5, int(round(capture_size_orig1 * scale_orig1_to_draw_w)))
            except Exception as e_scale:
                print(f'Warning: Error calculating capture marker scale: {e_scale}')
            draw_capture_area_pil(draw_overlay, capture_marker_center_drawing, capture_marker_size_drawing)
            if magnifier_midpoint_drawing:
                is_dragging_capture = getattr(app, '_is_dragging_capture_point', False)
                draw_magnifier_pil(draw_overlay, overlay, app.original_image1, app.original_image2, capture_center_orig1, capture_center_orig2, capture_size_orig1, capture_size_orig2, magnifier_midpoint_drawing, magnifier_size_pixels_drawing, edge_spacing_pixels_drawing, app, is_dragging=is_dragging_capture)
    try:
        image_to_display = Image.alpha_composite(image_to_display, overlay)
    except Exception as e_composite:
        print(f'ERROR during alpha_composite: {e_composite}')
    draw_final = ImageDraw.Draw(image_to_display)
    if hasattr(app, 'checkbox_file_names') and app.checkbox_file_names.isChecked():
        if not app.is_horizontal:
            split_position_abs_names = max(0, min(orig_width, int(round(orig_width * app.split_position))))
            line_width_names, line_height_names = (line_thickness, 0)
        else:
            split_position_abs_names = max(0, min(orig_height, int(round(orig_height * app.split_position))))
            line_width_names, line_height_names = (0, line_thickness)
        color_tuple = app.file_name_color.getRgb()
        draw_file_names_on_image(app, draw_final, image_to_display, split_position_abs_names, orig_width, orig_height, line_width_names, line_height_names, color_tuple)
    try:
        if image_to_display.mode != 'RGBA':
            print(f'ERROR: Final image mode is {image_to_display.mode} INSTEAD OF RGBA before QImage conversion!')
            image_to_display = image_to_display.convert('RGBA')
        qimage = QImage(image_to_display.tobytes('raw', 'RGBA'), orig_width, orig_height, QImage.Format.Format_RGBA8888)
        if qimage.isNull():
            raise ValueError('Failed to create QImage from PIL image bytes')
        pixmap = QPixmap.fromImage(qimage)
        if pixmap.isNull():
            raise ValueError('Failed to create QPixmap from QImage')
    except Exception as e_conv:
        print(f'Error converting final PIL image to QPixmap: {e_conv}')
        traceback.print_exc()
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)
        return
    if not pixmap.isNull():
        scaled_pixmap = pixmap.scaled(target_display_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        if scaled_pixmap.isNull():
            if hasattr(app.image_label, 'clear'):
                app.image_label.clear()
        else:
            app.image_label.setPixmap(scaled_pixmap)
    else:
        print('Warning: Final QPixmap is null before setting to label.')
        if hasattr(app.image_label, 'clear'):
            app.image_label.clear()
        app.pixmap_width, app.pixmap_height = (0, 0)

def draw_magnifier_pil(draw, image_to_draw_on, image1_for_crop, image2_for_crop, capture_pos1, capture_pos2, capture_size_orig1, capture_size_orig2, magnifier_midpoint_target, magnifier_size_pixels, edge_spacing_pixels, app, is_dragging=False):
    if not image1_for_crop or not image2_for_crop or (not capture_pos1) or (not capture_pos2) or (not magnifier_midpoint_target):
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
        return
    if not isinstance(image_to_draw_on, Image.Image):
        print('draw_magnifier_pil: image_to_draw_on is not a PIL Image.')
        return
    if image_to_draw_on.mode != 'RGBA':
        print('Warning: draw_magnifier_pil requires image_to_draw_on to be RGBA.')
        return
    result_width, result_height = image_to_draw_on.size
    if result_width <= 0 or result_height <= 0:
        print('draw_magnifier_pil: image_to_draw_on has zero dimensions.')
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
        draw_combined_magnifier_circle_pil(draw, image_to_draw_on, magnifier_midpoint_target, capture_pos1, capture_pos2, capture_size_orig1, capture_size_orig2, magnifier_size_pixels, image1_for_crop, image2_for_crop, is_dragging=is_dragging)
    else:
        draw_single_magnifier_circle_pil(draw, image_to_draw_on, left_center, capture_pos1, capture_size_orig1, magnifier_size_pixels, image1_for_crop, is_dragging=is_dragging)
        draw_single_magnifier_circle_pil(draw, image_to_draw_on, right_center, capture_pos2, capture_size_orig2, magnifier_size_pixels, image2_for_crop, is_dragging=is_dragging)

def draw_capture_area_pil(draw, center_pos, size):
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
        draw.ellipse(bbox_int, outline=(255, 0, 0, 155), width=thickness)
    except Exception as e:
        print(f'ERROR in draw_capture_area_pil: {e}. Bbox={bbox}, thickness={thickness}')
        pass

def create_circular_mask(size):
    if size <= 0:
        return None
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask

def draw_single_magnifier_circle_pil(draw, target_image, display_center_pos, capture_center_orig, capture_size_orig, magnifier_size_pixels, image_for_crop, is_dragging=False):
    if not isinstance(image_for_crop, Image.Image) or not hasattr(image_for_crop, 'size'):
        print('draw_single_magnifier: Invalid source image.')
        return
    if not isinstance(target_image, Image.Image):
        print('draw_single_magnifier: Invalid target image.')
        return
    if capture_size_orig <= 0 or magnifier_size_pixels <= 0:
        return
    source_width, source_height = image_for_crop.size
    if source_width <= 0 or source_height <= 0:
        print('draw_single_magnifier: Source image has zero dimensions.')
        return
    capture_radius_orig = capture_size_orig // 2
    crop_x = capture_center_orig.x() - capture_radius_orig
    crop_y = capture_center_orig.y() - capture_radius_orig
    crop_x_clamped = max(0, min(crop_x, source_width - capture_size_orig))
    crop_y_clamped = max(0, min(crop_y, source_height - capture_size_orig))
    captured_area = None
    try:
        crop_box = (crop_x_clamped, crop_y_clamped, crop_x_clamped + capture_size_orig, crop_y_clamped + capture_size_orig)
        captured_area = image_for_crop.crop(crop_box)
    except Exception as e:
        print(f'Error cropping single magnifier source: {e}')
        return
    scaled_capture = None
    try:
        resampling_method = Image.Resampling.BILINEAR if is_dragging else Image.Resampling.LANCZOS
        scaled_capture = captured_area.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e:
        print(f'Error resizing single magnifier capture: {e}')
        return
    if scaled_capture.mode != 'RGBA':
        try:
            scaled_capture = scaled_capture.convert('RGBA')
        except Exception as e:
            print(f'Error converting scaled capture to RGBA: {e}')
            return
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        if mask:
            scaled_capture.putalpha(mask)
        else:
            print('Warning: Failed to create circular mask.')
    except Exception as e:
        print(f'Error applying mask to single magnifier: {e}')
    radius_float = float(magnifier_size_pixels) / 2.0
    center_x_float = float(display_center_pos.x())
    center_y_float = float(display_center_pos.y())
    paste_x_float = center_x_float - radius_float
    paste_y_float = center_y_float - radius_float
    paste_x = int(round(paste_x_float))
    paste_y = int(round(paste_y_float))
    try:
        target_image.paste(scaled_capture, (paste_x, paste_y), scaled_capture)
    except Exception as e:
        print(f'Error pasting single magnifier onto target: {e}')
        return
    try:
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size_pixels - 1, paste_y + magnifier_size_pixels - 1]
        thickness_float = MAG_BORDER_THICKNESS_FACTOR * math.sqrt(max(1.0, float(magnifier_size_pixels)))
        thickness_clamped = max(float(MIN_MAG_BORDER_THICKNESS), min(float(MAX_MAG_BORDER_THICKNESS), thickness_float))
        border_thickness = max(1, int(round(thickness_clamped)))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception as e:
        print(f'Error drawing border for single magnifier: {e}')
        pass

def draw_combined_magnifier_circle_pil(draw, target_image, display_center_pos, capture_center_orig1, capture_center_orig2, capture_size_orig1, capture_size_orig2, magnifier_size_pixels, image1_for_crop, image2_for_crop, is_dragging=False):
    if not image1_for_crop or not image2_for_crop or (not capture_center_orig1) or (not capture_center_orig2):
        print('draw_combined: Missing source images or capture points.')
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
        return
    if not isinstance(target_image, Image.Image) or target_image.mode != 'RGBA':
        print('draw_combined: Target image is invalid or not RGBA.')
        return
    source1_width, source1_height = image1_for_crop.size
    source2_width, source2_height = image2_for_crop.size
    if source1_width <= 0 or source1_height <= 0 or source2_width <= 0 or (source2_height <= 0):
        print('draw_combined: Source images have zero dimensions.')
        return
    captured_area1 = captured_area2 = None
    cap_radius_orig1 = capture_size_orig1 // 2
    cap_radius_orig2 = capture_size_orig2 // 2
    try:
        crop1_x = capture_center_orig1.x() - cap_radius_orig1
        crop1_y = capture_center_orig1.y() - cap_radius_orig1
        crop1_x_clamped = max(0, min(crop1_x, source1_width - capture_size_orig1))
        crop1_y_clamped = max(0, min(crop1_y, source1_height - capture_size_orig1))
        crop_box1 = (crop1_x_clamped, crop1_y_clamped, crop1_x_clamped + capture_size_orig1, crop1_y_clamped + capture_size_orig1)
        captured_area1 = image1_for_crop.crop(crop_box1)
    except Exception as e:
        print(f'Error cropping img1 for combined magnifier: {e}')
        return
    try:
        crop2_x = capture_center_orig2.x() - cap_radius_orig2
        crop2_y = capture_center_orig2.y() - cap_radius_orig2
        crop2_x_clamped = max(0, min(crop2_x, source2_width - capture_size_orig2))
        crop2_y_clamped = max(0, min(crop2_y, source2_height - capture_size_orig2))
        crop_box2 = (crop2_x_clamped, crop2_y_clamped, crop2_x_clamped + capture_size_orig2, crop2_y_clamped + capture_size_orig2)
        captured_area2 = image2_for_crop.crop(crop_box2)
    except Exception as e:
        print(f'Error cropping img2 for combined magnifier: {e}')
        return
    scaled_capture1 = scaled_capture2 = None
    try:
        resampling_method = Image.Resampling.BILINEAR if is_dragging else Image.Resampling.LANCZOS
        scaled_capture1 = captured_area1.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
        scaled_capture2 = captured_area2.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e:
        print(f'Error resizing combined magnifier parts: {e}')
        return
    magnifier_img = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels), (0, 0, 0, 0))
    half_width = max(0, magnifier_size_pixels // 2)
    right_half_start = half_width
    right_half_width = magnifier_size_pixels - right_half_start
    try:
        left_half = scaled_capture1.crop((0, 0, half_width, magnifier_size_pixels))
        if right_half_start < scaled_capture2.width and right_half_width > 0:
            right_half = scaled_capture2.crop((right_half_start, 0, right_half_start + right_half_width, magnifier_size_pixels))
        else:
            right_half = Image.new('RGBA', (max(0, right_half_width), magnifier_size_pixels), (0, 0, 0, 0))
        magnifier_img.paste(left_half, (0, 0))
        if right_half.width > 0:
            magnifier_img.paste(right_half, (right_half_start, 0))
    except Exception as paste_err:
        print(f'Error pasting halves for combined magnifier: {paste_err}')
        return
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        if mask:
            magnifier_img.putalpha(mask)
        else:
            print('Warning: Failed to create mask for combined magnifier.')
    except Exception as mask_err:
        print(f'Error applying mask to combined magnifier: {mask_err}')
        return
    radius_float = float(magnifier_size_pixels) / 2.0
    center_x_float = float(display_center_pos.x())
    center_y_float = float(display_center_pos.y())
    paste_x_float = center_x_float - radius_float
    paste_y_float = center_y_float - radius_float
    paste_x = int(round(paste_x_float))
    paste_y = int(round(paste_y_float))
    try:
        target_image.paste(magnifier_img, (paste_x, paste_y), magnifier_img)
    except Exception as final_err:
        print(f'Error pasting combined magnifier onto target: {final_err}')
        return
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
        pass

def save_result_processor(self):
    file_name = None
    try:
        if not self.original_image1 or not self.original_image2:
            QMessageBox.warning(self, tr('Warning', self.current_language), tr('Please load and select images in both slots first.', self.current_language))
            return
        if not self.image1 or not self.image2:
            print('Warning: Resized images (self.image1/2) missing in save_result_processor. Attempting resize.')
            resize_images_processor(self)
            if not self.image1 or not self.image2:
                QMessageBox.warning(self, tr('Warning', self.current_language), tr('Resized images not available. Cannot save result. Please reload or select images.', self.current_language))
                return
        if self.image1.size != self.image2.size:
            print(f'ERROR: Mismatched image sizes in save_result_processor: {self.image1.size} vs {self.image2.size}. Retrying resize.')
            resize_images_processor(self)
            if not self.image1 or not self.image2 or self.image1.size != self.image2.size:
                print('ERROR: Mismatched sizes persist after resize attempt. Aborting save.')
                QMessageBox.warning(self, tr('Error', self.current_language), tr('Internal error: Image sizes do not match. Cannot save.', self.current_language))
                return
        img1_rgba = self.image1
        img2_rgba = self.image2
        width, height = img1_rgba.size
        image_to_save = Image.new('RGBA', (width, height))
        split_position_abs = 0
        try:
            if not self.is_horizontal:
                split_position_abs = max(0, min(width, int(round(width * self.split_position))))
                if split_position_abs > 0:
                    image_to_save.paste(img1_rgba.crop((0, 0, split_position_abs, height)), (0, 0))
                if split_position_abs < width:
                    image_to_save.paste(img2_rgba.crop((split_position_abs, 0, width, height)), (split_position_abs, 0))
            else:
                split_position_abs = max(0, min(height, int(round(height * self.split_position))))
                if split_position_abs > 0:
                    image_to_save.paste(img1_rgba.crop((0, 0, width, split_position_abs)), (0, 0))
                if split_position_abs < height:
                    image_to_save.paste(img2_rgba.crop((0, split_position_abs, width, height)), (0, split_pos_abs))
        except Exception as paste_err:
            print(f'ERROR creating base image for saving: {paste_err}')
            QMessageBox.critical(self, tr('Error', self.current_language), tr('Failed to create the base image for saving.', self.current_language))
            return
        line_thickness_save = max(1, min(5, int(width * 0.0035))) if not self.is_horizontal else max(1, min(5, int(height * 0.005)))
        draw_split_line_pil(image_to_save, self.image1, self.image2, self.split_position, self.is_horizontal, line_thickness=line_thickness_save, blend_alpha=0.5)
        overlay_save = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw_overlay_save = ImageDraw.Draw(overlay_save)
        if self.use_magnifier:
            save_width, save_height = image_to_save.size
            coords_save = get_original_coords(self, drawing_width=save_width, drawing_height=save_height, display_width=save_width, display_height=save_height, use_visual_offset=False)
            if coords_save and coords_save[0] is not None:
                capture_center_orig1, capture_center_orig2, capture_size_orig1, capture_size_orig2, magnifier_midpoint_save, magnifier_size_pixels_save, magnifier_spacing_pixels_save = coords_save
                if capture_center_orig1 and capture_size_orig1 > 0:
                    cap_center_draw_x = int(round(self.capture_position_relative.x() * float(save_width)))
                    cap_center_draw_y = int(round(self.capture_position_relative.y() * float(save_height)))
                    capture_marker_center_drawing = QPoint(cap_center_draw_x, cap_center_draw_y)
                    capture_marker_size_drawing = 10
                    try:
                        if self.original_image1 and self.original_image1.size[0] > 0 and (save_width > 0):
                            scale_orig1_to_draw_w = float(save_width) / float(self.original_image1.size[0])
                            capture_marker_size_drawing = max(5, int(round(capture_size_orig1 * scale_orig1_to_draw_w)))
                    except Exception as e_scale_save:
                        print(f'Warning: Error calculating capture marker scale for saving: {e_scale_save}')
                    draw_capture_area_pil(draw_overlay_save, capture_marker_center_drawing, capture_marker_size_drawing)
                if magnifier_midpoint_save:
                    draw_magnifier_pil(draw_overlay_save, overlay_save, self.original_image1, self.original_image2, capture_center_orig1, capture_center_orig2, capture_size_orig1, capture_size_orig2, magnifier_midpoint_save, magnifier_size_pixels_save, magnifier_spacing_pixels_save, self, is_dragging=False)
        if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            line_width_names = line_thickness_save if not self.is_horizontal else 0
            line_height_names = line_thickness_save if self.is_horizontal else 0
            color_tuple = self.file_name_color.getRgb()
            draw_file_names_on_image(self, draw_overlay_save, overlay_save, split_position_abs, width, height, line_width_names, line_height_names, color_tuple)
        try:
            image_to_save = Image.alpha_composite(image_to_save, overlay_save)
        except Exception as e_composite_save:
            print(f'ERROR during alpha_composite for saving: {e_composite_save}')
        file_name, selected_filter = QFileDialog.getSaveFileName(self, tr('Save Image', self.current_language), '', tr('PNG Files', self.current_language) + ' (*.png);;' + tr('JPEG Files', self.current_language) + ' (*.jpg *.jpeg);;' + tr('All Files', self.current_language) + ' (*)')
        if not file_name:
            return
        _, ext = os.path.splitext(file_name)
        original_ext = ext
        if not ext:
            if 'JPEG' in selected_filter:
                file_name += '.jpg'
            else:
                file_name += '.png'
        else:
            ext_lower = ext.lower()
            if 'JPEG' in selected_filter and ext_lower not in ('.jpg', '.jpeg'):
                print(f'Warning: Filter is JPEG, but extension is {ext}. Saving as JPG.')
                file_name = os.path.splitext(file_name)[0] + '.jpg'
            elif 'PNG' in selected_filter and ext_lower != '.png':
                print(f'Warning: Filter is PNG, but extension is {ext}. Saving as PNG.')
                file_name = os.path.splitext(file_name)[0] + '.png'
            elif ext_lower not in ('.jpg', '.jpeg', '.png'):
                print(f"Warning: Unknown extension '{ext}'. Saving as PNG.")
                file_name = os.path.splitext(file_name)[0] + '.png'
        try:
            if file_name.lower().endswith(('.jpg', '.jpeg')):
                print('Saving as JPEG, creating white background...')
                img_for_jpeg = image_to_save.copy()
                background = Image.new('RGB', img_for_jpeg.size, (255, 255, 255))
                try:
                    img_for_jpeg.load()
                    background.paste(img_for_jpeg, mask=img_for_jpeg.split()[3])
                except IndexError:
                    print('Warning: Image for JPEG save has no alpha channel. Pasting as RGB.')
                    background.paste(img_for_jpeg.convert('RGB'))
                except Exception as load_err:
                    print(f'Error loading/pasting image data for JPEG save: {load_err}. Pasting as RGB.')
                    background.paste(img_for_jpeg.convert('RGB'))
                current_jpeg_quality = getattr(self, 'jpeg_quality', 93)
                print(f'Using JPEG quality: {current_jpeg_quality}')
                background.save(file_name, 'JPEG', quality=current_jpeg_quality)
                print(f'Image successfully saved as JPEG: {file_name}')
            else:
                if not file_name.lower().endswith(('.jpg', '.jpeg', '.png')):
                    file_name = os.path.splitext(file_name)[0] + '.png'
                print(f'Saving as PNG (or original if PNG): {file_name}')
                image_to_save.save(file_name)
                print(f'Image successfully saved: {file_name}')
        except Exception as e_save:
            QMessageBox.critical(self, tr('Error', self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{file_name}\n\n{str(e_save)}")
            print(f'ERROR during actual file save operation: {e_save}')
            traceback.print_exc()
    except Exception as e_outer:
        print(f'ERROR in save_result_processor (outer): {e_outer}')
        traceback.print_exc()
        error_path_msg = file_name if file_name else tr('Path not determined', self.current_language)
        QMessageBox.critical(self, tr('Error', self.current_language), f"{tr('An unexpected error occurred during the save process:', self.current_language)}\n{error_path_msg}\n\n{str(e_outer)}")

def draw_file_names_on_image(self, draw: ImageDraw.ImageDraw, image: Image.Image, split_position_abs: int, orig_width: int, orig_height: int, line_width: int, line_height: int, text_color_tuple: tuple):
    font_size_percentage = self.font_size_slider.value() / 200.0
    base_font_size_ratio = 0.03
    font_size = max(10, int(orig_height * base_font_size_ratio * font_size_percentage))
    margin = max(5, int(font_size * 0.25))
    font_path_to_use = getattr(self, 'font_path_absolute', None)
    font: FontType = None
    if font_path_to_use and os.path.exists(font_path_to_use):
        try:
            font = ImageFont.truetype(font_path_to_use, size=font_size)
        except IOError as e:
            print(f'Warning: Failed to load font from path (IOError): {font_path_to_use}. Error: {e}')
            font = None
        except Exception as e:
            print(f'Warning: Unexpected error loading font from path: {font_path_to_use}. Error: {e}')
            font = None
    elif font_path_to_use:
        print(f"Warning: Custom font path '{font_path_to_use}' not found or invalid. Trying fallbacks.")
    if font is None:
        try:
            font = ImageFont.truetype('arial.ttf', size=font_size)
        except IOError:
            print('Warning: Arial font not found. Using PIL default font.')
            try:
                font = ImageFont.truetype(None, size=font_size)
            except Exception as e_def:
                print(f'Error loading default truetype font: {e_def}. Falling back to load_default().')
                try:
                    font = ImageFont.load_default()
                except Exception as e_ld:
                    print(f'FATAL: Could not load any font: {e_ld}')
                    return
    file_name1_raw = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else 'Image 1')
    file_name2_raw = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else 'Image 2')
    max_length = self.max_name_length

    def _internal_get_text_size(text: str, font_to_use: FontType) -> Tuple[int, int]:
        if not text or not font_to_use:
            return (0, 0)
        try:
            if hasattr(draw, 'textbbox') and hasattr(font_to_use, 'getbbox'):
                bbox = draw.textbbox((0, 0), text, font=font_to_use, anchor='lt')
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]
                return (int(round(width)), int(round(height)))
            elif hasattr(draw, 'textlength') and hasattr(font_to_use, 'getmetrics'):
                ascent, descent = font_to_use.getmetrics()
                height = int(round(ascent + descent))
                width = int(round(draw.textlength(text, font=font_to_use)))
                return (width, height)
            elif hasattr(font_to_use, 'getsize'):
                width, height = font_to_use.getsize(text)
                return (int(round(width)), int(round(height)))
            else:
                print('Warning: Cannot determine text size accurately. Using approximation.')
                char_width_approx = font_size * 0.6
                return (int(round(len(text) * char_width_approx)), int(round(font_size)))
        except Exception as e:
            print(f"Error getting text size for '{text[:20]}...': {e}")
            char_width_approx = font_size * 0.6
            return (int(round(len(text) * char_width_approx)), int(round(font_size)))
    margin_int = int(round(margin))
    available_width1 = 0
    if not self.is_horizontal:
        available_width1 = max(10, int(round(split_position_abs - line_width // 2 - margin_int * 2)))
    else:
        available_width1 = max(10, int(round(orig_width - margin_int * 2)))
    available_width2 = 0
    if not self.is_horizontal:
        available_width2 = max(10, int(round(orig_width - (split_position_abs + (line_width + 1) // 2) - margin_int * 2)))
    else:
        available_width2 = max(10, int(round(orig_width - margin_int * 2)))
    file_name1 = truncate_text(file_name1_raw, available_width1, max_length, font, _internal_get_text_size)
    file_name2 = truncate_text(file_name2_raw, available_width2, max_length, font, _internal_get_text_size)
    text_color = text_color_tuple
    if not self.is_horizontal:
        draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin_int, orig_width, orig_height, text_color, _internal_get_text_size)
    else:
        draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin_int, orig_width, orig_height, text_color, _internal_get_text_size)

def draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size_func):
    y_baseline = orig_height - margin
    if file_name1:
        try:
            ideal_x1_right = split_position_abs - line_width // 2 - margin
            ideal_x1_pos = ideal_x1_right
            bbox1 = None
            anchor1 = 'rs'
            if hasattr(draw, 'textbbox') and hasattr(font, 'getbbox'):
                bbox1 = draw.textbbox((ideal_x1_pos, y_baseline), file_name1, font=font, anchor=anchor1)
            else:
                text_width1, text_height1 = get_text_size_func(file_name1, font)
                approx_ascent = text_height1 * 0.75
                bbox1_top = y_baseline - approx_ascent
                bbox1_left = ideal_x1_pos - text_width1
                bbox1 = (bbox1_left, bbox1_top, ideal_x1_pos, bbox1_top + text_height1)
            if bbox1 and bbox1[0] >= margin:
                draw.text((ideal_x1_pos, y_baseline), file_name1, fill=text_color, font=font, anchor=anchor1)
        except Exception as e:
            print(f'Error processing or drawing filename 1 (vertical): {e}')
    if file_name2:
        try:
            ideal_x2_left = split_position_abs + (line_width + 1) // 2 + margin
            ideal_x2_pos = ideal_x2_left
            bbox2 = None
            anchor2 = 'ls'
            if hasattr(draw, 'textbbox') and hasattr(font, 'getbbox'):
                bbox2 = draw.textbbox((ideal_x2_pos, y_baseline), file_name2, font=font, anchor=anchor2)
            else:
                text_width2, text_height2 = get_text_size_func(file_name2, font)
                approx_ascent = text_height2 * 0.75
                bbox2_top = y_baseline - approx_ascent
                bbox2_right = ideal_x2_pos + text_width2
                bbox2 = (ideal_x2_pos, bbox2_top, bbox2_right, bbox2_top + text_height2)
            if bbox2 and bbox2[2] <= orig_width - margin:
                draw.text((ideal_x2_pos, y_baseline), file_name2, fill=text_color, font=font, anchor=anchor2)
        except Exception as e:
            print(f'Error processing or drawing filename 2 (vertical): {e}')

def draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size_func):
    line_top = split_position_abs - line_height // 2
    line_bottom = split_position_abs + (line_height + 1) // 2
    if file_name1:
        try:
            ideal_y1_baseline = line_top - margin
            ideal_x1 = margin
            bbox1 = None
            anchor1 = 'ls'
            if hasattr(draw, 'textbbox'):
                bbox1 = draw.textbbox((ideal_x1, ideal_y1_baseline), file_name1, font=font, anchor=anchor1)
            else:
                text_width1, text_height1 = get_text_size_func(file_name1, font)
                approx_ascent = text_height1 * 0.75
                bbox1_top = ideal_y1_baseline - approx_ascent
                bbox1_bottom = bbox1_top + text_height1
                bbox1 = (ideal_x1, bbox1_top, ideal_x1 + text_width1, bbox1_bottom)
            if bbox1 and bbox1[1] >= margin:
                draw.text((ideal_x1, ideal_y1_baseline), file_name1, fill=text_color, font=font, anchor=anchor1)
        except Exception as e:
            print(f'Error processing or drawing filename 1 (horizontal): {e}')
    if file_name2:
        try:
            ideal_y2_top = line_bottom + margin
            ideal_x2 = margin
            bbox2 = None
            anchor2 = 'lt'
            if hasattr(draw, 'textbbox'):
                bbox2 = draw.textbbox((ideal_x2, ideal_y2_top), file_name2, font=font, anchor=anchor2)
            else:
                text_width2, text_height2 = get_text_size_func(file_name2, font)
                bbox2 = (ideal_x2, ideal_y2_top, ideal_x2 + text_width2, ideal_y2_top + text_height2)
            if bbox2 and bbox2[3] <= orig_height - margin:
                draw.text((ideal_x2, ideal_y2_top), file_name2, fill=text_color, font=font, anchor=anchor2)
        except Exception as e:
            print(f'Error processing or drawing filename 2 (horizontal): {e}')
