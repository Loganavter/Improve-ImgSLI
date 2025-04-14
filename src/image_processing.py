from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtCore import Qt, QPoint, QPointF, QSize
try:
    from translations import tr
except ImportError:
    print("Warning: 'translations.py' not found. Using fallback translation.")

    def tr(text, lang='en', *args, **kwargs):
        return text
import os
import math
MIN_CAPTURE_THICKNESS = 1
MAX_CAPTURE_THICKNESS = 4
CAPTURE_THICKNESS_FACTOR = 0.35
MIN_MAG_BORDER_THICKNESS = 1
MAX_MAG_BORDER_THICKNESS = 4
MAG_BORDER_THICKNESS_FACTOR = 0.15

def get_scaled_pixmap_dimensions(app):
    source_image = app.result_image if app.result_image else app.original_image1
    if not source_image:
        return 0, 0
    label_width = app.image_label.width()
    label_height = app.image_label.height()
    if label_width <= 0 or label_height <= 0:
        return 0, 0
    orig_width, orig_height = source_image.size
    if orig_height == 0 or orig_width == 0:
        return 0, 0
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
    return scaled_width, scaled_height

def get_original_coords(app, drawing_width, drawing_height, display_width, display_height, use_visual_offset):
    if not app.original_image1 or not app.original_image2:
        return None, None, None, None, None, None, None
    if drawing_width <= 0 or drawing_height <= 0 or display_width <= 0 or display_height <= 0:
        return None, None, None, None, None, None, None
    orig1_width, orig1_height = app.original_image1.size
    orig2_width, orig2_height = app.original_image2.size
    if orig1_width <= 0 or orig1_height <= 0 or orig2_width <= 0 or orig2_height <= 0:
        return None, None, None, None, None, None, None
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
            REFERENCE_MAGNIFIER_RELATIVE_SIZE = 0.2
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
    return (capture_center_orig1, capture_center_orig2,
            capture_size_orig1_int, capture_size_orig2_int,
            magnifier_midpoint_drawing,
            magnifier_size_pixels_drawing,
            edge_spacing_pixels_drawing)

def resize_images_processor(app):
    if not app.original_image1 or not app.original_image2:
        app.image1 = None; app.image2 = None; return
    orig1_w, orig1_h = app.original_image1.size
    orig2_w, orig2_h = app.original_image2.size
    max_width = max(orig1_w, orig2_w)
    max_height = max(orig1_h, orig2_h)
    try:
        img1_copy = app.original_image1.copy()
        app.image1 = img1_copy.resize((max_width, max_height), Image.Resampling.LANCZOS) if img1_copy.size != (max_width, max_height) else img1_copy
        if app.image1.mode != 'RGBA': app.image1 = app.image1.convert('RGBA')
        img2_copy = app.original_image2.copy()
        app.image2 = img2_copy.resize((max_width, max_height), Image.Resampling.LANCZOS) if img2_copy.size != (max_width, max_height) else img2_copy
        if app.image2.mode != 'RGBA': app.image2 = app.image2.convert('RGBA')
    except Exception as e:
        app.image1 = None; app.image2 = None
        if hasattr(app, 'current_language'):
            QMessageBox.warning(app, tr("Error", app.current_language), f"{tr('Failed to resize images:', app.current_language)}\n{e}")

def update_comparison_processor(app):
    if not app.image1 or not app.image2:
        app.image_label.clear(); app.result_image = None; return
    img1_rgba = app.image1; img2_rgba = app.image2
    width, height = img1_rgba.size
    result = Image.new('RGBA', (width, height))
    split_pos = 0
    if not app.is_horizontal:
        split_pos = max(0, min(width, int(width * app.split_position)))
        if split_pos > 0: result.paste(img1_rgba.crop((0, 0, split_pos, height)), (0, 0))
        if split_pos < width: result.paste(img2_rgba.crop((split_pos, 0, width, height)), (split_pos, 0))
    else:
        split_pos = max(0, min(height, int(height * app.split_position)))
        if split_pos > 0: result.paste(img1_rgba.crop((0, 0, width, split_pos)), (0, 0))
        if split_pos < height: result.paste(img2_rgba.crop((0, split_pos, width, height)), (0, split_pos))
    app.result_image = result
    display_result_processor(app)

