from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF
from translations import tr
import numpy as np
import os
import math


def resize_images_processor(app):
    """Resizes image1 and image2 to the maximum dimensions of both."""
    if not app.image1 or not app.image2:
        return
    max_width = max(app.image1.width, app.image2.width)
    max_height = max(app.image1.height, app.image2.height)
    app.image1 = app.image1.resize((max_width, max_height), Image.LANCZOS)
    app.image2 = app.image2.resize((max_width, max_height), Image.LANCZOS)


def update_comparison_processor(app):
    """Updates the comparison result image based on split position and orientation."""
    if not app.image1 or not app.image2:
        return
    width, height = app.image1.size
    result = Image.new('RGB', (width, height))
    split_position = int(width * app.split_position) if not app.is_horizontal else int(height * app.split_position)
    if not app.is_horizontal:
        result.paste(app.image1.crop((0, 0, split_position, height)), (0, 0))
        result.paste(app.image2.crop((split_position, 0, width, height)), (split_position, 0))
    else:
        result.paste(app.image1.crop((0, 0, width, split_position)), (0, 0))
        result.paste(app.image2.crop((0, split_position, width, height)), (0, split_position))
    app.result_image = result
    display_result_processor(app)


def display_result_processor(app):
    """Displays the result image on the image label, including split line and magnifier."""
    if not app.result_image:
        return
    qimage = app.result_image.toqimage()
    pixmap = QPixmap.fromImage(qimage)
    scaled_pixmap = pixmap.scaled(app.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    display_pixmap = QPixmap(scaled_pixmap)
    painter = QPainter(display_pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    draw_split_line(app, painter, scaled_pixmap)
    if app.use_magnifier and hasattr(app, 'capture_position') and hasattr(app, 'magnifier_position'):
        initialize_magnifier_positions(app, scaled_pixmap)
        draw_magnifier_processor(app, painter, display_pixmap)
    painter.end()
    app.image_label.setPixmap(display_pixmap)


def draw_split_line(app, painter, scaled_pixmap):
    """Draws the split line on the displayed image."""
    if not app.is_horizontal:
        line_x = int(scaled_pixmap.width() * app.split_position)
        line_width = max(1, int(scaled_pixmap.width() * 0.0025)) # Reduced line width to match original
        painter.fillRect(line_x - line_width // 2, 0, line_width, scaled_pixmap.height(), QColor(0, 0, 0, 128))
    else:
        line_y = int(scaled_pixmap.height() * app.split_position)
        line_height = max(1, int(scaled_pixmap.height() * 0.0025)) # Reduced line height to match original
        painter.fillRect(0, line_y - line_height // 2, scaled_pixmap.width(), line_height, QColor(0, 0, 0, 128))


def initialize_magnifier_positions(app, scaled_pixmap):
    """Initializes magnifier and capture positions if they are not set."""
    if app.capture_position is None:
        center_x = scaled_pixmap.width() // 2
        center_y = scaled_pixmap.height() // 2
        app.capture_position = QPoint(center_x, center_y)
    if app.magnifier_position is None:
        center_x = scaled_pixmap.width() // 2
        center_y = scaled_pixmap.height() // 2
        app.magnifier_position = QPoint(center_x, center_y)


def draw_magnifier_processor(app, painter, pixmap):
    """Draws the magnifier on the displayed image, handling combined or separate magnifiers."""
    if not hasattr(app, 'capture_size'): app.capture_size = 30
    if not hasattr(app, 'magnifier_size'): app.magnifier_size = 120
    if not hasattr(app, 'magnifier_spacing'): app.magnifier_spacing = 10

    capture_rect = QRect(app.capture_position.x() - app.capture_size // 2, app.capture_position.y() - app.capture_size // 2, app.capture_size, app.capture_size)
    draw_capture_area_processor(app, painter, capture_rect)

    adjusted_magnifier_position = QPoint(app.magnifier_position.x(), app.magnifier_position.y() - 100)  # Fixed position
    left_center = QPoint(adjusted_magnifier_position.x() - app.magnifier_size // 2 - app.magnifier_spacing, adjusted_magnifier_position.y() + 25) # Fixed position
    right_center = QPoint(adjusted_magnifier_position.x() + app.magnifier_size // 2 + app.magnifier_spacing, adjusted_magnifier_position.y() + 25) # Fixed position

    distance_between_magnifiers = right_center.x() - left_center.x()
    min_distance = app.magnifier_size

    if distance_between_magnifiers <= min_distance:
        center_x = (left_center.x() + right_center.x()) // 2
        combined_center = QPoint(center_x, left_center.y())
        draw_combined_magnifier_circle_processor(app, painter, pixmap, capture_rect, combined_center, app.image1, app.image2)
    else:
        draw_magnifier_circle_processor(app, painter, pixmap, capture_rect, left_center, app.image1)
        draw_magnifier_circle_processor(app, painter, pixmap, capture_rect, right_center, app.image2)


def draw_combined_magnifier_circle_processor(app, painter, pixmap, capture_rect, center, image1, image2):
    """Draws a combined magnifier circle showing portions of both images."""
    painter.save()
    center_f = QPointF(center)
    path = QPainterPath()
    path.addEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)
    painter.setClipPath(path)

    display_rect = app.image_label.rect()
    scaled_width = pixmap.width()
    scaled_height = pixmap.height()
    x_offset = (display_rect.width() - scaled_width) // 2
    y_offset = (display_rect.height() - scaled_height) // 2

    adjusted_capture_x = capture_rect.x() - x_offset
    adjusted_capture_y = capture_rect.y() - y_offset
    adjusted_capture_x = max(0, min(adjusted_capture_x, scaled_width))
    adjusted_capture_y = max(0, min(adjusted_capture_y, scaled_height))

    scale_x1 = image1.width / scaled_width
    scale_y1 = image1.height / scaled_height
    scale_x2 = image2.width / scaled_width
    scale_y2 = image2.height / scaled_height

    orig_x1 = int(adjusted_capture_x * scale_x1)
    orig_y1 = int(adjusted_capture_y * scale_y1)
    orig_size1 = int(capture_rect.width() * scale_x1)
    orig_x1 = max(0, min(orig_x1, image1.width - orig_size1))
    orig_y1 = max(0, min(orig_y1, image1.height - orig_size1))

    orig_x2 = int(adjusted_capture_x * scale_x2)
    orig_y2 = int(adjusted_capture_y * scale_y2)
    orig_size2 = int(capture_rect.width() * scale_x2)
    orig_x2 = max(0, min(orig_x2, image2.width - orig_size2))
    orig_y2 = max(0, min(orig_y2, image2.height - orig_size2))

    captured_area1 = image1.crop((orig_x1, orig_y1, min(orig_x1 + orig_size1, image1.width), min(orig_y1 + orig_size1, image1.height)))
    captured_area2 = image2.crop((orig_x2, orig_y2, min(orig_x2 + orig_size2, image2.width), min(orig_y2 + orig_size2, image2.height)))

    scaled_capture1 = captured_area1.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)
    scaled_capture2 = captured_area2.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)

    half_width = app.magnifier_size // 2
    line_width = max(1, int(app.magnifier_size * 0.025)) # Reduced line width to match original

    left_pixmap = QPixmap.fromImage(scaled_capture1.toqimage())
    left_pixmap = left_pixmap.copy(0, 0, half_width, app.magnifier_size)
    painter.drawPixmap(center.x() - app.magnifier_size // 2, center.y() - app.magnifier_size // 2, left_pixmap)

    right_pixmap = QPixmap.fromImage(scaled_capture2.toqimage())
    right_pixmap = right_pixmap.copy(half_width, 0, half_width, app.magnifier_size)
    painter.drawPixmap(center.x(), center.y() - app.magnifier_size // 2, right_pixmap)

    painter.fillRect(center.x() - line_width // 2, center.y() - app.magnifier_size // 2, line_width, app.magnifier_size, QColor(255, 255, 255))
    painter.setPen(QPen(Qt.GlobalColor.white, 2))
    painter.drawEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)
    painter.restore()


def draw_magnifier_circle_processor(app, painter, pixmap, capture_rect, center, source_image):
    """Draws a single magnifier circle showing a magnified portion of the source image."""
    painter.save()
    center_f = QPointF(center)
    path = QPainterPath()
    path.addEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)
    painter.setClipPath(path)

    display_rect = app.image_label.rect()
    scaled_width = pixmap.width()
    scaled_height = pixmap.height()
    x_offset = (display_rect.width() - scaled_width) // 2
    y_offset = (display_rect.height() - scaled_height) // 2

    adjusted_capture_x = capture_rect.x() - x_offset
    adjusted_capture_y = capture_rect.y() - y_offset
    adjusted_capture_x = max(0, min(adjusted_capture_x, scaled_width))
    adjusted_capture_y = max(0, min(adjusted_capture_y, scaled_height))

    scale_x = source_image.width / scaled_width
    scale_y = source_image.height / scaled_height

    orig_x = int(adjusted_capture_x * scale_x)
    orig_y = int(adjusted_capture_y * scale_y)
    orig_size = int(capture_rect.width() * scale_x)
    orig_x = max(0, min(orig_x, source_image.width - orig_size))
    orig_y = max(0, min(orig_y, source_image.height - orig_size))

    captured_area = source_image.crop((orig_x, orig_y, min(orig_x + orig_size, source_image.width), min(orig_y + orig_size, source_image.height)))
    scaled_capture = captured_area.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)
    scaled_pixmap = QPixmap.fromImage(scaled_capture.toqimage())
    painter.drawPixmap(center.x() - app.magnifier_size // 2, center.y() - app.magnifier_size // 2, scaled_pixmap)

    painter.setPen(QPen(Qt.GlobalColor.white, 2))
    painter.drawEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)
    painter.restore()


def draw_capture_area_processor(app, painter, capture_rect):
    """Draws a red circle to indicate the capture area for the magnifier."""
    painter.save()
    pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.SolidLine)
    painter.setPen(pen)

    display_rect = app.image_label.rect()
    pixmap = app.image_label.pixmap()
    if pixmap:
        scaled_width = pixmap.width()
        scaled_height = pixmap.height()
        x_offset = (display_rect.width() - scaled_width) // 2
        y_offset = (display_rect.height() - scaled_height) // 2

        adjusted_capture_x = capture_rect.center().x() - x_offset
        adjusted_capture_y = capture_rect.center().y() - y_offset
        adjusted_capture_x = max(0, min(adjusted_capture_x, scaled_width))
        adjusted_capture_y = max(0, min(adjusted_capture_y, scaled_height))
        capture_center = QPointF(adjusted_capture_x, adjusted_capture_y)
        painter.drawEllipse(capture_center, app.capture_size // 2, app.capture_size // 2)
    painter.restore()


def save_result_processor(self):
    """Saves the comparison result image to a file, including file names if enabled."""
    if not self.image1 or not self.image2 or not self.result_image:
        return

    file_name, selected_filter = QFileDialog.getSaveFileName(self, tr("Save Image", self.current_language), "", "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)")
    if not file_name:
        return
    if not file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
        if "PNG" in selected_filter:
            file_name += '.png'
        elif "JPEG" in selected_filter:
            file_name += '.jpg'
        else:
            file_name += '.png'

    orig_width, orig_height = self.image1.size
    result = Image.new('RGB', (orig_width, orig_height))
    split_pos = int(orig_width * self.split_position) if not self.is_horizontal else int(orig_height * self.split_position)

    line_width = max(1, int(orig_width * 0.0025))
    line_height = max(1, int(orig_height * 0.0025))

    if not self.is_horizontal:
        result.paste(self.image1.crop((0, 0, split_pos, orig_height)), (0, 0))
        result.paste(self.image2.crop((split_pos, 0, orig_width, orig_height)), (split_pos, 0))
        draw = ImageDraw.Draw(result)
        draw.rectangle([split_pos - line_width // 2, 0, split_pos + line_width // 2, orig_height], fill=(0, 0, 0, 128))
    else:
        result.paste(self.image1.crop((0, 0, orig_width, split_pos)), (0, 0))
        result.paste(self.image2.crop((0, split_pos, orig_width, orig_height)), (0, split_pos))
        draw = ImageDraw.Draw(result)
        draw.rectangle([0, split_pos - line_height // 2, orig_width, split_pos + line_height // 2], fill=(0, 0, 0, 128))

    # Добавляем отладочный вывод для проверки состояния чекбокса
    print(f"Include file names: {self.checkbox_file_names.isChecked()}")
    if self.checkbox_file_names.isChecked():
        print("Drawing file names...")
        draw_file_names_on_image(self, result, split_pos, orig_width, orig_height, line_width, line_height)

    try:
        if file_name.lower().endswith(".jpg") or file_name.lower().endswith(".jpeg"):
            result.save(file_name, "JPEG", quality=93)
        else:
            result.save(file_name)
        print(f"Image saved to {file_name}")
    except Exception as e:
        QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)} {str(e)}")


def draw_file_names_on_image(self, result, split_pos, orig_width, orig_height, line_width, line_height):
    """Draws file names on the saved image."""
    draw = ImageDraw.Draw(result)
    font_size_percent = self.font_size_slider.value() / 100
    font_size = max(1, int(orig_height * font_size_percent / 100))
    base_margin = 5
    additional_margin = int(font_size * 0.1)
    margin = min(base_margin + additional_margin, int(orig_height * 0.03))
    font_path = "./SourceSans3-Regular.ttf"  # Убедитесь, что путь к шрифту корректен

    try:
        font = ImageFont.truetype(font_path, size=font_size)
        print(f"Font loaded: {font_path}, size: {font_size}")
    except IOError:
        print("Font not found, using default font.")
        QMessageBox.warning(self, tr("Warning", self.current_language), "Шрифт Source Sans Pro не найден, используется шрифт по умолчанию.")
        font = ImageFont.load_default()  # Используем шрифт по умолчанию без размера, если метод load_default(size) недоступен

    # Получаем имена файлов
    file_name1_raw = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else "Изображение 1")
    file_name2_raw = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else "Изображение 2")
    max_length = self.max_name_length
    file_name1 = file_name1_raw[:max_length-3] + "..." if len(file_name1_raw) > max_length else file_name1_raw
    file_name2 = file_name2_raw[:max_length-3] + "..." if len(file_name2_raw) > max_length else file_name2_raw

    print(f"File names: {file_name1}, {file_name2}")

    if not self.is_horizontal:
        draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_pos, line_width, margin, orig_width, orig_height)
    else:
        draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_pos, line_height, margin, orig_width, orig_height)


def draw_vertical_filenames(self, draw, font, file_name1, file_name2, split_pos, line_width, margin, orig_width, orig_height):
    """Draws filenames for vertical split."""
    text_margin_x = margin
    text_margin_y_factor = 0.35

    bbox1 = draw.textbbox((0, 0), file_name1, font=font)
    text_width1 = bbox1[2] - bbox1[0]
    text_height1 = bbox1[3] - bbox1[1]
    x1 = split_pos - line_width // 2 - text_width1 - text_margin_x
    x1 = max(margin, min(x1, orig_width - text_width1 - margin))
    text_margin_y1 = max(margin, int(text_height1 * text_margin_y_factor))
    y1 = orig_height - text_height1 - text_margin_y1
    y1 = max(0, min(y1, orig_height - text_height1))
    draw.text((x1, y1), file_name1, fill=(255, 0, 0), font=font)

    bbox2 = draw.textbbox((0, 0), file_name2, font=font)
    text_width2 = bbox2[2] - bbox2[0]
    text_height2 = bbox2[3] - bbox2[1]
    x2 = split_pos + line_width // 2 + text_margin_x
    x2 = max(split_pos + line_width // 2, min(x2, orig_width - text_width2 - margin))
    text_margin_y2 = max(margin, int(text_height2 * text_margin_y_factor))
    y2 = orig_height - text_height2 - text_margin_y2
    y2 = max(0, min(y2, orig_height - text_height2))
    draw.text((x2, y2), file_name2, fill=(255, 0, 0), font=font)


def draw_horizontal_filenames(self, draw, font, file_name1, file_name2, split_pos, line_height, margin, orig_width, orig_height):
    """Draws filenames for horizontal split."""
    line_top = split_pos - line_height // 2
    line_bottom = split_pos + line_height // 2
    top_margin = int(margin * 2) # Increased top margin to match original
    bottom_margin = int(margin * 0.001) # Reduced bottom margin to match original

    bbox1 = draw.textbbox((0, 0), file_name1, font=font)
    text_width1 = bbox1[2] - bbox1[0]
    text_height1 = bbox1[3] - bbox1[1]
    x1 = margin
    y1 = line_top - text_height1 - top_margin
    if y1 < margin:
        y1 = margin
    draw.text((x1, max(0, y1)), file_name1, fill=(255, 0, 0), font=font)

    bbox2 = draw.textbbox((0, 0), file_name2, font=font)
    text_width2 = bbox2[2] - bbox2[0]
    text_height2 = bbox2[3] - bbox2[1]
    x2 = margin
    y2 = line_bottom + bottom_margin
    if y2 + text_height2 > orig_height - margin:
        y2 = orig_height - text_height2 - margin
    draw.text((x2, max(0, y2)), file_name2, fill=(255, 0, 0), font=font)
