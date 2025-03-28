from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QFileDialog, QMessageBox
# QPixmap, QPainter, QColor, QPen, QPainterPath, QImage are used in the main app, not directly needed here except QImage/QPixmap conversion
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF
from translations import tr
import os
import math
# import traceback # Removed import

# --- Helper Functions ---

def get_scaled_pixmap_dimensions(app):
    """Calculates the dimensions the pixmap will have when scaled."""
    # Use result_image size if available, otherwise try original_image1 size
    source_image = app.result_image if app.result_image else app.original_image1
    if not source_image or app.image_label.width() <= 0 or app.image_label.height() <= 0:
        return 0, 0

    orig_width, orig_height = source_image.size
    label_width = app.image_label.width()
    label_height = app.image_label.height()

    if orig_height == 0: return 0, 0 # Prevent division by zero

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

def get_original_coords(app):
    """
    Calculates the original image coordinates for capture centers (for image1 and image2)
    and the magnifier visual midpoint.
    Uses VISUAL (interpolated) positions for smoother magnifier interaction, except when frozen.
    """
    if not app.original_image1 or not app.original_image2:
        return None, None, None

    orig1_width, orig1_height = app.original_image1.size
    orig2_width, orig2_height = app.original_image2.size

    if orig1_width <= 0 or orig1_height <= 0 or orig2_width <= 0 or orig2_height <= 0:
        # print("Warning: Invalid original image dimensions detected in get_original_coords.") # Removed print
        return None, None, None

    # --- Capture Centers ---
    capture_rel_x = app.capture_position_relative.x()
    capture_rel_y = app.capture_position_relative.y()
    cap1_center_orig_x = max(0, min(orig1_width - 1, int(capture_rel_x * orig1_width)))
    cap1_center_orig_y = max(0, min(orig1_height - 1, int(capture_rel_y * orig1_height)))
    capture_center_orig1 = QPoint(cap1_center_orig_x, cap1_center_orig_y)
    cap2_center_orig_x = max(0, min(orig2_width - 1, int(capture_rel_x * orig2_width)))
    cap2_center_orig_y = max(0, min(orig2_height - 1, int(capture_rel_y * orig2_height)))
    capture_center_orig2 = QPoint(cap2_center_orig_x, cap2_center_orig_y)

    # --- Magnifier Visual Midpoint (Based on Image1 coordinate space) ---
    magnifier_center_orig = None
    if app.use_magnifier:
        if app.freeze_magnifier:
            if app.frozen_magnifier_position_relative is not None:
                frozen_rel_x = max(0.0, min(1.0, app.frozen_magnifier_position_relative.x()))
                frozen_rel_y = max(0.0, min(1.0, app.frozen_magnifier_position_relative.y()))
                magn_center_orig_x = max(0, min(orig1_width - 1, int(frozen_rel_x * orig1_width)))
                magn_center_orig_y = max(0, min(orig1_height - 1, int(frozen_rel_y * orig1_height)))
                magnifier_center_orig = QPoint(magn_center_orig_x, magn_center_orig_y)
            else:
                magnifier_center_orig = capture_center_orig1 # Fallback
        else:
            scaled_width, scaled_height = get_scaled_pixmap_dimensions(app)
            if scaled_width > 0 and scaled_height > 0:
                scale_factor_x = orig1_width / scaled_width
                scale_factor_y = orig1_height / scaled_height
                offset_x_orig = app.magnifier_offset_float_visual.x() * scale_factor_x
                offset_y_orig = app.magnifier_offset_float_visual.y() * scale_factor_y
                magn_center_orig_x = capture_center_orig1.x() + int(round(offset_x_orig))
                magn_center_orig_y = capture_center_orig1.y() + int(round(offset_y_orig))
                magn_center_orig_x = max(0, min(orig1_width - 1, magn_center_orig_x))
                magn_center_orig_y = max(0, min(orig1_height - 1, magn_center_orig_y))
                magnifier_center_orig = QPoint(magn_center_orig_x, magn_center_orig_y)
            else:
                 magnifier_center_orig = capture_center_orig1 # Fallback

    if app.use_magnifier and magnifier_center_orig is None:
        magnifier_center_orig = capture_center_orig1

    return capture_center_orig1, capture_center_orig2, magnifier_center_orig


