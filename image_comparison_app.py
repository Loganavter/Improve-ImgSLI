from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel, QFileDialog, QSizePolicy, QMessageBox
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QDragEnterEvent, QDropEvent, QIcon, QPixmap
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QMimeData, QSize, QSettings, QLocale
from PIL import Image, ImageDraw
import base64
from flag_icons import FLAG_ICONS
from clickable_label import ClickableLabel
from image_processing import resize_images, update_comparison, draw_magnifier, draw_capture_area, save_result
import numpy as np
from math import sqrt, cos, sin, pi
from translations import tr

class ImageComparisonApp(QWidget):
    def __init__(self):
        super().__init__()
        
        overlay_style = """
            background-color: rgba(0, 0, 0, 0.5);
            color: white;
            font-size: 24px;
            border-radius: 15px;
            padding: 10px;
        """

        self.drag_overlay1 = QLabel(self)
        self.drag_overlay1.setText(tr("Drop Image 1 Here", 'en'))
        self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay1.setStyleSheet(overlay_style)
        self.drag_overlay1.setWordWrap(True)
        self.drag_overlay1.hide()

        self.drag_overlay2 = QLabel(self)
        self.drag_overlay2.setText(tr("Drop Image 2 Here", 'en'))
        self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay2.setStyleSheet(overlay_style)
        self.drag_overlay2.setWordWrap(True)
        self.drag_overlay2.hide()

        settings = QSettings("YourCompany", "ImproveImgSLI")
        saved_lang = settings.value("language", None)
        
        if saved_lang is not None:
            self.current_language = saved_lang
        else:
            system_lang = QLocale.system().name[:2]
            self.current_language = system_lang if system_lang in ['en', 'ru', 'zh'] else 'en'
        
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
        self.movement_timer.setInterval(16)
        self.active_keys = set()
        self.movement_speed = 2
        self.magnifier_spacing = 50
        self.freeze_magnifier = False

        self.update_translations()
        self.update_language_checkboxes()

    def initUI(self):
        self.setWindowTitle('Improve ImgSLI')
        self.setGeometry(100, 100, 800, 900)
        self.setAcceptDrops(True)

        layout = QVBoxLayout()

        btn_layout = QHBoxLayout()
        self.btn_image1 = QPushButton(tr('Select Image 1', self.current_language))
        self.btn_image2 = QPushButton(tr('Select Image 2', self.current_language))
        self.btn_image1.clicked.connect(lambda: self.load_image(1))
        self.btn_image2.clicked.connect(lambda: self.load_image(2))

        self.btn_swap = QPushButton(tr('⇄', self.current_language))
        self.btn_swap.setFixedSize(20, 20)
        self.btn_swap.clicked.connect(self.swap_images)

        btn_layout.addWidget(self.btn_image1)
        btn_layout.addWidget(self.btn_swap)
        btn_layout.addWidget(self.btn_image2)
        layout.addLayout(btn_layout)

        checkbox_layout = QHBoxLayout()
        self.checkbox_horizontal = QCheckBox(tr('Horizontal Split', self.current_language))
        self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        self.checkbox_magnifier = QCheckBox(tr('Use Magnifier', self.current_language))
        self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)

        self.help_button = QPushButton('?')
        self.help_button.setFixedSize(24, 24)
        self.help_button.clicked.connect(self.show_help)

        self.freeze_button = QCheckBox(tr('Freeze Magnifier', self.current_language))
        self.freeze_button.stateChanged.connect(self.toggle_freeze_magnifier)

        self.lang_en = QCheckBox()
        self.lang_ru = QCheckBox()
        self.lang_zh = QCheckBox()

        self.lang_en.setIcon(self.create_flag_icon(FLAG_ICONS['en']))
        self.lang_ru.setIcon(self.create_flag_icon(FLAG_ICONS['ru']))
        self.lang_zh.setIcon(self.create_flag_icon(FLAG_ICONS['zh']))

        icon_size = QSize(24, 16)
        self.lang_en.setIconSize(icon_size)
        self.lang_ru.setIconSize(icon_size)
        self.lang_zh.setIconSize(icon_size)

        self.lang_en.setText('')
        self.lang_ru.setText('')
        self.lang_zh.setText('')

        style = '''
        QCheckBox {
            padding: 2px;
            border: none;
        }
        QCheckBox::indicator {
            width: 24px;
            height: 16px;
        }
        '''
        self.lang_en.setStyleSheet(style)
        self.lang_ru.setStyleSheet(style)
        self.lang_zh.setStyleSheet(style)

        checkbox_layout.addWidget(self.checkbox_horizontal)
        checkbox_layout.addWidget(self.checkbox_magnifier)
        checkbox_layout.addWidget(self.freeze_button)
        checkbox_layout.addStretch()
        checkbox_layout.addWidget(self.lang_en)
        checkbox_layout.addWidget(self.lang_ru)
        checkbox_layout.addWidget(self.lang_zh)
        checkbox_layout.addWidget(self.help_button)
        layout.addLayout(checkbox_layout)

        self.lang_en.stateChanged.connect(lambda: self.on_language_changed('en'))
        self.lang_ru.stateChanged.connect(lambda: self.on_language_changed('ru'))
        self.lang_zh.stateChanged.connect(lambda: self.on_language_changed('zh'))

        self.slider_layout = QHBoxLayout()
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
        self.slider_layout.addWidget(QLabel(tr("Magnifier Size:", self.current_language)))
        self.slider_layout.addWidget(self.slider_size)
        self.slider_layout.addWidget(QLabel(tr("Capture Size:", self.current_language)))
        self.slider_layout.addWidget(self.slider_capture)
        self.slider_layout.addWidget(QLabel(tr("Movement Speed:", self.current_language)))
        self.slider_layout.addWidget(self.slider_speed)
        layout.addLayout(self.slider_layout)

        self.image_label = ClickableLabel(self)
        self.image_label.setMinimumSize(300, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.mouseMoveEvent = self.on_mouse_move
        layout.addWidget(self.image_label)

        self.btn_save = QPushButton(tr('Save Result', self.current_language))
        self.btn_save.clicked.connect(self.save_result)
        layout.addWidget(self.btn_save)

        self.setLayout(layout)
        self.update_minimum_window_size()
        self.update_language_checkboxes()

    def create_flag_icon(self, base64_data):
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(base64_data))
        return QIcon(pixmap)

    def on_language_changed(self, language):
        self.lang_en.blockSignals(True)
        self.lang_ru.blockSignals(True)
        self.lang_zh.blockSignals(True)

        self.lang_en.setChecked(language == 'en')
        self.lang_ru.setChecked(language == 'ru')
        self.lang_zh.setChecked(language == 'zh')

        self.lang_en.blockSignals(False)
        self.lang_ru.blockSignals(False)
        self.lang_zh.blockSignals(False)

        self.change_language(language)

    def show_help(self):
        help_text = tr("To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.", self.current_language)

        QMessageBox.information(self, tr("Help", self.current_language), help_text)

    def update_language_checkboxes(self):
        self.lang_en.setChecked(self.current_language == 'en')
        self.lang_ru.setChecked(self.current_language == 'ru')
        self.lang_zh.setChecked(self.current_language == 'zh')

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
        file_name, _ = QFileDialog.getOpenFileName(self, tr(f"Select Image {image_number}", self.current_language), "", "Image Files (*.png *.jpg *.bmp)")
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
            if dx != 0 and dy != 0:
                dx = dx / sqrt(2)
                dy = dy / sqrt(2)

            new_x = self.magnifier_position.x() + int(dx)
            new_y = self.magnifier_position.y() + int(dy)

            self.magnifier_position = QPoint(new_x, new_y)
            needs_update = True

        if needs_update:
            self.update_comparison()

    def keyPressEvent(self, event):
        if self.use_magnifier:
            key = event.key()
            if key not in self.active_keys:
                self.active_keys.add(key)
                if not self.movement_timer.isActive():
                    self.movement_timer.start()
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

    def change_language(self, language):
        self.current_language = language
        self.update_translations()
        self.update_language_checkboxes()

        settings = QSettings("YourCompany", "ImproveImgSLI")
        settings.setValue("language", language)

    def update_translations(self):
        if hasattr(self, 'drag_overlay1') and hasattr(self, 'drag_overlay2'):
            self.drag_overlay1.setText(tr("Drop Image 1 Here", self.current_language))
            self.drag_overlay2.setText(tr("Drop Image 2 Here", self.current_language))

        self.btn_image1.setText(tr('Select Image 1', self.current_language))
        self.btn_image2.setText(tr('Select Image 2', self.current_language))
        self.checkbox_horizontal.setText(tr('Horizontal Split', self.current_language))
        self.checkbox_magnifier.setText(tr('Use Magnifier', self.current_language))
        self.freeze_button.setText(tr('Freeze Magnifier', self.current_language))
        self.btn_save.setText(tr('Save Result', self.current_language))
        self.drag_overlay1.setText(tr("Drop Image 1 Here", self.current_language))
        self.drag_overlay2.setText(tr("Drop Image 2 Here", self.current_language))
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        self.btn_swap.setText(tr('⇄', self.current_language))
        if self.slider_layout:
            self.slider_layout.itemAt(0).widget().setText(tr("Magnifier Size:", self.current_language))
            self.slider_layout.itemAt(2).widget().setText(tr("Capture Size:", self.current_language))
            self.slider_layout.itemAt(4).widget().setText(tr("Movement Speed:", self.current_language))
