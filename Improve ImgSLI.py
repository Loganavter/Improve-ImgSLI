import sys
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QLabel, QCheckBox, QSlider, QSizePolicy
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QBrush, QImage, QRegion, QPainterPath, QKeyEvent
from PyQt6.QtCore import Qt, QRect, QPoint, QPointF, QTimer, QSize
from PIL import Image, ImageDraw
import numpy as np
from math import sqrt

class ImageComparisonApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.image1 = None
        self.image2 = None
        self.result_image = None
        self.is_horizontal = False
        self.use_magnifier = False
        self.split_position = 0.5
        self.magnifier_position = QPoint(300, 300)
        self.magnifier_size = 100
        self.magnifier_zoom = 2
        self.capture_size = 50
        self.capture_position = QPoint(300, 300)
        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(self.update_magnifier_position)
        self.active_keys = set()
        self.movement_speed = 2
        self.magnifier_spacing = 50

    def initUI(self):
        self.setWindowTitle('Image Comparison App')
        self.setGeometry(100, 100, 800, 900)

        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.btn_image1 = QPushButton('Select Image 1')
        self.btn_image2 = QPushButton('Select Image 2')
        self.btn_image1.clicked.connect(lambda: self.load_image(1))
        self.btn_image2.clicked.connect(lambda: self.load_image(2))
        btn_layout.addWidget(self.btn_image1)
        btn_layout.addWidget(self.btn_image2)
        layout.addLayout(btn_layout)

        checkbox_layout = QHBoxLayout()
        self.checkbox_horizontal = QCheckBox('Horizontal Split')
        self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        self.checkbox_magnifier = QCheckBox('Use Magnifier')
        self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)
        checkbox_layout.addWidget(self.checkbox_horizontal)
        checkbox_layout.addWidget(self.checkbox_magnifier)
        layout.addLayout(checkbox_layout)

        slider_layout = QHBoxLayout()
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(50, 200)
        self.slider_size.setValue(100)
        self.slider_size.valueChanged.connect(self.update_magnifier_size)
        self.slider_capture = QSlider(Qt.Orientation.Horizontal)
        self.slider_capture.setRange(1, 100)
        self.slider_capture.setValue(50)
        self.slider_capture.valueChanged.connect(self.update_capture_size)
        slider_layout.addWidget(QLabel("Magnifier Size:"))
        slider_layout.addWidget(self.slider_size)
        slider_layout.addWidget(QLabel("Capture Size:"))
        slider_layout.addWidget(self.slider_capture)
        layout.addLayout(slider_layout)

        self.image_label = ClickableLabel(self)
        self.image_label.setMinimumSize(300, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.mouseMoveEvent = self.on_mouse_move
        layout.addWidget(self.image_label)

        self.btn_save = QPushButton('Save Result')
        self.btn_save.clicked.connect(self.save_result)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)

        self.update_minimum_window_size()

    def resizeEvent(self, event):
        self.update_comparison()
        self.update_minimum_window_size()
        super().resizeEvent(event)

    def update_minimum_window_size(self):
        min_label_size = self.image_label.minimumSize()
        min_width = 300
        min_height = min_label_size.height() + self.layout().contentsMargins().top() + self.layout().contentsMargins().bottom()

        for i in range(self.layout().count() - 1):
            item = self.layout().itemAt(i).widget()
            if item:
                min_height += item.sizeHint().height()

        self.setMinimumSize(min_width, min_height)

    def load_image(self, image_number):
        file_name, _ = QFileDialog.getOpenFileName(self, f"Select Image {image_number}", "", "Image Files (*.png *.jpg *.bmp)")
        if file_name:
            image = Image.open(file_name)
            if image_number == 1:
                self.image1 = image
            else:
                self.image2 = image
            
            if self.image1 and self.image2:
                self.resize_images()
                self.update_comparison()

    def resize_images(self):
        max_width = max(self.image1.width, self.image2.width)
        max_height = max(self.image1.height, self.image2.height)

        self.image1 = self.image1.resize((max_width, max_height), Image.LANCZOS)
        self.image2 = self.image2.resize((max_width, max_height), Image.LANCZOS)

    def update_comparison(self):
        if self.image1 and self.image2:
            width, height = self.image1.size
            result = Image.new('RGB', (width, height))
            split_position = int(width * self.split_position) if not self.is_horizontal else int(height * self.split_position)

            if not self.is_horizontal:
                result.paste(self.image1.crop((0, 0, split_position, height)), (0, 0))
                result.paste(self.image2.crop((split_position, 0, width, height)), (split_position, 0))
            else:
                result.paste(self.image1.crop((0, 0, width, split_position)), (0, 0))
                result.paste(self.image2.crop((0, split_position, width, height)), (0, split_position))

            self.result_image = result
            self.display_result()

    def display_result(self):
        if self.result_image:
            qimage = self.result_image.toqimage()
            pixmap = QPixmap.fromImage(qimage)
            scaled_pixmap = pixmap.scaled(self.image_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            painter = QPainter(scaled_pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            if not self.is_horizontal:
                line_x = int(scaled_pixmap.width() * self.split_position)
                line_width = max(1, int(scaled_pixmap.width() * 0.005))
                painter.fillRect(line_x - line_width // 2, 0, line_width, scaled_pixmap.height(), QColor(0, 0, 0, 128))
            else:
                line_y = int(scaled_pixmap.height() * self.split_position)
                line_height = max(1, int(scaled_pixmap.height() * 0.005))
                painter.fillRect(0, line_y - line_height // 2, scaled_pixmap.width(), line_height, QColor(0, 0, 0, 128))
            
            if self.use_magnifier:
                self.draw_magnifier(painter, scaled_pixmap)
            
            painter.end()

            self.image_label.setPixmap(scaled_pixmap)

    def draw_magnifier(self, painter, pixmap):
        capture_rect = QRect(
            self.capture_position.x() - self.capture_size // 2,
            self.capture_position.y() - self.capture_size // 2,
            self.capture_size,
            self.capture_size
        )

        self.draw_capture_area(painter, capture_rect)

        adjusted_magnifier_position = QPoint(self.magnifier_position.x(), self.magnifier_position.y() - 100)

        left_center = QPoint(adjusted_magnifier_position.x() - self.magnifier_size // 2 - self.magnifier_spacing, 
                            adjusted_magnifier_position.y() + 25)
        right_center = QPoint(adjusted_magnifier_position.x() + self.magnifier_size // 2 + self.magnifier_spacing, 
                             adjusted_magnifier_position.y() + 25)

        distance_between_magnifiers = right_center.x() - left_center.x()
        min_distance = self.magnifier_size  # 60px for the minimum distance

        if distance_between_magnifiers <= min_distance:
            # Center the magnifiers and draw the combined magnifier
            center_x = (left_center.x() + right_center.x()) // 2
            combined_center = QPoint(center_x, left_center.y())

            self.draw_combined_magnifier_circle(painter, pixmap, capture_rect, combined_center, self.image1, self.image2)
        else:
            self.draw_magnifier_circle(painter, pixmap, capture_rect, left_center, self.image1)
            self.draw_magnifier_circle(painter, pixmap, capture_rect, right_center, self.image2)

    def draw_combined_magnifier_circle(self, painter, pixmap, capture_rect, center, image1, image2):
        painter.save()

        center_f = QPointF(center)
        path = QPainterPath()
        path.addEllipse(center_f, self.magnifier_size // 2, self.magnifier_size // 2)
        painter.setClipPath(path)

        display_rect = self.image_label.rect()
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

        scaled_capture1 = captured_area1.resize((self.magnifier_size, self.magnifier_size), Image.LANCZOS)
        scaled_capture2 = captured_area2.resize((self.magnifier_size, self.magnifier_size), Image.LANCZOS)

        half_width = self.magnifier_size // 2
        line_width = max(1, int(self.magnifier_size * 0.025))  # Уменьшение ширины в два раза

        # Draw left half
        left_pixmap = QPixmap.fromImage(scaled_capture1.toqimage())
        left_pixmap = left_pixmap.copy(0, 0, half_width, self.magnifier_size)
        painter.drawPixmap(
            center.x() - self.magnifier_size // 2,
            center.y() - self.magnifier_size // 2,
            left_pixmap
        )

        # Draw right half
        right_pixmap = QPixmap.fromImage(scaled_capture2.toqimage())
        right_pixmap = right_pixmap.copy(half_width, 0, half_width, self.magnifier_size)
        painter.drawPixmap(
            center.x(),
            center.y() - self.magnifier_size // 2,
            right_pixmap
        )

        # Draw the split line
        painter.fillRect(center.x() - line_width // 2, center.y() - self.magnifier_size // 2,
                         line_width, self.magnifier_size, QColor(255, 255, 255))  # Полностью белая линия

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(center_f, self.magnifier_size // 2, self.magnifier_size // 2)

        painter.restore()

    def draw_magnifier_circle(self, painter, pixmap, capture_rect, center, source_image):
        painter.save()
        
        center_f = QPointF(center)

        path = QPainterPath()
        path.addEllipse(center_f, self.magnifier_size // 2, self.magnifier_size // 2)
        painter.setClipPath(path)

        display_rect = self.image_label.rect()
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
        
        scaled_capture = captured_area.resize((self.magnifier_size, self.magnifier_size), Image.LANCZOS)
        scaled_pixmap = QPixmap.fromImage(scaled_capture.toqimage())

        painter.drawPixmap(
            center.x() - self.magnifier_size // 2,
            center.y() - self.magnifier_size // 2,
            scaled_pixmap
        )

        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(center_f, self.magnifier_size // 2, self.magnifier_size // 2)

        painter.restore()

    def draw_capture_area(self, painter, capture_rect):
        painter.save()
        pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        capture_center = QPointF(capture_rect.center().x(), capture_rect.center().y() - 75) 
        painter.drawEllipse(capture_center, self.capture_size // 2, self.capture_size // 2)
        painter.restore()

    def toggle_orientation(self, state):
        self.is_horizontal = state == Qt.CheckState.Checked.value
        self.update_comparison()

    def toggle_magnifier(self, state):
        self.use_magnifier = state == Qt.CheckState.Checked.value
        self.update_comparison()

    def update_magnifier_size(self, value):
        self.magnifier_size = value
        self.update_comparison()

    def update_capture_size(self, value):
        self.capture_size = value
        self.update_comparison()

    def save_result(self):
        if not self.image1 or not self.image2 or not self.result_image:
            return

        file_name, selected_filter = QFileDialog.getSaveFileName(
            self,
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
        orig_width, orig_height = self.image1.size
        result = Image.new('RGB', (orig_width, orig_height))
        
        # Calculate split position in original resolution
        split_pos = int(orig_width * self.split_position) if not self.is_horizontal else int(orig_height * self.split_position)

        # Draw main split view
        if not self.is_horizontal:
            result.paste(self.image1.crop((0, 0, split_pos, orig_height)), (0, 0))
            result.paste(self.image2.crop((split_pos, 0, orig_width, orig_height)), (split_pos, 0))
            
            draw = ImageDraw.Draw(result)
            line_width = max(1, int(orig_width * 0.005))
            draw.rectangle([split_pos - line_width // 2, 0, 
                           split_pos + line_width // 2, orig_height], 
                           fill=(0, 0, 0, 128))
        else:
            result.paste(self.image1.crop((0, 0, orig_width, split_pos)), (0, 0))
            result.paste(self.image2.crop((0, split_pos, orig_width, orig_height)), (0, split_pos))
            
            draw = ImageDraw.Draw(result)
            line_height = max(1, int(orig_height * 0.005))
            draw.rectangle([0, split_pos - line_height // 2,
                           orig_width, split_pos + line_height // 2],
                           fill=(0, 0, 0, 128))

        if self.use_magnifier:
            # Get scale factors
            display_pixmap = self.image_label.pixmap()
            scale_x = orig_width / display_pixmap.width()
            scale_y = orig_height / display_pixmap.height()

            # Calculate capture position in original resolution
            display_rect = self.image_label.rect()
            x_offset = (display_rect.width() - display_pixmap.width()) // 2
            y_offset = (display_rect.height() - display_pixmap.height()) // 2
            
            capture_x = int((self.capture_position.x() - x_offset) * scale_x)
            capture_y = int((self.capture_position.y() - y_offset) * scale_y)

            # Draw capture area
            orig_capture_size = int(self.capture_size * scale_x)
            draw = ImageDraw.Draw(result)
            draw.ellipse([
                capture_x - orig_capture_size // 2,
                capture_y - orig_capture_size // 2,
                capture_x + orig_capture_size // 2,
                capture_y + orig_capture_size // 2
            ], outline='red', width=max(1, int(2 * scale_x)))

            # Calculate magnifier dimensions and positions
            orig_magnifier_size = int(self.magnifier_size * scale_x)
            magnifier_y = int((self.magnifier_position.y() - 75) * scale_y)
            
            left_center = QPoint(
                self.magnifier_position.x() - self.magnifier_size // 2 - self.magnifier_spacing,
                self.magnifier_position.y() + 25
            )
            right_center = QPoint(
                self.magnifier_position.x() + self.magnifier_size // 2 + self.magnifier_spacing,
                self.magnifier_position.y() + 25
            )

            # Check if magnifiers should be merged
            distance_between_magnifiers = right_center.x() - left_center.x()
            min_distance = self.magnifier_size

            if distance_between_magnifiers <= min_distance:
                # Draw merged magnifier
                center_x = int(((left_center.x() + right_center.x()) // 2 - x_offset) * scale_x)
                
                # Create mask for merged magnifier
                mask = Image.new('L', (orig_magnifier_size, orig_magnifier_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse([0, 0, orig_magnifier_size, orig_magnifier_size], fill=255)

                # Draw left half
                left_capture = self.image1.crop((
                    max(0, capture_x - orig_capture_size // 2),
                    max(0, capture_y - orig_capture_size // 2),
                    min(orig_width, capture_x + orig_capture_size // 2),
                    min(orig_height, capture_y + orig_capture_size // 2)
                ))
                left_magnified = left_capture.resize((orig_magnifier_size, orig_magnifier_size), Image.LANCZOS)
                left_half = left_magnified.crop((0, 0, orig_magnifier_size // 2, orig_magnifier_size))
                
                # Draw right half
                right_capture = self.image2.crop((
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
                    (left_center, self.image1),
                    (right_center, self.image2)
                ]):
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
            QMessageBox.critical(self, "Error", f"Failed to save image: {str(e)}")

    def on_mouse_move(self, event):
        if self.image_label.pixmap():
            if not event.buttons() & Qt.MouseButton.LeftButton:
                return

            pos = event.position()
            cursor_pos = QPoint(int(pos.x()), int(pos.y()))
            
            if not self.is_within_interaction_area(cursor_pos):
                return
                
            pixmap = self.image_label.pixmap()
            
            label_rect = self.image_label.rect()
            x_offset = (label_rect.width() - pixmap.width()) // 2
            y_offset = (label_rect.height() - pixmap.height()) // 2
            
            adjusted_x = pos.x() - x_offset
            adjusted_y = pos.y() - y_offset
            
            if not self.use_magnifier:
                if not self.is_horizontal:
                    self.split_position = adjusted_x / pixmap.width()
                else:
                    self.split_position = adjusted_y / pixmap.height()
                self.split_position = max(0, min(1, self.split_position))
            
            if self.use_magnifier:
                dx = self.magnifier_position.x() - self.capture_position.x()
                dy = self.magnifier_position.y() - self.capture_position.y()
                
                self.capture_position = cursor_pos
                
                self.magnifier_position = QPoint(cursor_pos.x() + dx, cursor_pos.y() + dy)
            
            self.update_comparison()

    def is_within_interaction_area(self, pos):
        if not self.image_label.pixmap():
            return False
            
        pixmap = self.image_label.pixmap()
        label_rect = self.image_label.rect()
        
        x_offset = (label_rect.width() - pixmap.width()) // 2
        y_offset = (label_rect.height() - pixmap.height()) // 2
        
        interaction_area = QRect(
            x_offset,
            y_offset,
            pixmap.width(),
            pixmap.height()
        )
        
        return interaction_area.contains(pos)

    def keyPressEvent(self, event):
        if self.use_magnifier:
            key = event.key()
            self.active_keys.add(key)
            self.movement_timer.start(30)

    def keyReleaseEvent(self, event):
        key = event.key()
        if key in self.active_keys:
            self.active_keys.remove(key)
        if not self.active_keys:
            self.movement_timer.stop()


    def update_magnifier_position(self):
        if not self.use_magnifier:
            return

        dx = 0
        dy = 0
        
        if Qt.Key.Key_A in self.active_keys:
            dx -= 1
        if Qt.Key.Key_D in self.active_keys:
            dx += 1
        if Qt.Key.Key_W in self.active_keys:
            dy -= 1
        if Qt.Key.Key_S in self.active_keys:
            dy += 1
        if Qt.Key.Key_Q in self.active_keys:
            self.magnifier_spacing = max(0, self.magnifier_spacing - 2)
        if Qt.Key.Key_E in self.active_keys:
            self.magnifier_spacing += 2
            
        if dx != 0 or dy != 0:
            if dx != 0 and dy != 0:
                length = sqrt(dx * dx + dy * dy)
                dx = dx / length
                dy = dy / length
                
            new_x = self.magnifier_position.x() + int(dx * self.movement_speed)
            new_y = self.magnifier_position.y() + int(dy * self.movement_speed)
            
            self.magnifier_position = QPoint(new_x, new_y)
            
        self.update_comparison()

class ClickableLabel(QLabel):
    def mousePressEvent(self, event):
        self.parent().on_mouse_move(event)

    def mouseMoveEvent(self, event):
        self.parent().on_mouse_move(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = ImageComparisonApp()
    ex.show()
    sys.exit(app.exec())
