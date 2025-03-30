from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QPixmap, QImage, QColor
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF
try:
    from translations import tr
except ImportError:
    print("Warning: 'translations.py' not found. Using fallback translation.")
    def tr(text, lang='en', *args, **kwargs):
        return text
import os
import math

_module_dir = os.path.dirname(os.path.abspath(__file__))
_font_file_name = "SourceSans3-Regular.ttf"
_font_path_absolute = os.path.join(_module_dir, _font_file_name)

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

def get_original_coords(app):
    if not app.original_image1 or not app.original_image2:
        return None, None, None

    orig1_width, orig1_height = app.original_image1.size
    orig2_width, orig2_height = app.original_image2.size

    if orig1_width <= 0 or orig1_height <= 0 or orig2_width <= 0 or orig2_height <= 0:
        return None, None, None

    capture_rel_x = app.capture_position_relative.x()
    capture_rel_y = app.capture_position_relative.y()
    cap1_center_orig_x = max(0, min(orig1_width - 1, int(capture_rel_x * orig1_width)))
    cap1_center_orig_y = max(0, min(orig1_height - 1, int(capture_rel_y * orig1_height)))
    capture_center_orig1 = QPoint(cap1_center_orig_x, cap1_center_orig_y)

    cap2_center_orig_x = max(0, min(orig2_width - 1, int(capture_rel_x * orig2_width)))
    cap2_center_orig_y = max(0, min(orig2_height - 1, int(capture_rel_y * orig2_height)))
    capture_center_orig2 = QPoint(cap2_center_orig_x, cap2_center_orig_y)

    magnifier_midpoint_result = None

    result_width, result_height = 0, 0
    if app.result_image:
        result_width, result_height = app.result_image.size

    cap_center_res_x = -1
    cap_center_res_y = -1
    if result_width > 0 and result_height > 0:
        cap_center_res_x = max(0, min(result_width - 1, int(capture_rel_x * result_width)))
        cap_center_res_y = max(0, min(result_height - 1, int(capture_rel_y * result_height)))

    if app.use_magnifier:
        if app.freeze_magnifier:
            if app.frozen_magnifier_position_relative is not None and result_width > 0 and result_height > 0:
                frozen_rel_x = max(0.0, min(1.0, app.frozen_magnifier_position_relative.x()))
                frozen_rel_y = max(0.0, min(1.0, app.frozen_magnifier_position_relative.y()))
                magn_center_res_x = max(0, min(result_width - 1, int(frozen_rel_x * result_width)))
                magn_center_res_y = max(0, min(result_height - 1, int(frozen_rel_y * result_height)))
                magnifier_midpoint_result = QPoint(magn_center_res_x, magn_center_res_y)
            elif cap_center_res_x != -1:
                 magnifier_midpoint_result = QPoint(cap_center_res_x, cap_center_res_y)
        else:
            scaled_width, scaled_height = get_scaled_pixmap_dimensions(app)
            if scaled_width > 0 and scaled_height > 0 and result_width > 0 and result_height > 0 and cap_center_res_x != -1:
                scale_pix_to_res_x = result_width / float(scaled_width) if scaled_width != 0 else 0
                scale_pix_to_res_y = result_height / float(scaled_height) if scaled_height != 0 else 0

                if abs(scale_pix_to_res_x) > 1e-6 and abs(scale_pix_to_res_y) > 1e-6:
                    offset_res_x = app.magnifier_offset_float_visual.x() * scale_pix_to_res_x
                    offset_res_y = app.magnifier_offset_float_visual.y() * scale_pix_to_res_y

                    magn_center_res_x = cap_center_res_x + int(round(offset_res_x))
                    magn_center_res_y = cap_center_res_y + int(round(offset_res_y))

                    magn_center_res_x = max(0, min(result_width - 1, magn_center_res_x))
                    magn_center_res_y = max(0, min(result_height - 1, magn_center_res_y))
                    magnifier_midpoint_result = QPoint(magn_center_res_x, magn_center_res_y)
                else:
                    magnifier_midpoint_result = QPoint(cap_center_res_x, cap_center_res_y)
            elif cap_center_res_x != -1:
                 magnifier_midpoint_result = QPoint(cap_center_res_x, cap_center_res_y)

    return capture_center_orig1, capture_center_orig2, magnifier_midpoint_result

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
    if not app.result_image:
        app.image_label.clear(); app.pixmap_width = 0; app.pixmap_height = 0; return

    image_to_display = app.result_image.copy()
    draw = ImageDraw.Draw(image_to_display)
    orig_width, orig_height = image_to_display.size

    scaled_width, scaled_height = get_scaled_pixmap_dimensions(app)
    scale_factor = 1.0
    if orig_width > 0 and scaled_width > 0:
        scale_factor = scaled_width / float(orig_width)
    elif orig_height > 0 and scaled_height > 0:
        scale_factor = scaled_height / float(orig_height)

    magnifier_size_to_draw = app.magnifier_size
    if scale_factor > 1e-6:
        magnifier_size_to_draw = int(round(app.magnifier_size / scale_factor))
    magnifier_size_to_draw = max(10, magnifier_size_to_draw)

    if not app.original_image1 or not app.original_image2:
         pass
    else:
        orig1_size = app.original_image1.size
        orig2_size = app.original_image2.size

        draw_split_line_pil(draw, image_to_display, app.split_position, app.is_horizontal)

        if app.use_magnifier:
            current_edge_spacing = app.magnifier_spacing
            capture_pos_orig1, capture_pos_orig2, magnifier_midpoint_result = get_original_coords(app)

            if capture_pos_orig1 and capture_pos_orig2 and magnifier_midpoint_result:
                draw_magnifier_pil(
                    draw, image_to_display,
                    app.original_image1,
                    app.original_image2,
                    orig1_size,
                    orig2_size,
                    capture_pos_orig1,
                    capture_pos_orig2,
                    magnifier_midpoint_result,
                    app.capture_size,
                    magnifier_size_to_draw,
                    current_edge_spacing,
                    app
                )

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

    try:
        qimage = None
        if image_to_display.mode == 'RGBA': qimage = QImage(image_to_display.tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)
        elif image_to_display.mode == 'RGB': qimage = QImage(image_to_display.tobytes("raw", "RGB"), orig_width, orig_height, QImage.Format.Format_RGB888)
        else: qimage = QImage(image_to_display.convert('RGBA').tobytes("raw", "RGBA"), orig_width, orig_height, QImage.Format.Format_RGBA8888)

        if qimage is None or qimage.isNull(): raise ValueError("Failed to create QImage")
        pixmap = QPixmap.fromImage(qimage)
    except Exception as e:
        app.image_label.clear(); return

    if not pixmap.isNull():
        scaled_pixmap = pixmap.scaled(app.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        app.pixmap_width = scaled_pixmap.width(); app.pixmap_height = scaled_pixmap.height()
        app.image_label.setPixmap(scaled_pixmap)
    else:
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
                       image1, image2, orig1_size, orig2_size,
                       capture_pos1, capture_pos2,
                       magnifier_midpoint_result,
                       base_capture_size,
                       magnifier_size,
                       edge_spacing_input,
                       app):

    if not image1 or not image2 or not capture_pos1 or not capture_pos2 or not magnifier_midpoint_result:
        return
    if not orig1_size or not orig2_size or orig1_size[0] <= 0 or orig1_size[1] <= 0 or orig2_size[0] <= 0 or orig2_size[1] <= 0:
        return

    result_width, result_height = image_to_draw_on.size
    if result_width <= 0 or result_height <= 0:
        return

    capture_size_for_orig1 = base_capture_size
    capture_size_for_orig2 = base_capture_size

    if result_width > 0 and orig1_size[0] > 0:
        scale_res_to_orig1 = orig1_size[0] / float(result_width)
        capture_size_for_orig1 = max(10, int(round(base_capture_size * scale_res_to_orig1)))
    elif result_height > 0 and orig1_size[1] > 0:
        scale_res_to_orig1 = orig1_size[1] / float(result_height)
        capture_size_for_orig1 = max(10, int(round(base_capture_size * scale_res_to_orig1)))
    else:
        capture_size_for_orig1 = max(10, int(round(base_capture_size)))

    if result_width > 0 and orig2_size[0] > 0:
        scale_res_to_orig2 = orig2_size[0] / float(result_width)
        capture_size_for_orig2 = max(10, int(round(base_capture_size * scale_res_to_orig2)))
    elif result_height > 0 and orig2_size[1] > 0:
        scale_res_to_orig2 = orig2_size[1] / float(result_height)
        capture_size_for_orig2 = max(10, int(round(base_capture_size * scale_res_to_orig2)))
    else:
        capture_size_for_orig2 = max(10, int(round(base_capture_size)))


    capture_center_for_marker_x = int(app.capture_position_relative.x() * result_width)
    capture_center_for_marker_y = int(app.capture_position_relative.y() * result_height)
    capture_center_for_marker = QPoint(capture_center_for_marker_x, capture_center_for_marker_y)
    marker_size = max(10, int(round(base_capture_size)))
    draw_capture_area_pil(draw, capture_center_for_marker, marker_size)

    radius = magnifier_size / 2.0
    edge_spacing = max(0.0, float(edge_spacing_input))
    offset_from_midpoint = radius + (edge_spacing / 2.0)
    left_center_x = magnifier_midpoint_result.x() - offset_from_midpoint
    right_center_x = magnifier_midpoint_result.x() + offset_from_midpoint
    center_y = magnifier_midpoint_result.y()
    left_center = QPoint(int(round(left_center_x)), int(round(center_y)))
    right_center = QPoint(int(round(right_center_x)), int(round(center_y)))

    should_combine = edge_spacing < 1.0

    if should_combine:
        draw_combined_magnifier_circle_pil(
            image_to_draw_on, magnifier_midpoint_result,
            capture_pos1, capture_pos2,
            capture_size_for_orig1, capture_size_for_orig2,
            magnifier_size,
            image1, image2
        )
    else:
        draw_single_magnifier_circle_pil(
            image_to_draw_on, left_center,
            capture_pos1,
            capture_size_for_orig1,
            magnifier_size,
            image1
        )
        draw_single_magnifier_circle_pil(
            image_to_draw_on, right_center,
            capture_pos2,
            capture_size_for_orig2,
            magnifier_size,
            image2
        )


