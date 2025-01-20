from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel, QFileDialog, QSizePolicy, QMessageBox
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QDragEnterEvent, QDropEvent
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QMimeData, QSize
from PIL import Image, ImageDraw
from clickable_label import ClickableLabel
from image_processing import resize_images, update_comparison, draw_magnifier, draw_capture_area, save_result
import numpy as np
from math import sqrt, cos, sin, pi

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
        self.movement_timer.setInterval(16)  # ~60 FPS for smooth movement
        self.active_keys = set()
        self.movement_speed = 2  # Базовая скорость движения
        self.magnifier_spacing = 50
        self.freeze_magnifier = False

        # Create drag overlays for Image 1 and Image 2
        self.drag_overlay1 = QLabel(self)
        self.drag_overlay1.setText("Drop Image 1 Here")
        self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay1.setStyleSheet("background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 24px; border-radius: 15px;")
        self.drag_overlay1.hide()

        self.drag_overlay2 = QLabel(self)
        self.drag_overlay2.setText("Drop Image 2 Here")
        self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay2.setStyleSheet("background-color: rgba(0, 0, 0, 0.5); color: white; font-size: 24px; border-radius: 15px;")
        self.drag_overlay2.hide()

    def initUI(self):
        self.setWindowTitle('Improve ImgSLI')
        self.setGeometry(100, 100, 800, 900)
        self.setAcceptDrops(True)  # Enable drag and drop

        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.btn_image1 = QPushButton('Select Image 1')
        self.btn_image2 = QPushButton('Select Image 2')
        self.btn_image1.clicked.connect(lambda: self.load_image(1))
        self.btn_image2.clicked.connect(lambda: self.load_image(2))

        self.btn_swap = QPushButton('⇄')
        self.btn_swap.setFixedSize(20, 20)
        self.btn_swap.clicked.connect(self.swap_images)
        
        btn_layout.addWidget(self.btn_image1)
        btn_layout.addWidget(self.btn_swap)
        btn_layout.addWidget(self.btn_image2)
        layout.addLayout(btn_layout)

        checkbox_layout = QHBoxLayout()
        self.checkbox_horizontal = QCheckBox('Horizontal Split')
        self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        self.checkbox_magnifier = QCheckBox('Use Magnifier')
        self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)
        
        self.help_button = QPushButton('?')
        self.help_button.setFixedSize(24, 24)  # Make it square and compact
        self.help_button.clicked.connect(self.show_help)
        
        self.freeze_button = QCheckBox('Freeze Magnifier')
        self.freeze_button.stateChanged.connect(self.toggle_freeze_magnifier)
        
        checkbox_layout.addWidget(self.checkbox_horizontal)
        checkbox_layout.addWidget(self.checkbox_magnifier)
        checkbox_layout.addWidget(self.freeze_button)
        checkbox_layout.addStretch()  # Add stretch to push help button to the right
        checkbox_layout.addWidget(self.help_button)
        layout.addLayout(checkbox_layout)

        slider_layout = QHBoxLayout()
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(50, 400)
        self.slider_size.setValue(100)
        self.slider_size.valueChanged.connect(self.update_magnifier_size)
        self.slider_capture = QSlider(Qt.Orientation.Horizontal)
        self.slider_capture.setRange(1, 200)
        self.slider_capture.setValue(50)
        self.slider_capture.valueChanged.connect(self.update_capture_size)
        self.slider_speed = QSlider(Qt.Orientation.Horizontal)
        self.slider_speed.setRange(1, 10)
        self.slider_speed.setValue(2)
        self.slider_speed.valueChanged.connect(self.update_movement_speed)
        slider_layout.addWidget(QLabel("Magnifier Size:"))
        slider_layout.addWidget(self.slider_size)
        slider_layout.addWidget(QLabel("Capture Size:"))
        slider_layout.addWidget(self.slider_capture)
        slider_layout.addWidget(QLabel("Movement Speed:"))
        slider_layout.addWidget(self.slider_speed)
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

    def show_help(self):
        help_text = ("To move magnifying glasses separately from the detection area - use WASD keys. "
                    "To change the distance between magnifying glasses - use Q and E keys. "
                    "If the distance between them becomes too small, they will merge.")
        
        QMessageBox.information(self, "Help", help_text)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.image1 and self.image2:
            self.update_comparison()
        if hasattr(self, 'drag_overlay1') and hasattr(self, 'drag_overlay2'):
            self.update_drag_overlays()
    
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
                resize_images(self)
                self.update_comparison()

    def swap_images(self):
        self.image1, self.image2 = self.image2, self.image1
        if self.image1 and self.image2:
            resize_images(self)
            self.update_comparison()

    def update_comparison(self):
        update_comparison(self)

    def toggle_orientation(self, state):
        self.is_horizontal = state == Qt.CheckState.Checked.value
        self.update_comparison()

    def toggle_magnifier(self, state):
        self.use_magnifier = state == Qt.CheckState.Checked.value
        self.update_comparison()

    def toggle_freeze_magnifier(self, state):
        self.freeze_magnifier = state == Qt.CheckState.Checked.value

    def update_magnifier_size(self, value):
        self.magnifier_size = value
        self.update_comparison()

    def update_capture_size(self, value):
        self.capture_size = value
        self.update_comparison()

    def update_movement_speed(self, value):
        self.movement_speed = value

    def save_result(self):
        save_result(self)

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
                if not self.freeze_magnifier:
                    dx = self.magnifier_position.x() - self.capture_position.x()
                    dy = self.magnifier_position.y() - self.capture_position.y()
                    self.capture_position = cursor_pos
                    self.magnifier_position = QPoint(cursor_pos.x() + dx, cursor_pos.y() + dy)
                else:
                    self.capture_position = cursor_pos
            
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

    def update_magnifier_position(self):
        if not self.use_magnifier:
            return

        needs_update = False
        
        dx = 0
        dy = 0
        
        if Qt.Key.Key_A in self.active_keys:
            dx -= self.movement_speed
        if Qt.Key.Key_D in self.active_keys:
            dx += self.movement_speed
        if Qt.Key.Key_W in self.active_keys:
            dy -= self.movement_speed
        if Qt.Key.Key_S in self.active_keys:
            dy += self.movement_speed
        if Qt.Key.Key_Q in self.active_keys:
            self.magnifier_spacing = max(0, self.magnifier_spacing - 2)
            needs_update = True
        if Qt.Key.Key_E in self.active_keys:
            self.magnifier_spacing += 2
            needs_update = True
        if dx != 0 or dy != 0:
            # При движении по диагонали нормализуем компоненты так, 
            # чтобы результирующая скорость была равна self.movement_speed
            if dx != 0 and dy != 0:
                dx = dx / sqrt(2)
                dy = dy / sqrt(2)
            
            new_x = self.magnifier_position.x() + int(dx)
            new_y = self.magnifier_position.y() + int(dy)
            
            self.magnifier_position = QPoint(new_x, new_y)
            needs_update = True

        # Update the comparison if any changes occurred
        if needs_update:
            self.update_comparison()

    def keyPressEvent(self, event):
        if self.use_magnifier:
            key = event.key()
            if key not in self.active_keys:
                self.active_keys.add(key)
                # Start timer if it's not already running
                if not self.movement_timer.isActive():
                    self.movement_timer.start()
                # Immediate update for Q/E keys
                if key in [Qt.Key.Key_Q, Qt.Key.Key_E]:
                    self.update_magnifier_position()

    def keyReleaseEvent(self, event):
        key = event.key()
        if key in self.active_keys:
            self.active_keys.remove(key)
        if not self.active_keys:
            self.movement_timer.stop()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.update_drag_overlays()
            self.drag_overlay1.show()
            self.drag_overlay2.show()

    def dragLeaveEvent(self, event):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()

    def dropEvent(self, event: QDropEvent):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path:
                    drop_pos = event.position().toPoint()
                    if self.is_in_left_area(drop_pos):
                        self.load_image_from_path(file_path, 1)
                    else:
                        self.load_image_from_path(file_path, 2)

    def load_image_from_path(self, file_path, image_number):
        image = Image.open(file_path)
        if image_number == 1:
            self.image1 = image
        else:
            self.image2 = image
        
        if self.image1 and self.image2:
            resize_images(self)
            self.update_comparison()
            
    def update_drag_overlays(self):
        if not hasattr(self, 'drag_overlay1') or not hasattr(self, 'drag_overlay2'):
            return
        width = self.width()
        height = self.height()
        overlay_width = width // 2 - 20
        overlay_height = height - 40

        self.drag_overlay1.setGeometry(10, 20, overlay_width, overlay_height)
        self.drag_overlay2.setGeometry(width // 2 + 10, 20, overlay_width, overlay_height)

    def is_in_left_area(self, pos):
        return pos.x() < self.width() // 2