def display_result_processor(app):
    """
    Processes the combined result image, draws overlays (split line, magnifier, names),
    and displays the final scaled pixmap in the image_label.
    Also updates app.pixmap_width and app.pixmap_height.
    """
    if not app.result_image:
        app.image_label.clear()
        app.pixmap_width = 0
        app.pixmap_height = 0
        return
    try:
        image_to_display = app.result_image.copy()
    except Exception as e:
        print(f"Error copying result image for display: {e}")
        app.image_label.clear()
        app.pixmap_width = 0
        app.pixmap_height = 0
        return
    draw = ImageDraw.Draw(image_to_display)
    orig_width, orig_height = image_to_display.size
    current_label_size = app.image_label.size()
    label_width = current_label_size.width()
    label_height = current_label_size.height()
    if label_width <= 0 or label_height <= 0 or orig_width <= 0 or orig_height <= 0:
         app.image_label.clear()
         app.pixmap_width = 0
         app.pixmap_height = 0
         return
    aspect_ratio = float(orig_width) / float(orig_height) if orig_height > 0 else 1.0
    label_aspect_ratio = float(label_width) / float(label_height) if label_height > 0 else aspect_ratio + 1
    if aspect_ratio > label_aspect_ratio:
        display_width = label_width
        display_height = int(round(label_width / aspect_ratio)) if aspect_ratio != 0 else 0
    else:
        display_height = label_height
        display_width = int(round(label_height * aspect_ratio))
    display_width = max(1, display_width)
    display_height = max(1, display_height)
    target_display_size = QSize(display_width, display_height)
    app.pixmap_width = display_width
    app.pixmap_height = display_height
    draw_split_line_pil(draw, image_to_display, app.split_position, app.is_horizontal)
    if app.use_magnifier and app.original_image1 and app.original_image2:
        coords = get_original_coords(app,
                                      drawing_width=orig_width, drawing_height=orig_height,
                                      display_width=display_width,
                                      display_height=display_height,
                                      use_visual_offset=True)
        if coords and coords[0] is not None:
            (capture_center_orig1, capture_center_orig2,
             capture_size_orig1, capture_size_orig2,
             magnifier_midpoint_drawing,
             magnifier_size_pixels_drawing,
             edge_spacing_pixels_drawing) = coords
            cap_center_draw_x = int(round(app.capture_position_relative.x() * float(orig_width)))
            cap_center_draw_y = int(round(app.capture_position_relative.y() * float(orig_height)))
            capture_marker_center_drawing = QPoint(cap_center_draw_x, cap_center_draw_y)
            capture_marker_size_drawing = 10
            try:
                if app.original_image1 and app.original_image1.size[0] > 0 and orig_width > 0:
                    scale_orig1_to_draw_w = float(orig_width) / float(app.original_image1.size[0])
                    capture_marker_size_drawing = max(5, int(round(capture_size_orig1 * scale_orig1_to_draw_w)))
            except Exception as e_scale:
                print(f"Warning: Error calculating capture marker scale: {e_scale}")
            draw_capture_area_pil(draw, capture_marker_center_drawing, capture_marker_size_drawing)
            if magnifier_midpoint_drawing:
                is_dragging_capture = getattr(app, '_is_dragging_capture_point', False)
                draw_magnifier_pil(
                    draw, image_to_display,
                    app.original_image1, app.original_image2,
                    capture_center_orig1, capture_center_orig2,
                    capture_size_orig1, capture_size_orig2,
                    magnifier_midpoint_drawing,
                    magnifier_size_pixels_drawing,
                    edge_spacing_pixels_drawing,
                    app,
                    is_dragging=is_dragging_capture
                )
    if hasattr(app, 'checkbox_file_names') and app.checkbox_file_names.isChecked():
         split_position_abs = 0
         if not app.is_horizontal:
             split_position_abs = int(round(float(orig_width) * app.split_position))
         else:
             split_position_abs = int(round(float(orig_height) * app.split_position))
         line_width_names = max(1, min(5, int(orig_width * 0.0035))) if not app.is_horizontal else 0
         line_height_names = max(1, min(5, int(orig_height * 0.005))) if app.is_horizontal else 0
         color_tuple = app.file_name_color.getRgb()
         draw_file_names_on_image(
             app, draw, image_to_display, split_position_abs,
             orig_width, orig_height, line_width_names, line_height_names, color_tuple
         )
    try:
        qimage = None
        if image_to_display.mode == 'RGBA':
            qimage = QImage(image_to_display.tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)
        elif image_to_display.mode == 'RGB':
             qimage = QImage(image_to_display.tobytes("raw", "RGB"), orig_width, orig_height, QImage.Format.Format_RGB888)
        else:
            print(f"Warning: Unexpected image mode '{image_to_display.mode}' in display_result_processor. Converting to RGBA.")
            temp_rgba = image_to_display.convert('RGBA')
            qimage = QImage(temp_rgba.tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)
        if qimage is None or qimage.isNull():
            raise ValueError("Failed to create QImage from PIL image")
        pixmap = QPixmap.fromImage(qimage)
    except Exception as e:
        print(f"Error converting PIL image to QPixmap: {e}")
        app.image_label.clear(); app.pixmap_width = 0; app.pixmap_height = 0
        return
    if not pixmap.isNull():
        scaled_pixmap = pixmap.scaled(target_display_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        app.image_label.setPixmap(scaled_pixmap)
    else:
        print("Warning: Final QPixmap is null before setting to label.")
        app.image_label.clear(); app.pixmap_width = 0; app.pixmap_height = 0

def draw_split_line_pil(draw, image, split_position_ratio, is_horizontal, split_color=(0, 0, 0, 128)):
    width, height = image.size
    if not is_horizontal:
        line_x = int(width * split_position_ratio); line_width = max(1, min(5, int(width * 0.0035)))
        line_x = max(line_width // 2, min(width - (line_width + 1) // 2, line_x))
        draw.rectangle([line_x - line_width // 2, 0, line_x + (line_width + 1) // 2, height], fill=split_color)
    else:
        line_y = int(height * split_position_ratio); line_height = max(1, min(5, int(height * 0.005)))
        line_y = max(line_height // 2, min(height - (line_height + 1) // 2, line_y))
        draw.rectangle([0, line_y - line_height // 2, width, line_y + (line_height + 1) // 2], fill=split_color)

def draw_magnifier_pil(draw, image_to_draw_on,
                       image1, image2,
                       capture_pos1, capture_pos2,
                       capture_size_orig1, capture_size_orig2,
                       magnifier_midpoint_target,
                       magnifier_size_pixels,
                       edge_spacing_pixels,
                       app,
                       is_dragging=False):
    if not image1 or not image2 or not capture_pos1 or not capture_pos2 or not magnifier_midpoint_target:
        return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0:
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
        draw_combined_magnifier_circle_pil(
            image_to_draw_on, magnifier_midpoint_target,
            capture_pos1, capture_pos2,
            capture_size_orig1, capture_size_orig2,
            magnifier_size_pixels,
            image1, image2,
            is_dragging=is_dragging
        )
    else:
        draw_single_magnifier_circle_pil(
            image_to_draw_on, left_center,
            capture_pos1,
            capture_size_orig1,
            magnifier_size_pixels,
            image1,
            is_dragging=is_dragging
        )
        draw_single_magnifier_circle_pil(
            image_to_draw_on, right_center,
            capture_pos2,
            capture_size_orig2,
            magnifier_size_pixels,
            image2,
            is_dragging=is_dragging
        )

def draw_capture_area_pil(draw, center_pos, size):
    if size <= 0 or center_pos is None: return
    radius = size // 2
    bbox = [center_pos.x() - radius, center_pos.y() - radius,
            center_pos.x() + radius, center_pos.y() + radius]
    thickness_float = CAPTURE_THICKNESS_FACTOR * math.sqrt(max(1.0, float(size)))
    thickness_clamped = max(float(MIN_CAPTURE_THICKNESS), min(float(MAX_CAPTURE_THICKNESS), thickness_float))
    thickness = max(1, int(round(thickness_clamped)))
    try:
        bbox_int = [int(round(c)) for c in bbox]
        draw.ellipse(bbox_int, outline=(255, 0, 0, 255), width=thickness)
    except Exception as e:
        print(f"ERROR in draw_capture_area_pil: {e}")
        pass

def create_circular_mask(size):
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    return mask

def draw_single_magnifier_circle_pil(target_image, display_center_pos,
                                     capture_center_orig,
                                     capture_size_orig,
                                     magnifier_size_pixels,
                                     image_for_crop,
                                     is_dragging=False):
    if not isinstance(image_for_crop, Image.Image) or not hasattr(image_for_crop, 'size'): return
    if not isinstance(target_image, Image.Image): return
    if capture_size_orig <= 0 or magnifier_size_pixels <= 0: return
    source_width, source_height = image_for_crop.size
    if source_width <= 0 or source_height <= 0: return
    capture_radius_orig = capture_size_orig // 2
    crop_x = capture_center_orig.x() - capture_radius_orig
    crop_y = capture_center_orig.y() - capture_radius_orig
    crop_x_clamped = max(0, min(crop_x, source_width - capture_size_orig))
    crop_y_clamped = max(0, min(crop_y, source_height - capture_size_orig))
    try:
        crop_box = (crop_x_clamped, crop_y_clamped, crop_x_clamped + capture_size_orig, crop_y_clamped + capture_size_orig)
        captured_area = image_for_crop.crop(crop_box)
        resampling_method = Image.Resampling.BILINEAR if is_dragging else Image.Resampling.LANCZOS
        scaled_capture = captured_area.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e:
        print(f"Error cropping/resizing single magnifier: {e}")
        return
    if scaled_capture.mode != 'RGBA':
        try: scaled_capture = scaled_capture.convert('RGBA')
        except Exception: return
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        scaled_capture.putalpha(mask)
    except Exception: return
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
        print(f"Error pasting single magnifier: {e}")
        return
    try:
        draw = ImageDraw.Draw(target_image)
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size_pixels, paste_y + magnifier_size_pixels]
        thickness_float = MAG_BORDER_THICKNESS_FACTOR * math.sqrt(max(1.0, float(magnifier_size_pixels)))
        thickness_clamped = max(float(MIN_MAG_BORDER_THICKNESS), min(float(MAX_MAG_BORDER_THICKNESS), thickness_float))
        border_thickness = max(1, int(round(thickness_clamped)))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception: pass

def draw_combined_magnifier_circle_pil(target_image, display_center_pos,
                                       capture_center_orig1, capture_center_orig2,
                                       capture_size_orig1, capture_size_orig2,
                                       magnifier_size_pixels,
                                       image1_for_crop, image2_for_crop,
                                       is_dragging=False):
    if not image1_for_crop or not image2_for_crop or not capture_center_orig1 or not capture_center_orig2: return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size_pixels <= 0: return
    source1_width, source1_height = image1_for_crop.size
    source2_width, source2_height = image2_for_crop.size
    if source1_width <= 0 or source1_height <= 0 or source2_width <= 0 or source2_height <= 0: return
    captured_area1 = captured_area2 = None
    cap_radius_orig1 = capture_size_orig1 // 2
    cap_radius_orig2 = capture_size_orig2 // 2
    try:
        crop1_x = capture_center_orig1.x() - cap_radius_orig1; crop1_y = capture_center_orig1.y() - cap_radius_orig1
        crop1_x_clamped = max(0, min(crop1_x, source1_width - capture_size_orig1))
        crop1_y_clamped = max(0, min(crop1_y, source1_height - capture_size_orig1))
        crop_box1 = (crop1_x_clamped, crop1_y_clamped, crop1_x_clamped + capture_size_orig1, crop1_y_clamped + capture_size_orig1)
        captured_area1 = image1_for_crop.crop(crop_box1)
    except Exception as e: print(f"Error cropping img1 for combined magnifier: {e}"); return
    try:
        crop2_x = capture_center_orig2.x() - cap_radius_orig2; crop2_y = capture_center_orig2.y() - cap_radius_orig2
        crop2_x_clamped = max(0, min(crop2_x, source2_width - capture_size_orig2))
        crop2_y_clamped = max(0, min(crop2_y, source2_height - capture_size_orig2))
        crop_box2 = (crop2_x_clamped, crop2_y_clamped, crop2_x_clamped + capture_size_orig2, crop2_y_clamped + capture_size_orig2)
        captured_area2 = image2_for_crop.crop(crop_box2)
    except Exception as e: print(f"Error cropping img2 for combined magnifier: {e}"); return
    try:
        resampling_method = Image.Resampling.BILINEAR if is_dragging else Image.Resampling.LANCZOS
        scaled_capture1 = captured_area1.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
        scaled_capture2 = captured_area2.resize((magnifier_size_pixels, magnifier_size_pixels), resampling_method)
    except Exception as e: print(f"Error resizing combined magnifier parts: {e}"); return
    magnifier_img = Image.new('RGBA', (magnifier_size_pixels, magnifier_size_pixels))
    half_width = max(0, magnifier_size_pixels // 2)
    right_half_start = half_width
    right_half_width = magnifier_size_pixels - right_half_start
    try:
        left_half = scaled_capture1.crop((0, 0, half_width, magnifier_size_pixels))
        if right_half_start < scaled_capture2.width and right_half_width > 0:
             right_half = scaled_capture2.crop((right_half_start, 0, right_half_start + right_half_width, magnifier_size_pixels))
        else:
             right_half = Image.new('RGBA', (max(0, right_half_width), magnifier_size_pixels), (0,0,0,0))
        magnifier_img.paste(left_half, (0, 0))
        if right_half.width > 0:
             magnifier_img.paste(right_half, (right_half_start, 0))
    except Exception as paste_err: print(f"Error pasting halves for combined magnifier: {paste_err}"); return
    try:
        mask = create_circular_mask(magnifier_size_pixels)
        magnifier_img.putalpha(mask)
    except Exception as mask_err: print(f"Error applying mask to combined magnifier: {mask_err}"); return
    radius_float = float(magnifier_size_pixels) / 2.0
    center_x_float = float(display_center_pos.x())
    center_y_float = float(display_center_pos.y())
    paste_x_float = center_x_float - radius_float
    paste_y_float = center_y_float - radius_float
    paste_x = int(round(paste_x_float))
    paste_y = int(round(paste_y_float))
    try:
        target_image.paste(magnifier_img, (paste_x, paste_y), magnifier_img)
    except Exception as final_err: print(f"Error pasting combined magnifier onto target: {final_err}"); return
    try:
        draw = ImageDraw.Draw(target_image)
        thickness_float = MAG_BORDER_THICKNESS_FACTOR * math.sqrt(max(1.0, float(magnifier_size_pixels)))
        thickness_clamped = max(float(MIN_MAG_BORDER_THICKNESS), min(float(MAX_MAG_BORDER_THICKNESS), thickness_float))
        dynamic_thickness = max(1, int(round(thickness_clamped)))
        half_width = max(0, magnifier_size_pixels // 2)
        draw.rectangle([paste_x + half_width - dynamic_thickness // 2, paste_y,
                        paste_x + half_width + (dynamic_thickness + 1) // 2, paste_y + magnifier_size_pixels],
                       fill=(255, 255, 255, 200))
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size_pixels, paste_y + magnifier_size_pixels]
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=dynamic_thickness)
    except Exception as draw_err: pass

def save_result_processor(self):
    file_name = None
    try:
        if not self.original_image1 or not self.original_image2:
            QMessageBox.warning(self, tr("Warning", self.current_language), tr("Please load and select images in both slots first.", self.current_language))
            return
        if not self.image1 or not self.image2:
            print("Warning: Resized images (self.image1/2) missing in save_result_processor. Attempting resize.")
            resize_images_processor(self)
            if not self.image1 or not self.image2:
                QMessageBox.warning(self, tr("Warning", self.current_language), tr("Resized images not available. Cannot save result. Please reload or select images.", self.current_language))
                return
        img1_rgba = self.image1
        img2_rgba = self.image2
        width, height = img1_rgba.size
        image_to_save = Image.new('RGBA', (width, height))
        split_position_abs = 0
        if not self.is_horizontal:
            split_position_abs = max(0, min(width, int(width * self.split_position)))
            if split_position_abs > 0:
                image_to_save.paste(img1_rgba.crop((0, 0, split_position_abs, height)), (0, 0))
            if split_position_abs < width:
                image_to_save.paste(img2_rgba.crop((split_position_abs, 0, width, height)), (split_position_abs, 0))
        else:
            split_position_abs = max(0, min(height, int(height * self.split_position)))
            if split_position_abs > 0:
                image_to_save.paste(img1_rgba.crop((0, 0, width, split_position_abs)), (0, 0))
            if split_position_abs < height:
                image_to_save.paste(img2_rgba.crop((0, split_position_abs, width, height)), (0, split_position_abs))
        draw = ImageDraw.Draw(image_to_save)
        save_width, save_height = image_to_save.size
        save_split_color = (128, 128, 128, 255)
        draw_split_line_pil(draw, image_to_save, self.split_position, self.is_horizontal, split_color=save_split_color)
        if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            line_width_names = max(1, min(5, int(width * 0.0035))) if not self.is_horizontal else 0
            line_height_names = max(1, min(5, int(height * 0.005))) if self.is_horizontal else 0
            color_tuple = self.file_name_color.getRgb()
            draw_file_names_on_image(self, draw, image_to_save, split_position_abs, width, height, line_width_names, line_height_names, color_tuple)
        if self.use_magnifier:
            coords_save = get_original_coords(self,
                                              drawing_width=save_width, drawing_height=save_height,
                                              display_width=save_width, display_height=save_height,
                                              use_visual_offset=False)
            if coords_save and coords_save[0] is not None:
                (capture_center_orig1, capture_center_orig2,
                 capture_size_orig1, capture_size_orig2,
                 magnifier_midpoint_save,
                 magnifier_size_pixels_save,
                 magnifier_spacing_pixels_save) = coords_save
                if capture_center_orig1 and capture_size_orig1 > 0:
                    cap_center_draw_x = int(round(self.capture_position_relative.x() * float(save_width)))
                    cap_center_draw_y = int(round(self.capture_position_relative.y() * float(save_height)))
                    capture_marker_center_drawing = QPoint(cap_center_draw_x, cap_center_draw_y)
                    capture_marker_size_drawing = 10
                    try:
                        if self.original_image1 and self.original_image1.size[0] > 0 and save_width > 0:
                            scale_orig1_to_draw_w = float(save_width) / float(self.original_image1.size[0])
                            capture_marker_size_drawing = max(5, int(round(capture_size_orig1 * scale_orig1_to_draw_w)))
                    except Exception as e_scale_save:
                        print(f"Warning: Error calculating capture marker scale for saving: {e_scale_save}")
                    draw_capture_area_pil(draw, capture_marker_center_drawing, capture_marker_size_drawing)
                if magnifier_midpoint_save:
                     draw_magnifier_pil(
                        draw, image_to_save,
                        self.original_image1, self.original_image2,
                        capture_center_orig1, capture_center_orig2,
                        capture_size_orig1, capture_size_orig2,
                        magnifier_midpoint_save,
                        magnifier_size_pixels_save,
                        magnifier_spacing_pixels_save,
                        self
                    )
        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
            tr("Save Image", self.current_language),
            "",
            tr("PNG Files", self.current_language) + " (*.png);;" + tr("JPEG Files", self.current_language) + " (*.jpg *.jpeg);;" + tr("All Files", self.current_language) + " (*)"
        )
        if not file_name:
            return
        _, ext = os.path.splitext(file_name)
        if not ext:
            if "JPEG" in selected_filter: file_name += '.jpg'
            else: file_name += '.png'
        else:
            ext_lower = ext.lower()
            if "JPEG" in selected_filter and ext_lower not in (".jpg", ".jpeg"):
                 file_name = os.path.splitext(file_name)[0] + '.jpg'
            elif "PNG" in selected_filter and ext_lower != ".png":
                 file_name = os.path.splitext(file_name)[0] + '.png'
            elif ext_lower not in (".jpg", ".jpeg", ".png"):
                 print(f"Warning: Unknown extension '{ext}'. Saving as PNG.")
                 file_name = os.path.splitext(file_name)[0] + '.png'
        try:
            if file_name.lower().endswith((".jpg", ".jpeg")):
                print("Saving as JPEG, creating white background...")
                background = Image.new("RGB", image_to_save.size, (255, 255, 255))
                if image_to_save.mode == 'RGBA':
                    img_copy = image_to_save.copy()
                    try:
                      img_copy.load()
                      background.paste(img_copy, mask=img_copy.split()[3])
                    except Exception as load_err:
                       print(f"Error loading image data before pasting for JPEG save: {load_err}. Pasting as RGB.")
                       background.paste(image_to_save.convert("RGB"))
                else:
                     background.paste(image_to_save.convert("RGB"))
                background.save(file_name, "JPEG", quality=93)
                print(f"Image successfully saved as JPEG: {file_name}")
            else:
                if not file_name.lower().endswith((".jpg", ".jpeg", ".png")):
                     file_name = os.path.splitext(file_name)[0] + '.png'
                print(f"Saving as PNG (or original format): {file_name}")
                image_to_save.save(file_name)
                print(f"Image successfully saved: {file_name}")
        except Exception as e_save:
            QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{file_name}\n\n{str(e_save)}")
            print(f"ERROR during actual file save operation: {e_save}")
            import traceback
            traceback.print_exc()
    except Exception as e_outer:
        print(f"ERROR in save_result_processor (outer): {e_outer}")
        import traceback
        traceback.print_exc()
        error_path_msg = file_name if file_name else tr("Path not determined", self.current_language)
        QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('An unexpected error occurred during the save process:', self.current_language)}\n{error_path_msg}\n\n{str(e_outer)}")

def draw_file_names_on_image(self, draw, image, split_position_abs, orig_width, orig_height, line_width, line_height, text_color_tuple):
    """
    Рисует имена файлов на изображении.
    'self' здесь - это экземпляр ImageComparisonApp.
    """
    font_size_percentage = self.font_size_slider.value() / 200.0
    base_font_size_ratio = 0.03
    font_size = max(10, int(orig_height * base_font_size_ratio * font_size_percentage))
    margin = max(5, int(font_size * 0.25))
    font_path_to_use = getattr(self, 'font_path_absolute', None)
    font = None
    if font_path_to_use and os.path.exists(font_path_to_use):
        try:
            font = ImageFont.truetype(font_path_to_use, size=font_size)
        except IOError as e:
            print(f"Warning: Failed to load font from path (even though it exists): {font_path_to_use}. Error: {e}")
            font = None
        except Exception as e:
             print(f"Warning: Unexpected error loading font from path: {font_path_to_use}. Error: {e}")
             font = None
    else:
        if font_path_to_use:
             print(f"Warning: Custom font path '{font_path_to_use}' not found or invalid. Trying fallbacks.")
    if font is None:
        try:
            font = ImageFont.truetype("arial.ttf", size=font_size)
            print("Info: Using Arial font as fallback.")
        except IOError:
            print("Warning: Arial font not found. Using PIL default font.")
            try:
                font = ImageFont.truetype(None, size=font_size)
            except:
                font = ImageFont.load_default()
    file_name1_raw = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else "Image 1")
    file_name2_raw = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else "Image 2")
    max_length = self.max_name_length

    def get_text_size(text, font_to_use):
        if not text or not font_to_use: return 0, 0
        try:
            if hasattr(draw, 'textbbox') and hasattr(font_to_use, 'getbbox'):
                 bbox = draw.textbbox((0, 0), text, font=font_to_use, anchor="lt")
                 return bbox[2] - bbox[0], bbox[3] - bbox[1]
            elif hasattr(draw, 'textlength') and hasattr(font_to_use, 'getmetrics'):
                ascent, descent = font_to_use.getmetrics()
                height = ascent + descent
                return draw.textlength(text, font=font_to_use), height
            elif hasattr(font_to_use, 'getsize'):
                 width, height = font_to_use.getsize(text)
                 return width, height
            else:
                print("Warning: Cannot determine text size accurately. Using approximation.")
                char_width_approx = font_size * 0.6
                return len(text) * char_width_approx, font_size
        except Exception as e:
             print(f"Error getting text size for '{text[:20]}...': {e}")
             char_width_approx = font_size * 0.6
             return len(text) * char_width_approx, font_size
    available_width1 = max(10, (split_position_abs - (line_width // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name1 = file_name1_raw
    name1_w, _ = get_text_size(temp_name1, font)
    while name1_w > available_width1 and len(temp_name1) > 3:
        remove_chars = max(1, int(len(temp_name1) * 0.1))
        temp_name1 = temp_name1[:-(remove_chars + 3)] + "..."
        name1_w, _ = get_text_size(temp_name1, font)
        if len(temp_name1) <= 3: break
    if len(temp_name1) > max_length:
        temp_name1 = temp_name1[:max_length - 3] + "..."
    file_name1 = temp_name1 if len(temp_name1) > 3 else ""
    available_width2 = max(10, (orig_width - (split_position_abs + (line_width + 1) // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name2 = file_name2_raw
    name2_w, _ = get_text_size(temp_name2, font)
    while name2_w > available_width2 and len(temp_name2) > 3:
        remove_chars = max(1, int(len(temp_name2) * 0.1))
        temp_name2 = temp_name2[:-(remove_chars + 3)] + "..."
        name2_w, _ = get_text_size(temp_name2, font)
        if len(temp_name2) <= 3: break
    if len(temp_name2) > max_length:
        temp_name2 = temp_name2[:max_length - 3] + "..."
    file_name2 = temp_name2 if len(temp_name2) > 3 else ""
    text_color = text_color_tuple
    if not self.is_horizontal:
        draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size)
    else:
        draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size)

def draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size_func):
    y_baseline = max(margin, orig_height - margin)
    if file_name1:
        text_width1, text_height1 = get_text_size_func(file_name1, font)
        x1_right_edge = split_position_abs - (line_width // 2) - margin
        x1_pos = max(margin, x1_right_edge)
        try:
            draw.text((x1_pos, y_baseline), file_name1, fill=text_color, font=font, anchor="rs")
        except Exception as e:
            print(f"Error drawing filename 1 (vertical): {e}")
            pass
    if file_name2:
        text_width2, text_height2 = get_text_size_func(file_name2, font)
        x2_left_edge = split_position_abs + (line_width + 1) // 2 + margin
        x2_pos = min(orig_width - margin, max(margin, x2_left_edge))
        try:
            draw.text((x2_pos, y_baseline), file_name2, fill=text_color, font=font, anchor="ls")
        except Exception as e:
            print(f"Error drawing filename 2 (vertical): {e}")
            pass

def draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size_func):
    line_top = split_position_abs - (line_height // 2)
    line_bottom = split_position_abs + (line_height + 1) // 2
    if file_name1:
        text_width1, text_height1 = get_text_size_func(file_name1, font)
        x1 = margin
        y1_baseline = line_top - margin
        y1_pos = max(margin, y1_baseline)
        try:
            draw.text((x1, y1_pos), file_name1, fill=text_color, font=font, anchor="ls")
        except Exception as e:
            print(f"Error drawing filename 1 (horizontal): {e}")
            pass
    if file_name2:
        text_width2, text_height2 = get_text_size_func(file_name2, font)
        x2 = margin
        y2_top = line_bottom + margin
        y2_pos = min(orig_height - margin, max(margin, y2_top))
        try:
            draw.text((x2, y2_pos), file_name2, fill=text_color, font=font, anchor="lt")
        except Exception as e:
            print(f"Error drawing filename 2 (horizontal): {e}")
            pass