def draw_capture_area_pil(draw, center_pos, size):
    if size <= 0 or center_pos is None: return
    radius = size // 2
    bbox = [center_pos.x() - radius, center_pos.y() - radius,
            center_pos.x() + radius, center_pos.y() + radius]
    thickness = max(1, int(math.sqrt(size) * 0.25))
    try:
        draw.ellipse(bbox, outline=(255, 0, 0, 255), width=thickness)
    except Exception as e:
        pass


def create_circular_mask(size):
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    return mask

def draw_single_magnifier_circle_pil(target_image, display_center_pos,
                                     capture_center_orig,
                                     capture_size_orig,
                                     magnifier_size,
                                     image_for_crop):
    if not isinstance(image_for_crop, Image.Image) or not hasattr(image_for_crop, 'size'): return
    if not isinstance(target_image, Image.Image): return
    if capture_size_orig <= 0 or magnifier_size <= 0: return

    source_width, source_height = image_for_crop.size
    if source_width <= 0 or source_height <= 0: return

    capture_radius_orig = capture_size_orig // 2
    crop_x = capture_center_orig.x() - capture_radius_orig
    crop_y = capture_center_orig.y() - capture_radius_orig
    crop_x_clamped = max(0, min(crop_x, source_width - capture_size_orig))
    crop_y_clamped = max(0, min(crop_y, source_height - capture_size_orig))

    paste_x = display_center_pos.x() - magnifier_size // 2
    paste_y = display_center_pos.y() - magnifier_size // 2

    try:
        crop_box = (crop_x_clamped, crop_y_clamped, crop_x_clamped + capture_size_orig, crop_y_clamped + capture_size_orig)
        captured_area = image_for_crop.crop(crop_box)
        scaled_capture = captured_area.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)
    except Exception as e:
        return

    if scaled_capture.mode != 'RGBA':
        try: scaled_capture = scaled_capture.convert('RGBA')
        except Exception: return

    try:
        mask = create_circular_mask(magnifier_size)
        scaled_capture.putalpha(mask)
    except Exception: return

    try:
        target_image.paste(scaled_capture, (paste_x, paste_y), scaled_capture)
    except Exception: return

    try:
        draw = ImageDraw.Draw(target_image)
        border_bbox = [paste_x, paste_y, paste_x + magnifier_size, paste_y + magnifier_size]
        border_thickness = max(1, int(magnifier_size * 0.015))
        draw.ellipse(border_bbox, outline=(255, 255, 255, 255), width=border_thickness)
    except Exception: pass


