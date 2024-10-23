from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel, QFileDialog, QSizePolicy
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect
from PIL import Image, ImageDraw
from clickable_label import ClickableLabel
from image_processing import resize_images, update_comparison, draw_magnifier, draw_capture_area, save_result
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
        self.setWindowTitle('Improve ImgSLI')
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
        self.setFixedSize(self.size())
        self.setWindowFlags(self.windowFlags() |
                            Qt.WindowType.Dialog |
                                    Qt.WindowType.MSWindowsFixedSizeDialogHint)

        self.checkbox_magnifier = QCheckBox('Use Magnifier')
        self.checkbox_magnifier.setToolTip('Use WASD keys to move the magnifier glasses.\nUse Q and E keys to adjust the distance between magnifiers.')

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
        self.setFixedSize(self.size())

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

    def update_comparison(self):
        update_comparison(self)

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