# --- Image Processing Functions (resize_images_processor, update_comparison_processor) ---

def resize_images_processor(app):
    """
    Resizes copies of original images to the maximum dimensions of both
    and stores them in app.image1 and app.image2. Ensures output is RGBA.
    """
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
        # print(f"Error during image resizing: {e}") # Removed print
        app.image1 = None; app.image2 = None
        if hasattr(app, 'current_language'):
            QMessageBox.warning(app, tr("Error", app.current_language), f"{tr('Failed to resize images:', app.current_language)}\n{e}")

def update_comparison_processor(app):
    """Updates the comparison result image based on split position and orientation."""
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


# --- Display Function ---

def display_result_processor(app):
    """Displays the result image on the image_label, drawing overlays using PIL."""
    if not app.result_image:
        app.image_label.clear(); app.pixmap_width = 0; app.pixmap_height = 0; return

    image_to_display = app.result_image.copy()
    draw = ImageDraw.Draw(image_to_display)
    orig_width, orig_height = image_to_display.size # These are max_width, max_height

    # Check if original images exist before proceeding with overlays
    if not app.original_image1 or not app.original_image2:
         # print("Warning: Original images not available for drawing overlays.") # Removed print
         pass # Skip overlays if originals are missing
    else:
        orig1_size = app.original_image1.size
        orig2_size = app.original_image2.size

        # 1. Draw Split Line
        draw_split_line_pil(draw, image_to_display, app.split_position, app.is_horizontal)

        # 2. Draw Magnifier (if enabled)
        if app.use_magnifier:
            current_edge_spacing = app.magnifier_spacing
            capture_pos_orig1, capture_pos_orig2, magnifier_midpoint_orig = get_original_coords(app)

            if capture_pos_orig1 and capture_pos_orig2 and magnifier_midpoint_orig:
                draw_magnifier_pil(
                    draw, image_to_display,
                    app.original_image1, app.original_image2, # Pass originals
                    orig1_size, orig2_size,               # Pass original sizes
                    capture_pos_orig1, capture_pos_orig2, # Pass capture centers
                    magnifier_midpoint_orig,              # Pass visual midpoint
                    app.capture_size, app.magnifier_size, current_edge_spacing
                )
            else:
                 # print("Warning: Failed to get coordinates for magnifier.") # Removed print
                 pass

        # 3. Draw File Names (if enabled)
        if hasattr(app, 'checkbox_file_names') and app.checkbox_file_names.isChecked():
             split_position_abs = int(orig_width * app.split_position) if not app.is_horizontal else int(orig_height * app.split_position)
             line_width_names = max(1, min(5, int(orig_width * 0.0035))) if not app.is_horizontal else 0
             line_height_names = max(1, min(5, int(orig_height * 0.005))) if app.is_horizontal else 0
             color_tuple = app.file_name_color.getRgb()
             draw_file_names_on_image(
                 app, draw, image_to_display,
                 split_position_abs, orig_width, orig_height,
                 line_width_names, line_height_names, color_tuple
             )

    # --- Convert PIL image to QPixmap for display ---
    try:
        qimage = None
        if image_to_display.mode == 'RGBA': qimage = QImage(image_to_display.tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)
        elif image_to_display.mode == 'RGB': qimage = QImage(image_to_display.tobytes("raw", "RGB"), orig_width, orig_height, QImage.Format.Format_RGB888)
        else: qimage = QImage(image_to_display.convert('RGBA').tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)

        if qimage is None or qimage.isNull(): raise ValueError("Failed to create QImage")
        pixmap = QPixmap.fromImage(qimage)
    except Exception as e:
        # print(f"Error converting PIL to QPixmap: {e}") # Removed print
        app.image_label.clear(); return

    # --- Scale and Display on the Label ---
    if not pixmap.isNull():
        scaled_pixmap = pixmap.scaled(app.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        app.pixmap_width = scaled_pixmap.width(); app.pixmap_height = scaled_pixmap.height()
        app.image_label.setPixmap(scaled_pixmap)
    else:
        # print("Error: Created pixmap is null.") # Removed print
        app.image_label.clear(); app.pixmap_width = 0; app.pixmap_height = 0

# --- PIL Drawing Functions ---

def draw_split_line_pil(draw, image, split_position_ratio, is_horizontal):
    """Draws the split line on the PIL image using ImageDraw."""
    width, height = image.size; split_color = (0, 0, 0, 128)
    if not is_horizontal:
        line_x = int(width * split_position_ratio); line_width = max(1, min(5, int(width * 0.0035)))
        line_x = max(line_width // 2, min(width - (line_width + 1) // 2, line_x))
        draw.rectangle([line_x - line_width // 2, 0, line_x + (line_width + 1) // 2, height], fill=split_color)
    else:
        line_y = int(height * split_position_ratio); line_height = max(1, min(5, int(height * 0.005)))
        line_y = max(line_height // 2, min(height - (line_height + 1) // 2, line_y))
        draw.rectangle([0, line_y - line_height // 2, width, line_y + (line_height + 1) // 2], fill=split_color)


def draw_magnifier_pil(draw, image_to_draw_on,
                       image1, image2, orig1_size, orig2_size,
                       capture_pos1, capture_pos2, magnifier_midpoint,
                       base_capture_size, magnifier_size, edge_spacing_input):
    """
    Draws the magnifier overlay using PIL. Uses separate capture positions
    and adjusts capture size for image2 based on original image size ratio.
    """
    if not image1 or not image2 or not capture_pos1 or not capture_pos2 or not magnifier_midpoint:
        # print("Error: Missing images, capture positions, or midpoint in draw_magnifier_pil.") # Removed print
        return
    if not orig1_size or not orig2_size or orig1_size[0] <= 0:
        # print("Error: Missing or invalid original image sizes in draw_magnifier_pil.") # Removed print
        return # Cannot calculate ratio

    # --- Calculate capture size ratio ---
    size_ratio = orig2_size[0] / orig1_size[0] if orig1_size[0] > 0 else 1.0
    capture_size1 = base_capture_size
    capture_size2 = max(10, int(round(base_capture_size * size_ratio))) # Ensure min size

    # --- Draw Capture Area Circle ---
    if capture_pos1:
        draw_capture_area_pil(draw, capture_pos1, base_capture_size) # Use base size for visual cue
    else:
        # print("Warning: capture_pos1 not provided, skipping capture area.") # Removed print
        pass

    # --- Calculate Magnifier Circle Positions ---
    radius = magnifier_size / 2.0
    edge_spacing = max(0.0, float(edge_spacing_input))
    offset_from_midpoint = radius + (edge_spacing / 2.0)
    left_center_x = magnifier_midpoint.x() - offset_from_midpoint
    right_center_x = magnifier_midpoint.x() + offset_from_midpoint
    center_y = magnifier_midpoint.y()
    left_center = QPoint(int(round(left_center_x)), int(round(center_y)))
    right_center = QPoint(int(round(right_center_x)), int(round(center_y)))

    # --- Determine if circles should be combined ---
    should_combine = edge_spacing < 1.0

    if should_combine:
        # Pass BOTH capture sizes
        draw_combined_magnifier_circle_pil(
            image_to_draw_on, magnifier_midpoint,
            capture_pos1, capture_pos2,
            capture_size1, capture_size2, # Pass BOTH sizes
            magnifier_size,
            image1, image2
        )
    else:
        # Left circle (image1) - use capture_size1
        draw_single_magnifier_circle_pil(
            image_to_draw_on, left_center,
            capture_pos1,
            capture_size1, # Use size 1
            magnifier_size,
            image1
        )
        # Right circle (image2) - use capture_size2
        draw_single_magnifier_circle_pil(
            image_to_draw_on, right_center,
            capture_pos2,
            capture_size2, # Use size 2
            magnifier_size,
            image2
        )


def draw_capture_area_pil(draw, center_pos, size):
    """Draws the red capture circle using PIL."""
    radius = size // 2
    bbox = [center_pos.x() - radius, center_pos.y() - radius,
            center_pos.x() + radius, center_pos.y() + radius]
    thickness = max(1, int(math.sqrt(size) * 0.7))
    try:
        draw.ellipse(bbox, outline=(255, 0, 0, 255), width=thickness)
    except Exception as e:
        # print(f"Error drawing capture area ellipse: {e}") # Removed print
        pass


def create_circular_mask(size):
    """Creates a circular alpha mask (L mode) with the given diameter."""
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    return mask

def draw_single_magnifier_circle_pil(target_image, display_center_pos, capture_center,
                                     capture_size, magnifier_size, source_image):
    """Draws one magnified circle from source_image onto target_image using the provided capture_size."""
    if not isinstance(source_image, Image.Image) or not hasattr(source_image, 'size'):
        # print(f"Error (draw_single): Invalid source_image.") # Removed print
        return
    if not isinstance(target_image, Image.Image):
        # print(f"Error (draw_single): Invalid target_image.") # Removed print
        return
    if capture_size <= 0 or magnifier_size <= 0:
        # print(f"Error (draw_single): Invalid sizes (capture={capture_size}, magnify={magnifier_size}).") # Removed print
        return

    orig_width, orig_height = source_image.size
    if orig_width <= 0 or orig_height <= 0:
        # print(f"Error (draw_single): Invalid source dimensions {source_image.size}") # Removed print
        return

    capture_radius = capture_size // 2
    orig_x = capture_center.x() - capture_radius
    orig_y = capture_center.y() - capture_radius

    # Clamp crop box top-left corner
    orig_x_clamped = max(0, min(orig_x, orig_width - 1)) # Prevent starting beyond image edge
    orig_y_clamped = max(0, min(orig_y, orig_height - 1))

    # Calculate actual crop dimensions based on clamped start and available image size
    end_x_actual = min(orig_width, orig_x_clamped + capture_size)
    end_y_actual = min(orig_height, orig_y_clamped + capture_size)
    crop_width = max(0, end_x_actual - orig_x_clamped)
    crop_height = max(0, end_y_actual - orig_y_clamped)

    crop_box = (orig_x_clamped, orig_y_clamped, orig_x_clamped + crop_width, orig_y_clamped + crop_height)
    paste_x = display_center_pos.x() - magnifier_size // 2
    paste_y = display_center_pos.y() - magnifier_size // 2

    if crop_width <= 0 or crop_height <= 0:
        # print(f"Warning (draw_single): Zero crop dimensions ({crop_width}x{crop_height}). Box={crop_box}. Skipping draw.") # Removed print
        try:
            draw = ImageDraw.Draw(target_image)
            placeholder_bbox = [paste_x, paste_y, paste_x + magnifier_size, paste_y + magnifier_size]
            draw.ellipse(placeholder_bbox, fill=(50, 50, 50, 128))
        except Exception: pass
        return

    try:
        captured_area = source_image.crop(crop_box)
        scaled_capture = captured_area.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)
    except Exception as e:
        # print(f"Error (draw_single) cropping/resizing: {e}, CropBox={crop_box}, SourceSize={source_image.size}") # Removed print
        return

    if scaled_capture.mode != 'RGBA':
        try: scaled_capture = scaled_capture.convert('RGBA')
        except Exception as convert_err:
            # print(f"Error (draw_single) converting to RGBA: {convert_err}") # Removed print
            return

    try:
        mask = create_circular_mask(magnifier_size)
        if 'A' in scaled_capture.getbands():
             scaled_capture.putalpha(mask)
        else:
             scaled_capture.putalpha(mask)

    except Exception as mask_err:
        # print(f"Error (draw_single) applying mask: {mask_err}") # Removed print
        return

    try:
        target_image.paste(scaled_capture, (paste_x, paste_y), scaled_capture) # Use image's alpha mask
    except Exception as paste_err:
        # print(f"Error (draw_single) pasting circle: {paste_err}") # Removed print
        return

    try:
        draw = ImageDraw.Draw(target_image)
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size, paste_y + magnifier_size]
        border_thickness = max(1, int(magnifier_size * 0.015))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception as border_err:
        # print(f"Error (draw_single) drawing border: {border_err}") # Removed print
        pass


def draw_combined_magnifier_circle_pil(target_image, display_center_pos,
                                       capture_center1, capture_center2,
                                       capture_size1, capture_size2, # SEPARATE SIZES
                                       magnifier_size,
                                       image1, image2):
    """Draws a combined half-left/half-right magnifier circle using individual capture centers and sizes."""
    if not image1 or not image2 or not capture_center1 or not capture_center2:
        # print(f"  ERROR: Combined - Missing images or capture centers.") # Removed print
        return
    if capture_size1 <= 0 or capture_size2 <= 0 or magnifier_size <= 0:
        # print(f"  ERROR: Combined - Invalid sizes (cap1={capture_size1}, cap2={capture_size2}, mag={magnifier_size}).") # Removed print
        return

    orig1_width, orig1_height = image1.size
    orig2_width, orig2_height = image2.size

    # --- Calculate and Validate crop_box1 ---
    cap1_radius = capture_size1 // 2
    orig1_x = capture_center1.x() - cap1_radius
    orig1_y = capture_center1.y() - cap1_radius
    orig1_x_clamped = max(0, min(orig1_x, orig1_width - 1))
    orig1_y_clamped = max(0, min(orig1_y, orig1_height - 1))
    end1_x = min(orig1_width, orig1_x_clamped + capture_size1)
    end1_y = min(orig1_height, orig1_y_clamped + capture_size1)
    crop1_width = max(0, end1_x - orig1_x_clamped)
    crop1_height = max(0, end1_y - orig1_y_clamped)
    crop_box1 = (orig1_x_clamped, orig1_y_clamped, orig1_x_clamped + crop1_width, orig1_y_clamped + crop1_height)
    if crop1_width <= 0 or crop1_height <= 0:
        # print(f"  ERROR: Combined - Crop1 dimensions non-positive ({crop1_width}x{crop1_height}). Box={crop_box1}") # Removed print
        return

    # --- Calculate and Validate crop_box2 ---
    cap2_radius = capture_size2 // 2
    orig2_x = capture_center2.x() - cap2_radius
    orig2_y = capture_center2.y() - cap2_radius
    orig2_x_clamped = max(0, min(orig2_x, orig2_width - 1))
    orig2_y_clamped = max(0, min(orig2_y, orig2_height - 1))
    end2_x = min(orig2_width, orig2_x_clamped + capture_size2)
    end2_y = min(orig2_height, orig2_y_clamped + capture_size2)
    crop2_width = max(0, end2_x - orig2_x_clamped)
    crop2_height = max(0, end2_y - orig2_y_clamped)
    crop_box2 = (orig2_x_clamped, orig2_y_clamped, orig2_x_clamped + crop2_width, orig2_y_clamped + crop2_height)
    if crop2_width <= 0 or crop2_height <= 0:
        # print(f"  ERROR: Combined - Crop2 dimensions non-positive ({crop2_width}x{crop2_height}). Box={crop_box2}") # Removed print
        return

    # --- Crop and Resize ---
    try:
        captured_area1 = image1.crop(crop_box1)
        captured_area2 = image2.crop(crop_box2)
        if captured_area1.width <= 0 or captured_area1.height <= 0 or captured_area2.width <= 0 or captured_area2.height <= 0:
            raise ValueError("Captured area has zero size after crop.")

        scaled_capture1 = captured_area1.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)
        scaled_capture2 = captured_area2.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)

        if scaled_capture1.size != (magnifier_size, magnifier_size) or scaled_capture2.size != (magnifier_size, magnifier_size):
             raise ValueError(f"Resize failed. Target:({magnifier_size},{magnifier_size}), Got: SC1={scaled_capture1.size}, SC2={scaled_capture2.size}")

    except Exception as e:
        # print(f"  ERROR: Combined - Exception during crop/resize: {e}") # Removed print
        # traceback.print_exc() # Removed traceback
        return

    # --- Crop and Paste Halves ---
    magnifier_img = Image.new('RGBA', (magnifier_size, magnifier_size))
    half_width = max(0, magnifier_size // 2)
    right_half_start = half_width
    right_half_width = magnifier_size - right_half_start

    try:
        left_half = scaled_capture1.crop((0, 0, half_width, magnifier_size))
        if right_half_start < scaled_capture2.width and right_half_width > 0:
             right_half = scaled_capture2.crop((right_half_start, 0, right_half_start + right_half_width, magnifier_size))
        else:
             right_half = Image.new('RGBA', (max(0, right_half_width), magnifier_size), (0,0,0,0)) # Empty

        magnifier_img.paste(left_half, (0, 0))
        if right_half.width > 0: magnifier_img.paste(right_half, (right_half_start, 0))

    except Exception as paste_err:
         # print(f"  ERROR: Combined - Exception during half crop/paste: {paste_err}") # Removed print
         # traceback.print_exc() # Removed traceback
         return

    # --- Apply Mask and Final Paste ---
    try:
        mask = create_circular_mask(magnifier_size)
        if 'A' in magnifier_img.getbands(): magnifier_img.putalpha(mask) # Replace alpha if exists
        else: magnifier_img.putalpha(mask)

        paste_x = display_center_pos.x() - magnifier_size // 2
        paste_y = display_center_pos.y() - magnifier_size // 2
        target_image.paste(magnifier_img, (paste_x, paste_y), magnifier_img) # Use alpha mask
    except Exception as final_err:
        # print(f"  ERROR: Combined - Exception during mask/final paste: {final_err}") # Removed print
        # traceback.print_exc() # Removed traceback
        return

    # --- Draw Border/Line ---
    try:
        draw = ImageDraw.Draw(target_image)
        line_width_div = max(1, int(magnifier_size * 0.025))
        draw.rectangle([paste_x + half_width - line_width_div // 2, paste_y,
                        paste_x + half_width + (line_width_div + 1) // 2, paste_y + magnifier_size],
                       fill=(255, 255, 255, 255))
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size, paste_y + magnifier_size]
        border_thickness = max(1, int(magnifier_size * 0.02))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception as draw_err:
        # print(f"  ERROR: Combined - Exception drawing border/line: {draw_err}") # Removed print
        pass
    # print(f"--- Combined END (Success) ---") # DEBUG # Removed print


# --- Save Function ---

def save_result_processor(self): # Takes 'self' to access app state
    """Saves the comparison result image to a file, drawing overlays using PIL."""
    if not self.original_image1 or not self.original_image2:
        QMessageBox.warning(self, tr("Warning", self.current_language), tr("Please load both images first.", self.current_language)); return
    if not self.image1 or not self.image2:
        QMessageBox.warning(self, tr("Warning", self.current_language), tr("Resized images not available. Please reload.", self.current_language)); return

    img1_rgba = self.image1; img2_rgba = self.image2
    width, height = img1_rgba.size # Use size of the already resized working copies

    # Create the base image
    image_to_save = Image.new('RGBA', (width, height))
    split_position_abs = 0
    if not self.is_horizontal:
        split_position_abs = max(0, min(width, int(width * self.split_position)))
        if split_position_abs > 0: image_to_save.paste(img1_rgba.crop((0, 0, split_position_abs, height)), (0, 0))
        if split_position_abs < width: image_to_save.paste(img2_rgba.crop((split_position_abs, 0, width, height)), (split_position_abs, 0))
    else:
        split_position_abs = max(0, min(height, int(height * self.split_position)))
        if split_position_abs > 0: image_to_save.paste(img1_rgba.crop((0, 0, width, split_position_abs)), (0, 0))
        if split_position_abs < height: image_to_save.paste(img2_rgba.crop((0, split_position_abs, width, height)), (0, split_position_abs))

    # --- Draw Overlays ---
    draw = ImageDraw.Draw(image_to_save)
    orig1_size = self.original_image1.size # Need original sizes for magnifier calculation
    orig2_size = self.original_image2.size

    # 1. Draw Split Line
    draw_split_line_pil(draw, image_to_save, self.split_position, self.is_horizontal)

    # 2. Draw File Names (if enabled)
    if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
        line_width_names = max(1, min(5, int(width * 0.0035))) if not self.is_horizontal else 0
        line_height_names = max(1, min(5, int(height * 0.005))) if self.is_horizontal else 0
        color_tuple = self.file_name_color.getRgb()
        draw_file_names_on_image(self, draw, image_to_save, split_position_abs, width, height, line_width_names, line_height_names, color_tuple)

    # 3. Draw Magnifier (if enabled)
    if self.use_magnifier:
        final_edge_spacing = self.magnifier_spacing
        capture_pos_orig1, capture_pos_orig2, magnifier_midpoint_orig = get_original_coords(self)

        # Ensure sizes are valid before drawing magnifier
        if orig1_size and orig2_size and orig1_size[0] > 0 and orig2_size[0] > 0:
            if capture_pos_orig1 and capture_pos_orig2 and magnifier_midpoint_orig:
                draw_magnifier_pil(
                    draw, image_to_save,
                    self.original_image1, self.original_image2,
                    orig1_size, orig2_size,               # Pass original sizes
                    capture_pos_orig1, capture_pos_orig2,
                    magnifier_midpoint_orig,
                    self.capture_size, self.magnifier_size, final_edge_spacing
                )
            else:
                # print("Warning (Save): Failed to get coordinates for magnifier.") # Removed print
                pass
        else:
            # print("Warning (Save): Invalid original image sizes for magnifier calculation.") # Removed print
            pass


    # --- Ask for Filename ---
    file_name, selected_filter = QFileDialog.getSaveFileName(self, tr("Save Image", self.current_language), "", "PNG Files (*.png);;JPEG Files (*.jpg *.jpeg);;All Files (*)")
    if not file_name: return

    _, ext = os.path.splitext(file_name)
    if not ext: file_name += '.png' # Default to PNG
    if "JPEG" in selected_filter and not file_name.lower().endswith((".jpg", ".jpeg")): file_name += '.jpg'
    elif "PNG" in selected_filter and not file_name.lower().endswith(".png"): file_name += '.png'

    # --- Save the Image ---
    try:
        if file_name.lower().endswith((".jpg", ".jpeg")):
            # Create white background for JPG and paste RGBA image onto it
            background = Image.new("RGB", image_to_save.size, (255, 255, 255))
            if image_to_save.mode == 'RGBA': background.paste(image_to_save, mask=image_to_save.split()[3]) # Use alpha
            else: background.paste(image_to_save.convert("RGB"))
            background.save(file_name, "JPEG", quality=93)
        else: # Assume PNG or other format supporting transparency
            image_to_save.save(file_name, "PNG") # Force PNG for transparency
        # print(f"Image saved to {file_name}") # Removed print
    except Exception as e:
        QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)} {str(e)}")


# --- Filename Drawing ---

def draw_file_names_on_image(self, draw, image, split_pos_abs, orig_width, orig_height, line_width, line_height, text_color_tuple):
    """Draws file names on the image using PIL Draw object and specified color."""
    font_size_percentage = self.font_size_slider.value() / 200.0
    base_font_size_ratio = 0.03
    font_size = max(10, int(orig_height * base_font_size_ratio * font_size_percentage))
    base_margin = 5; additional_margin = int(font_size * 0.1)
    margin = min(base_margin + additional_margin, int(orig_height * 0.03))
    font_path = "./SourceSans3-Regular.ttf"
    try: font = ImageFont.truetype(font_path, size=font_size)
    except IOError:
        # print(f"Warning: Font '{font_path}' not found. Using default.") # Removed print
        font = ImageFont.load_default() # Fallback

    file_name1_raw = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else "Image 1")
    file_name2_raw = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else "Image 2")
    max_length = self.max_name_length

    def get_text_size(text, font_to_use):
         if hasattr(font_to_use, 'getbbox'): bbox = draw.textbbox((0, 0), text, font=font_to_use); return bbox[2] - bbox[0], bbox[3] - bbox[1]
         elif hasattr(draw, 'textlength'): return draw.textlength(text, font=font_to_use), font_to_use.getmetrics()[0] if hasattr(font_to_use,'getmetrics') else font_size
         else: return len(text) * font_size * 0.6, font_size # Estimate

    available_width1 = max(10, (split_pos_abs - (line_width // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name1 = file_name1_raw; name1_w, _ = get_text_size(temp_name1, font)
    while name1_w > available_width1 and len(temp_name1) > 3: temp_name1 = temp_name1[:-4] + "..."; name1_w, _ = get_text_size(temp_name1, font)
    if len(temp_name1) > max_length: temp_name1 = temp_name1[:max_length - 3] + "..."
    file_name1 = temp_name1

    available_width2 = max(10, (orig_width - (split_pos_abs + (line_width + 1) // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name2 = file_name2_raw; name2_w, _ = get_text_size(temp_name2, font)
    while name2_w > available_width2 and len(temp_name2) > 3: temp_name2 = temp_name2[:-4] + "..."; name2_w, _ = get_text_size(temp_name2, font)
    if len(temp_name2) > max_length: temp_name2 = temp_name2[:max_length - 3] + "..."
    file_name2 = temp_name2

    text_color = text_color_tuple
    if not self.is_horizontal: draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_pos_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size)
    else: draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_pos_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size)


def draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_pos_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size_func):
    """Draws filenames for vertical split using PIL."""
    text_margin_x = margin; text_margin_y_factor = 0.35
    text_width1, text_height1 = get_text_size_func(file_name1, font)
    x1 = max(margin, split_pos_abs - (line_width // 2) - text_width1 - text_margin_x)
    text_margin_y1 = max(margin, int(text_height1 * text_margin_y_factor))
    y1 = max(margin, orig_height - text_height1 - text_margin_y1)
    draw.text((x1, y1), file_name1, fill=text_color, font=font)

    text_width2, text_height2 = get_text_size_func(file_name2, font)
    x2 = min(orig_width - text_width2 - margin, split_pos_abs + (line_width + 1) // 2 + text_margin_x)
    text_margin_y2 = max(margin, int(text_height2 * text_margin_y_factor))
    y2 = max(margin, orig_height - text_height2 - text_margin_y2)
    draw.text((x2, y2), file_name2, fill=text_color, font=font)


def draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_pos_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size_func):
    """Draws filenames for horizontal split using PIL."""
    line_top = split_pos_abs - (line_height // 2); line_bottom = split_pos_abs + (line_height + 1) // 2
    top_margin = int(margin * 1.5); bottom_margin = int(margin * 0.5)
    text_width1, text_height1 = get_text_size_func(file_name1, font)
    x1_clamped = max(margin, min(margin, orig_width - text_width1 - margin))
    y1 = max(margin, line_top - text_height1 - top_margin)
    draw.text((x1_clamped, y1), file_name1, fill=text_color, font=font)

    text_width2, text_height2 = get_text_size_func(file_name2, font)
    x2_clamped = max(margin, min(margin, orig_width - text_width2 - margin))
    y2 = max(line_bottom + margin, min(line_bottom + bottom_margin, orig_height - text_height2 - margin))
    draw.text((x2_clamped, y2), file_name2, fill=text_color, font=font)
