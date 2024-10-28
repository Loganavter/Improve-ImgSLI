from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF
import numpy as np

def resize_images(app):
    max_width = max(app.image1.width, app.image2.width)
    max_height = max(app.image1.height, app.image2.height)

    app.image1 = app.image1.resize((max_width, max_height), Image.LANCZOS)
    app.image2 = app.image2.resize((max_width, max_height), Image.LANCZOS)

def update_comparison(app):
    if app.image1 and app.image2:
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
        display_result(app)

def display_result(app):
    if app.result_image:
        qimage = app.result_image.toqimage()
        pixmap = QPixmap.fromImage(qimage)
        scaled_pixmap = pixmap.scaled(app.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        
        painter = QPainter(scaled_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if not app.is_horizontal:
            line_x = int(scaled_pixmap.width() * app.split_position)
            line_width = max(1, int(scaled_pixmap.width() * 0.005))
            painter.fillRect(line_x - line_width // 2, 0, line_width, scaled_pixmap.height(), QColor(0, 0, 0, 128))
        else:
            line_y = int(scaled_pixmap.height() * app.split_position)
            line_height = max(1, int(scaled_pixmap.height() * 0.005))
            painter.fillRect(0, line_y - line_height // 2, scaled_pixmap.width(), line_height, QColor(0, 0, 0, 128))
        
        if app.use_magnifier:
            draw_magnifier(app, painter, scaled_pixmap)
        
        painter.end()

        app.image_label.setPixmap(scaled_pixmap)

def draw_magnifier(app, painter, pixmap):
    capture_rect = QRect(
        app.capture_position.x() - app.capture_size // 2,
        app.capture_position.y() - app.capture_size // 2,
        app.capture_size,
        app.capture_size
    )

    draw_capture_area(app, painter, capture_rect)

    adjusted_magnifier_position = QPoint(app.magnifier_position.x(), app.magnifier_position.y() - 100)

    left_center = QPoint(adjusted_magnifier_position.x() - app.magnifier_size // 2 - app.magnifier_spacing, 
                        adjusted_magnifier_position.y() + 25)
    right_center = QPoint(adjusted_magnifier_position.x() + app.magnifier_size // 2 + app.magnifier_spacing, 
                         adjusted_magnifier_position.y() + 25)

    distance_between_magnifiers = right_center.x() - left_center.x()
    min_distance = app.magnifier_size  # 60px for the minimum distance

    if distance_between_magnifiers <= min_distance:
        # Center the magnifiers and draw the combined magnifier
        center_x = (left_center.x() + right_center.x()) // 2
        combined_center = QPoint(center_x, left_center.y())

        draw_combined_magnifier_circle(app, painter, pixmap, capture_rect, combined_center, app.image1, app.image2)
    else:
        draw_magnifier_circle(app, painter, pixmap, capture_rect, left_center, app.image1)
        draw_magnifier_circle(app, painter, pixmap, capture_rect, right_center, app.image2)

def draw_combined_magnifier_circle(app, painter, pixmap, capture_rect, center, image1, image2):
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

    captured_area1 = image1.crop((
        orig_x1,
        orig_y1,
        min(orig_x1 + orig_size1, image1.width),
        min(orig_y1 + orig_size1, image1.height)
    ))

    captured_area2 = image2.crop((
        orig_x2,
        orig_y2,
        min(orig_x2 + orig_size2, image2.width),
        min(orig_y2 + orig_size2, image2.height)
    ))

    scaled_capture1 = captured_area1.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)
    scaled_capture2 = captured_area2.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)

    half_width = app.magnifier_size // 2
    line_width = max(1, int(app.magnifier_size * 0.025))  # Уменьшение ширины в два раза

    # Draw left half
    left_pixmap = QPixmap.fromImage(scaled_capture1.toqimage())
    left_pixmap = left_pixmap.copy(0, 0, half_width, app.magnifier_size)
    painter.drawPixmap(
        center.x() - app.magnifier_size // 2,
        center.y() - app.magnifier_size // 2,
        left_pixmap
    )

    # Draw right half
    right_pixmap = QPixmap.fromImage(scaled_capture2.toqimage())
    right_pixmap = right_pixmap.copy(half_width, 0, half_width, app.magnifier_size)
    painter.drawPixmap(
        center.x(),
        center.y() - app.magnifier_size // 2,
        right_pixmap
    )

    # Draw the split line
    painter.fillRect(center.x() - line_width // 2, center.y() - app.magnifier_size // 2,
                     line_width, app.magnifier_size, QColor(255, 255, 255))  # Полностью белая линия

    painter.setPen(QPen(Qt.GlobalColor.white, 2))
    painter.drawEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)

    painter.restore()

def draw_magnifier_circle(app, painter, pixmap, capture_rect, center, source_image):
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

    captured_area = source_image.crop((
        orig_x,
        orig_y,
        min(orig_x + orig_size, source_image.width),
        min(orig_y + orig_size, source_image.height)
    ))
    
    scaled_capture = captured_area.resize((app.magnifier_size, app.magnifier_size), Image.LANCZOS)
    scaled_pixmap = QPixmap.fromImage(scaled_capture.toqimage())

    painter.drawPixmap(
        center.x() - app.magnifier_size // 2,
        center.y() - app.magnifier_size // 2,
        scaled_pixmap
    )

    painter.setPen(QPen(Qt.GlobalColor.white, 2))
    painter.drawEllipse(center_f, app.magnifier_size // 2, app.magnifier_size // 2)

    painter.restore()

def draw_capture_area(app, painter, capture_rect):
    painter.save()
    pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.SolidLine)
    painter.setPen(pen)
    capture_center = QPointF(capture_rect.center().x(), capture_rect.center().y() - 100) 
    painter.drawEllipse(capture_center, app.capture_size // 2, app.capture_size // 2)
    painter.restore()

def save_result(app):
    if not app.image1 or not app.image2 or not app.result_image:
        return

    file_name, selected_filter = QFileDialog.getSaveFileName(
        app,
        "Save Image",
        "",
        "PNG Files (*.png);;JPEG Files (*.jpg);;All Files (*)"
    )
    
    if not file_name:
        return

    if not file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
        if "PNG" in selected_filter:
            file_name += '.png'
        elif "JPEG" in selected_filter:
            file_name += '.jpg'
        else:
            file_name += '.png'

    # Get original dimensions
    orig_width, orig_height = app.image1.size
    result = Image.new('RGB', (orig_width, orig_height))
    
    # Calculate split position in original resolution
    split_pos = int(orig_width * app.split_position) if not app.is_horizontal else int(orig_height * app.split_position)

    # Draw main split view
    if not app.is_horizontal:
        result.paste(app.image1.crop((0, 0, split_pos, orig_height)), (0, 0))
        result.paste(app.image2.crop((split_pos, 0, orig_width, orig_height)), (split_pos, 0))
        
        draw = ImageDraw.Draw(result)
        line_width = max(1, int(orig_width * 0.005))
        draw.rectangle([split_pos - line_width // 2, 0, 
                       split_pos + line_width // 2, orig_height], 
                       fill=(0, 0, 0, 128))
    else:
        result.paste(app.image1.crop((0, 0, orig_width, split_pos)), (0, 0))
        result.paste(app.image2.crop((0, split_pos, orig_width, orig_height)), (0, split_pos))
        
        draw = ImageDraw.Draw(result)
        line_height = max(1, int(orig_height * 0.005))
        draw.rectangle([0, split_pos - line_height // 2,
                       orig_width, split_pos + line_height // 2],
                       fill=(0, 0, 0, 128))

    if app.use_magnifier:
        # Get scale factors
        display_pixmap = app.image_label.pixmap()
        scale_x = orig_width / display_pixmap.width()
        scale_y = orig_height / display_pixmap.height()

        # Calculate capture position in original resolution
        display_rect = app.image_label.rect()
        x_offset = (display_rect.width() - display_pixmap.width()) // 2
        y_offset = (display_rect.height() - display_pixmap.height()) // 2
        
        capture_x = int((app.capture_position.x() - x_offset) * scale_x)
        capture_y = int((app.capture_position.y() - y_offset) * scale_y)

        # Draw capture area
        orig_capture_size = int(app.capture_size * scale_x)
        draw = ImageDraw.Draw(result)
        draw.ellipse([
            capture_x - orig_capture_size // 2,
            capture_y - orig_capture_size // 2,
            capture_x + orig_capture_size // 2,
            capture_y + orig_capture_size // 2
        ], outline='red', width=max(1, int(2 * scale_x)))

        # Calculate magnifier dimensions and positions
        orig_magnifier_size = int(app.magnifier_size * scale_x)
        magnifier_y = int((app.magnifier_position.y() - 75) * scale_y)
        
        left_center = QPoint(
            app.magnifier_position.x() - app.magnifier_size // 2 - app.magnifier_spacing,
            app.magnifier_position.y() + 25
        )
        right_center = QPoint(
            app.magnifier_position.x() + app.magnifier_size // 2 + app.magnifier_spacing,
            app.magnifier_position.y() + 25
        )

        # Check if magnifiers should be merged
        distance_between_magnifiers = right_center.x() - left_center.x()
        min_distance = app.magnifier_size

        if distance_between_magnifiers <= min_distance:
            # Draw merged magnifier
            center_x = int(((left_center.x() + right_center.x()) // 2 - x_offset) * scale_x)
            
            # Create mask for merged magnifier
            mask = Image.new('L', (orig_magnifier_size, orig_magnifier_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, orig_magnifier_size, orig_magnifier_size], fill=255)

            # Draw left half
            left_capture = app.image1.crop((
                max(0, capture_x - orig_capture_size // 2),
                max(0, capture_y - orig_capture_size // 2),
                min(orig_width, capture_x + orig_capture_size // 2),
                min(orig_height, capture_y + orig_capture_size // 2)
            ))
            left_magnified = left_capture.resize((orig_magnifier_size, orig_magnifier_size), Image.LANCZOS)
            left_half = left_magnified.crop((0, 0, orig_magnifier_size // 2, orig_magnifier_size))
            
            # Draw right half
            right_capture = app.image2.crop((
                max(0, capture_x - orig_capture_size // 2),
                max(0, capture_y - orig_capture_size // 2),
                min(orig_width, capture_x + orig_capture_size // 2),
                min(orig_height, capture_y + orig_capture_size // 2)
            ))
            right_magnified = right_capture.resize((orig_magnifier_size, orig_magnifier_size), Image.LANCZOS)
            right_half = right_magnified.crop((orig_magnifier_size // 2, 0, orig_magnifier_size, orig_magnifier_size))

            # Combine halves
            merged = Image.new('RGB', (orig_magnifier_size, orig_magnifier_size))
            merged.paste(left_half, (0, 0))
            merged.paste(right_half, (orig_magnifier_size // 2, 0))

            # Draw split line
            merge_draw = ImageDraw.Draw(merged)
            line_width = max(1, int(orig_magnifier_size * 0.025))
            merge_draw.rectangle([
                orig_magnifier_size // 2 - line_width // 2,
                0,
                orig_magnifier_size // 2 + line_width // 2,
                orig_magnifier_size
            ], fill=(255, 255, 255))

            # Paste merged magnifier
            result.paste(
                merged,
                (
                    center_x - orig_magnifier_size // 2,
                    magnifier_y - orig_magnifier_size // 2
                ),
                mask
            )

            # Draw border
            draw.ellipse([
                center_x - orig_magnifier_size // 2,
                magnifier_y - orig_magnifier_size // 2,
                center_x + orig_magnifier_size // 2,
                magnifier_y + orig_magnifier_size // 2
            ], outline='white', width=max(1, int(2 * scale_x)))

        else:
            # Draw separate magnifiers
            for i, (center, source_img) in enumerate([
                (left_center, app.image1),
                (right_center, app.image2)
            ]):
                # Create
                # Create mask for circular magnifier
                mask = Image.new('L', (orig_magnifier_size, orig_magnifier_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse([0, 0, orig_magnifier_size, orig_magnifier_size], fill=255)

                # Get and resize captured area
                capture_area = source_img.crop((
                    max(0, capture_x - orig_capture_size // 2),
                    max(0, capture_y - orig_capture_size // 2),
                    min(orig_width, capture_x + orig_capture_size // 2),
                    min(orig_height, capture_y + orig_capture_size // 2)
                ))
                magnified = capture_area.resize((orig_magnifier_size, orig_magnifier_size), Image.LANCZOS)

                # Calculate magnifier position
                mag_center_x = int((center.x() - x_offset) * scale_x)

                # Paste magnified area
                result.paste(
                    magnified,
                    (
                        mag_center_x - orig_magnifier_size // 2,
                        magnifier_y - orig_magnifier_size // 2
                    ),
                    mask
                )

                # Draw border
                draw.ellipse([
                    mag_center_x - orig_magnifier_size // 2,
                    magnifier_y - orig_magnifier_size // 2,
                    mag_center_x + orig_magnifier_size // 2,
                    magnifier_y + orig_magnifier_size // 2
                ], outline='white', width=max(1, int(2 * scale_x)))

    try:
        result.save(file_name)
    except Exception as e:
        QMessageBox.critical(app, "Error", f"Failed to save image: {str(e)}")