def draw_combined_magnifier_circle_pil(target_image, display_center_pos,
                                       capture_center_orig1, capture_center_orig2,
                                       capture_size_orig1, capture_size_orig2,
                                       magnifier_size,
                                       image1_for_crop, image2_for_crop):
    if not image1_for_crop or not image2_for_crop or not capture_center_orig1 or not capture_center_orig2: return
    if capture_size_orig1 <= 0 or capture_size_orig2 <= 0 or magnifier_size <= 0: return

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
    except Exception as e:
        return

    try:
        crop2_x = capture_center_orig2.x() - cap_radius_orig2; crop2_y = capture_center_orig2.y() - cap_radius_orig2
        crop2_x_clamped = max(0, min(crop2_x, source2_width - capture_size_orig2))
        crop2_y_clamped = max(0, min(crop2_y, source2_height - capture_size_orig2))
        crop_box2 = (crop2_x_clamped, crop2_y_clamped, crop2_x_clamped + capture_size_orig2, crop2_y_clamped + capture_size_orig2)
        captured_area2 = image2_for_crop.crop(crop_box2)
    except Exception as e:
        return

    try:
        scaled_capture1 = captured_area1.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)
        scaled_capture2 = captured_area2.resize((magnifier_size, magnifier_size), Image.Resampling.LANCZOS)
    except Exception as e:
        return

    magnifier_img = Image.new('RGBA', (magnifier_size, magnifier_size))
    half_width = max(0, magnifier_size // 2)
    right_half_start = half_width
    right_half_width = magnifier_size - right_half_start

    try:
        left_half = scaled_capture1.crop((0, 0, half_width, magnifier_size))
        if right_half_start < scaled_capture2.width and right_half_width > 0:
             right_half = scaled_capture2.crop((right_half_start, 0, right_half_start + right_half_width, magnifier_size))
        else:
             right_half = Image.new('RGBA', (max(0, right_half_width), magnifier_size), (0,0,0,0))

        magnifier_img.paste(left_half, (0, 0))
        if right_half.width > 0:
             magnifier_img.paste(right_half, (right_half_start, 0))
    except Exception as paste_err:
        return

    try:
        mask = create_circular_mask(magnifier_size)
        magnifier_img.putalpha(mask)
        paste_x = display_center_pos.x() - magnifier_size // 2
        paste_y = display_center_pos.y() - magnifier_size // 2
        target_image.paste(magnifier_img, (paste_x, paste_y), magnifier_img)
    except Exception as final_err:
        return

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
        pass


def save_result_processor(self):
    print("--- save_result_processor (Corrected Magnifier & Marker Size) ---")
    if not self.original_image1 or not self.original_image2:
        QMessageBox.warning(self, tr("Warning", self.current_language), tr("Please load and select images in both slots first.", self.current_language))
        print("  Save aborted: Original images missing.")
        return

    if not self.image1 or not self.image2:
        QMessageBox.warning(self, tr("Warning", self.current_language), tr("Resized images not available. Please reload or select images.", self.current_language))
        print("  Save aborted: Resized working images (self.image1/image2) missing.")
        return

    img1_rgba = self.image1
    img2_rgba = self.image2
    width, height = img1_rgba.size
    print(f"  Save base image dimensions: {width}x{height}")

    image_to_save = Image.new('RGBA', (width, height))
    split_position_abs = 0
    if not self.is_horizontal:
        split_position_abs = max(0, min(width, int(width * self.split_position)))
        print(f"  Vertical split at abs position: {split_position_abs}")
        if split_position_abs > 0:
            image_to_save.paste(img1_rgba.crop((0, 0, split_position_abs, height)), (0, 0))
        if split_position_abs < width:
            image_to_save.paste(img2_rgba.crop((split_position_abs, 0, width, height)), (split_position_abs, 0))
    else:
        split_position_abs = max(0, min(height, int(height * self.split_position)))
        print(f"  Horizontal split at abs position: {split_position_abs}")
        if split_position_abs > 0:
            image_to_save.paste(img1_rgba.crop((0, 0, width, split_position_abs)), (0, 0))
        if split_position_abs < height:
            image_to_save.paste(img2_rgba.crop((0, split_position_abs, width, height)), (0, split_position_abs))

    draw = ImageDraw.Draw(image_to_save)
    orig1_size = self.original_image1.size
    orig2_size = self.original_image2.size
    print(f"  Original sizes for overlays: 1={orig1_size}, 2={orig2_size}")

    valid_orig_sizes = orig1_size and orig2_size and orig1_size[0] > 0 and orig1_size[1] > 0 and orig2_size[0] > 0 and orig2_size[1] > 0
    print(f"  Original sizes valid for magnifier: {valid_orig_sizes}")

    save_split_color = (128, 128, 128, 255)
    print("  Drawing split line for save...")
    draw_split_line_pil(draw, image_to_save, self.split_position, self.is_horizontal, split_color=save_split_color)

    if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
        print("  Drawing file names for save...")
        line_width_names = max(1, min(5, int(width * 0.0035))) if not self.is_horizontal else 0
        line_height_names = max(1, min(5, int(height * 0.005))) if self.is_horizontal else 0
        color_tuple = self.file_name_color.getRgb()
        draw_file_names_on_image(self, draw, image_to_save, split_position_abs, width, height, line_width_names, line_height_names, color_tuple)
    else:
        print("  Skipping file names drawing (disabled).")

    if self.use_magnifier and valid_orig_sizes:
        print("  Drawing magnifier for save...")

        scaled_width_display, scaled_height_display = get_scaled_pixmap_dimensions(self)
        orig_width_save, orig_height_save = image_to_save.size
        scale_factor_display = 1.0
        if orig_width_save > 0 and scaled_width_display > 0:
            scale_factor_display = scaled_width_display / float(orig_width_save)
        elif orig_height_save > 0 and scaled_height_display > 0:
            scale_factor_display = scaled_height_display / float(orig_height_save)
        magnifier_size_for_save = self.magnifier_size
        if scale_factor_display > 1e-6:
            magnifier_size_for_save = int(round(self.magnifier_size / scale_factor_display))
        magnifier_size_for_save = max(10, magnifier_size_for_save)
        print(f"  Save - Display Scale Factor: {scale_factor_display:.3f}, Slider Size: {self.magnifier_size}, Calculated Magnifier Draw Size for Save: {magnifier_size_for_save}")

        final_edge_spacing = self.magnifier_spacing
        capture_pos_orig1, capture_pos_orig2, magnifier_midpoint_result_for_save = get_original_coords(self)
        print(f"  Coords from get_original_coords: cap1={capture_pos_orig1}, cap2={capture_pos_orig2}, midpoint(res)={magnifier_midpoint_result_for_save}")

        midpoint_to_use_for_draw = None
        if capture_pos_orig1 and capture_pos_orig2 and magnifier_midpoint_result_for_save:
            save_width, save_height = image_to_save.size
            res_width = res_height = 0
            if self.result_image: res_width, res_height = self.result_image.size

            if save_width == res_width and save_height == res_height:
                midpoint_to_use_for_draw = magnifier_midpoint_result_for_save
                print(f"  Using midpoint from get_original_coords directly: {midpoint_to_use_for_draw}")
            else:
                print(f"  Warning: Save image size ({save_width}x{save_height}) differs from last result image size ({res_width}x{res_height}). Recalculating midpoint based on capture center.")
                cap_center_save_x = max(0, min(width - 1, int(self.capture_position_relative.x() * width)))
                cap_center_save_y = max(0, min(height - 1, int(self.capture_position_relative.y() * height)))
                midpoint_to_use_for_draw = QPoint(cap_center_save_x, cap_center_save_y)
                print(f"  Using fallback midpoint (capture center in save coords): {midpoint_to_use_for_draw}")

            if midpoint_to_use_for_draw:
                draw_magnifier_pil(
                    draw, image_to_save,
                    self.original_image1,
                    self.original_image2,
                    orig1_size,
                    orig2_size,
                    capture_pos_orig1,
                    capture_pos_orig2,
                    midpoint_to_use_for_draw,
                    self.capture_size,
                    magnifier_size_for_save,
                    final_edge_spacing,
                    self
                )
            else:
                 print("  Save Warning: Failed to determine midpoint for magnifier drawing.")
        else:
             print("  Save Warning: Failed to get valid magnifier coordinates for saving.")
    elif self.use_magnifier and not valid_orig_sizes:
        print("  Save Warning: Cannot draw magnifier due to invalid original image sizes.")
        pass
    else:
        print("  Skipping magnifier drawing (disabled or invalid sizes).")

    print("  Opening save file dialog...")
    file_name, selected_filter = QFileDialog.getSaveFileName(
        self,
        tr("Save Image", self.current_language),
        "",
        tr("PNG Files", self.current_language) + " (*.png);;" + tr("JPEG Files", self.current_language) + " (*.jpg *.jpeg);;" + tr("All Files", self.current_language) + " (*)"
    )

    if not file_name:
        print("  Save cancelled by user.")
        return

    print(f"  User selected filename: {file_name}, filter: {selected_filter}")

    _, ext = os.path.splitext(file_name)
    original_file_name = file_name
    if not ext:
        if "JPEG" in selected_filter: file_name += '.jpg'
        else: file_name += '.png'
    else:
        ext_lower = ext.lower()
        if "JPEG" in selected_filter and ext_lower not in (".jpg", ".jpeg"):
             file_name = os.path.splitext(file_name)[0] + '.jpg'
        elif "PNG" in selected_filter and ext_lower != ".png":
             file_name = os.path.splitext(file_name)[0] + '.png'

    if file_name != original_file_name:
        print(f"  Adjusted filename with extension: {file_name}")

    try:
        print(f"  Attempting to save to: {file_name}")
        if file_name.lower().endswith((".jpg", ".jpeg")):
            print("  Saving as JPEG (creating white background)...")
            background = Image.new("RGB", image_to_save.size, (255, 255, 255))
            if image_to_save.mode == 'RGBA':
                img_copy = image_to_save.copy()
                img_copy.load()
                background.paste(img_copy, mask=img_copy.split()[3])
            else:
                 background.paste(image_to_save.convert("RGB"))
            background.save(file_name, "JPEG", quality=93)
            print("  JPEG saved successfully.")
        else:
            if not file_name.lower().endswith((".jpg", ".jpeg")) and not file_name.lower().endswith(".png"):
                 file_name = os.path.splitext(file_name)[0] + '.png'
                 print(f"  Forcing PNG format, final filename: {file_name}")

            print(f"  Saving as PNG (or other specified format): {file_name}")
            image_to_save.save(file_name)
            print("  PNG (or other) saved successfully.")

    except Exception as e:
        print(f"  ERROR during image save: {e}")
        QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{file_name}\n\n{str(e)}")

    print("--- save_result_processor finished ---")



def draw_file_names_on_image(self, draw, image, split_position_abs, orig_width, orig_height, line_width, line_height, text_color_tuple):
    font_size_percentage = self.font_size_slider.value() / 200.0
    base_font_size_ratio = 0.03
    font_size = max(10, int(orig_height * base_font_size_ratio * font_size_percentage))
    base_margin = max(5, int(font_size * 0.2))
    margin = min(base_margin, int(orig_height * 0.04))

    font_path = _font_path_absolute

    try:
        font = ImageFont.truetype(font_path, size=font_size)
    except IOError:
        print(f"Warning: Failed to load font '{_font_file_name}' from path '{font_path}'. Falling back.")
        try:
            font = ImageFont.truetype("arial.ttf", size=font_size)
        except IOError:
            print("Warning: Failed to load arial.ttf. Falling back to PIL default.")
            font = ImageFont.load_default()

    file_name1_raw = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else "Image 1")
    file_name2_raw = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else "Image 2")
    max_length = self.max_name_length

    def get_text_size(text, font_to_use):
        if not text: return 0, 0
        try:
            if hasattr(draw, 'textbbox'):
                bbox = draw.textbbox((0, 0), text, font=font_to_use, anchor="lt")
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            elif hasattr(draw, 'textlength'):
                if hasattr(font_to_use, 'getmetrics'):
                    ascent, descent = font_to_use.getmetrics(); height = ascent + descent
                elif hasattr(font_to_use, 'getsize'): _, height = font_to_use.getsize(text)
                else: height = font_size
                return draw.textlength(text, font=font_to_use), height
            else:
                return len(text) * font_size * 0.6, font_size
        except Exception:
            return len(text) * font_size * 0.6, font_size

    available_width1 = max(10, (split_position_abs - (line_width // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name1 = file_name1_raw
    name1_w, _ = get_text_size(temp_name1, font)
    while name1_w > available_width1 and len(temp_name1) > 3:
        temp_name1 = temp_name1[:-4] + "..."
        name1_w, _ = get_text_size(temp_name1, font)
    if len(temp_name1) > max_length:
        temp_name1 = temp_name1[:max_length - 3] + "..."
    file_name1 = temp_name1
    if not file_name1 or file_name1 == "...":
        file_name1 = ""

    available_width2 = max(10, (orig_width - (split_position_abs + (line_width + 1) // 2) - margin * 2) if not self.is_horizontal else (orig_width - margin * 2))
    temp_name2 = file_name2_raw
    name2_w, _ = get_text_size(temp_name2, font)
    while name2_w > available_width2 and len(temp_name2) > 3:
        temp_name2 = temp_name2[:-4] + "..."
        name2_w, _ = get_text_size(temp_name2, font)
    if len(temp_name2) > max_length:
        temp_name2 = temp_name2[:max_length - 3] + "..."
    file_name2 = temp_name2
    if not file_name2 or file_name2 == "...":
        file_name2 = ""

    text_color = text_color_tuple
    if not self.is_horizontal:
        draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size)
    else:
        draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size)


def draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_width, margin, orig_width, orig_height, text_color, get_text_size_func):
    y_baseline = max(margin, orig_height - margin)

    if file_name1:
        text_width1, _ = get_text_size_func(file_name1, font)
        x1_right_edge = max(margin + text_width1, split_position_abs - (line_width // 2) - margin)
        try:
            draw.text((x1_right_edge, y_baseline), file_name1, fill=text_color, font=font, anchor="rs")
        except Exception as e: pass

    if file_name2:
        text_width2, _ = get_text_size_func(file_name2, font)
        x2_left_edge = max(margin, split_position_abs + (line_width + 1) // 2 + margin)
        x2_left_edge = min(x2_left_edge, orig_width - margin - text_width2)
        x2_left_edge = max(margin, x2_left_edge)
        try:
            draw.text((x2_left_edge, y_baseline), file_name2, fill=text_color, font=font, anchor="ls")
        except Exception as e: pass


def draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_position_abs, line_height, margin, orig_width, orig_height, text_color, get_text_size_func):
    line_top = split_position_abs - (line_height // 2)
    line_bottom = split_position_abs + (line_height + 1) // 2
    text_height1 = text_height2 = 0

    if file_name1:
        text_width1, text_height1 = get_text_size_func(file_name1, font)
        x1 = margin
        y1_baseline = max(margin, line_top - margin)
        try:
            draw.text((x1, y1_baseline), file_name1, fill=text_color, font=font, anchor="ls")
        except Exception as e: pass

    if file_name2:
        text_width2, text_height2 = get_text_size_func(file_name2, font)
        x2 = margin
        y2_top = max(margin, line_bottom + margin)
        y2_top = min(y2_top, orig_height - margin - text_height2)

        if file_name1 and text_height1 > 0:
            y1_top_approx = y1_baseline - text_height1
            if y2_top < y1_baseline + (margin // 2):
                y2_top = y1_baseline + (margin // 2)

        y2_top = max(margin, y2_top)
        y2_top = min(y2_top, orig_height - margin - text_height2)

        try:
            draw.text((x2, y2_top), file_name2, fill=text_color, font=font, anchor="lt")
        except Exception as e: pass
        try:
            draw.text((x2, y2_top), file_name2, fill=text_color, font=font, anchor="lt")
        except Exception as e: pass
