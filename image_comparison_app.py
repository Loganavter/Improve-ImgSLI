import base64
import os
import math
import sys

from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel,
                             QFileDialog, QSizePolicy, QMessageBox, QLineEdit, QInputDialog, QApplication)
from PyQt6.QtGui import QPixmap, QPainter, QColor, QPen, QPainterPath, QDragEnterEvent, QDropEvent, QIcon, QFont
from PyQt6.QtCore import Qt, QPoint, QTimer, QRect, QEvent, QSize, QSettings, QLocale, QPointF
from translations import tr
from flag_icons import FLAG_ICONS
from clickable_label import ClickableLabel
from image_processing import (resize_images_processor, update_comparison_processor, display_result_processor,
                             draw_magnifier_processor, draw_combined_magnifier_circle_processor,
                             draw_magnifier_circle_processor, draw_capture_area_processor, save_result_processor)


class ImageComparisonApp(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("Loganavter", "ImproveImgSLI")
        saved_lang = self.settings.value("language", None)
        self.current_language = saved_lang.decode() if isinstance(saved_lang, bytes) else (QLocale.system().name()[:2] if QLocale.system().name()[:2] in ['en', 'ru', 'zh'] else 'en') if saved_lang else (QLocale.system().name()[:2] if QLocale.system().name()[:2] in ['en', 'ru', 'zh'] else 'en')
        self.max_name_length = self.settings.value("max_name_length", 20, type=int)
        saved_file_names_state = self.settings.value("include_file_names", False, type=bool)

        self.image1 = None
        self.image2 = None
        self.image1_path = None
        self.image2_path = None
        self.result_image = None
        self.is_horizontal = False
        self.use_magnifier = False
        self.split_position = 0.5
        self.magnifier_position = QPoint(300, 300)
        self.magnifier_size = 100
        self.capture_size = 50
        self.capture_position = QPoint(300, 300)
        self.movement_speed = 2
        self.magnifier_spacing = 50
        self.freeze_magnifier = False
        self.resize_in_progress = False
        self.previous_geometry = None
        self.label_pixmap_cache = None
        self.pixmap_width = 0
        self.pixmap_height = 0

        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(self.update_magnifier_position)
        self.movement_timer.setInterval(16)
        self.active_keys = set()

        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.finish_resize)

        self.init_drag_overlays()
        self.init_warning_label()
        self.initUI()

        self.checkbox_file_names.setChecked(saved_file_names_state)
        self.toggle_edit_layout_visibility(saved_file_names_state)

        saved_geometry = self.settings.value("window_geometry")
        if saved_geometry:
            self.restoreGeometry(saved_geometry)
        else:
            self.setGeometry(100, 100, 800, 900)

        self.update_minimum_window_size()

        if not saved_geometry:
            min_size = self.minimumSize()
            current_size = self.size()
            new_width = max(current_size.width(), min_size.width())
            new_height = max(current_size.height(), min_size.height())
            self.resize(new_width, new_height)

        self.connect_signals()
                
    def load_setting(self, key, default_value, value_type=None):
        return self.settings.value(key, default_value, type=value_type)

    def save_setting(self, key, value):
        self.settings = QSettings("Loganavter", "ImproveImgSLI")
        self.settings.setValue(key, value)

    def init_drag_overlays(self):
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

    def init_warning_label(self):
        self.length_warning_label = QLabel(self)
        self.length_warning_label.setStyleSheet("color: red;")
        self.length_warning_label.setVisible(False)
        self.length_warning_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.length_warning_label.mousePressEvent = self.edit_length_dialog
 
    def connect_signals(self):
            self.edit_name1.textChanged.connect(self.check_name_lengths)
            self.edit_name2.textChanged.connect(self.check_name_lengths)
            self.checkbox_file_names.toggled.connect(self.save_file_names_state)
            self.checkbox_file_names.toggled.connect(self.toggle_edit_layout_visibility)

    def initUI(self):
        self.setWindowTitle('Improve ImgSLI')
        self.setGeometry(100, 100, 800, 900)
        self.setAcceptDrops(True)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(self.create_button_layout())
        main_layout.addLayout(self.create_checkbox_layout())
        main_layout.addLayout(self.create_slider_layout())
        main_layout.addWidget(self.create_image_label())
        main_layout.addWidget(self.length_warning_label)
        main_layout.addLayout(self.create_file_names_layout())
        main_layout.addLayout(self.create_edit_layout())
        main_layout.addWidget(self.create_save_button())

        self.setLayout(main_layout)
        self.update_minimum_window_size()
        self.update_language_checkboxes()

    def create_button_layout(self):
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
        return btn_layout

    def create_checkbox_layout(self):
        checkbox_layout = QHBoxLayout()
        self.checkbox_horizontal = QCheckBox(tr('Horizontal Split', self.current_language))
        self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        self.checkbox_magnifier = QCheckBox(tr('Use Magnifier', self.current_language))
        self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)
        self.freeze_button = QCheckBox(tr('Freeze Magnifier', self.current_language))
        self.freeze_button.stateChanged.connect(self.toggle_freeze_magnifier)
        self.checkbox_file_names = QCheckBox(tr('Include file names in saved image', self.current_language))
        self.help_button = QPushButton('?')
        self.help_button.setFixedSize(24, 24)
        self.help_button.clicked.connect(self.show_help)

        self.lang_en, self.lang_ru, self.lang_zh = self.create_language_checkboxes()

        checkbox_layout.addWidget(self.checkbox_horizontal)
        checkbox_layout.addWidget(self.checkbox_magnifier)
        checkbox_layout.addWidget(self.freeze_button)
        checkbox_layout.addWidget(self.checkbox_file_names)
        checkbox_layout.addStretch()
        checkbox_layout.addWidget(self.lang_en)
        checkbox_layout.addWidget(self.lang_ru)
        checkbox_layout.addWidget(self.lang_zh)
        checkbox_layout.addWidget(self.help_button)
        return checkbox_layout

    def create_language_checkboxes(self):
        lang_en = QCheckBox()
        lang_ru = QCheckBox()
        lang_zh = QCheckBox()
        lang_en.setIcon(self.create_flag_icon(FLAG_ICONS['en']))
        lang_ru.setIcon(self.create_flag_icon(FLAG_ICONS['ru']))
        lang_zh.setIcon(self.create_flag_icon(FLAG_ICONS['zh']))

        icon_size = QSize(24, 16)
        lang_en.setIconSize(icon_size)
        lang_ru.setIconSize(icon_size)
        lang_zh.setIconSize(icon_size)
        lang_en.setText('')
        lang_ru.setText('')
        lang_zh.setText('')

        style = '''
        QCheckBox { padding: 2px; border: none; }
        QCheckBox::indicator { width: 24px; height: 16px; }
        '''
        lang_en.setStyleSheet(style)
        lang_ru.setStyleSheet(style)
        lang_zh.setStyleSheet(style)

        lang_en.toggled.connect(lambda checked: self.on_language_changed('en'))
        lang_ru.toggled.connect(lambda checked: self.on_language_changed('ru'))
        lang_zh.toggled.connect(lambda checked: self.on_language_changed('zh'))
        return lang_en, lang_ru, lang_zh
 
    def create_slider_layout(self):
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
        self.slider_speed.setRange(10, 1000)
        self.slider_speed.setValue(200)
        self.slider_speed.valueChanged.connect(self.update_movement_speed)

        self.label_magnifier_size = QLabel(tr("Magnifier Size:", self.current_language))
        self.label_capture_size = QLabel(tr("Capture Size:", self.current_language))
        self.label_movement_speed = QLabel(tr("Movement Speed:", self.current_language))

        slider_layout.addWidget(self.label_magnifier_size)
        slider_layout.addWidget(self.slider_size)
        slider_layout.addWidget(self.label_capture_size)
        slider_layout.addWidget(self.slider_capture)
        slider_layout.addWidget(self.label_movement_speed)
        slider_layout.addWidget(self.slider_speed)
        return slider_layout

    def create_image_label(self):
        self.image_label = ClickableLabel(self)
        self.image_label.setMinimumSize(300, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.mouseMoveEvent = self.on_mouse_move
        return self.image_label

    def create_file_names_layout(self):
        file_names_layout = QHBoxLayout()
        self.file_name_label1 = QLabel()
        self.file_name_label2 = QLabel()
        file_names_layout.addWidget(self.file_name_label1)
        file_names_layout.addStretch()
        file_names_layout.addWidget(self.file_name_label2)
        return file_names_layout

    def create_edit_layout(self):
        self.edit_layout = QHBoxLayout()
        self.edit_name1 = QLineEdit()
        self.edit_name1.setPlaceholderText(tr("Edit Image 1 Name", self.current_language))
        self.edit_name2 = QLineEdit()
        self.edit_name2.setPlaceholderText(tr("Edit Image 2 Name", self.current_language))

        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setRange(10, 1000)
        self.font_size_slider.setValue(200)
        self.font_size_slider.valueChanged.connect(self.update_file_names)

        self.edit_layout.addWidget(QLabel(tr("Name 1:", self.current_language)))
        self.edit_layout.addWidget(self.edit_name1)
        self.edit_layout.addWidget(QLabel(tr("Name 2:", self.current_language)))
        self.edit_layout.addWidget(self.edit_name2)
        self.edit_layout.addWidget(QLabel(tr("Font Size (%):", self.current_language)))
        self.edit_layout.addWidget(self.font_size_slider)
        return self.edit_layout

    def create_save_button(self):
        self.btn_save = QPushButton(tr('Save Result', self.current_language))
        self.btn_save.clicked.connect(self.save_result)
        return self.btn_save

    def toggle_edit_layout_visibility(self, checked):
        for i in range(self.edit_layout.count()):
            item = self.edit_layout.itemAt(i)
            if item.widget():
                item.widget().setVisible(checked)
            elif item.layout():
                for j in range(item.layout().count()):
                    sub_item = item.layout().itemAt(j)
                    if sub_item.widget():
                        sub_item.widget().setVisible(checked)
        
        self.update_minimum_window_size()
        self.layout().activate()

        is_fullscreen_or_maximized = self.windowState() & (Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMaximized)

        if is_fullscreen_or_maximized:
            self.image_label.update()
            self.update_comparison()
            QTimer.singleShot(100, self.adjust_after_toggle)
        else:
            if self.image1 and self.image2:
                self.update_comparison()
            self.update()

    def adjust_after_toggle(self):
        if self.image1 and self.image2:
            self.update_comparison()
        self.update()

    def check_name_lengths(self):
        name1 = self.edit_name1.text() or (os.path.basename(self.image1_path) if self.image1_path else "Image 1")
        name2 = self.edit_name2.text() or (os.path.basename(self.image2_path) if self.image2_path else "Image 2")
        if len(name1) > self.max_name_length or len(name2) > self.max_name_length:
            self.length_warning_label.setText(tr("Reduce Length!", self.current_language))
            tooltip = tr("Current length is {length}, which exceeds the maximum {max_length}", self.current_language).format(
                length=max(len(name1), len(name2)), max_length=self.max_name_length)
            self.length_warning_label.setToolTip(tooltip)
            self.length_warning_label.setVisible(True)
        else:
            self.length_warning_label.setVisible(False)

    def edit_length_dialog(self, event):
        new_limit, ok = QInputDialog.getInt(self, tr("Edit Length Limit", self.current_language),
                                            tr("Enter new maximum length (10-100):", self.current_language),
                                            value=self.max_name_length, min=10, max=100)
        if ok:
            self.max_name_length = new_limit
            self.save_setting("max_name_length", new_limit)
            self.check_name_lengths()

    def create_flag_icon(self, base64_data):
        pixmap = QPixmap()
        pixmap.loadFromData(base64.b64decode(base64_data))
        return QIcon(pixmap)

    def on_language_changed(self, language):
        self.block_language_checkbox_signals(True)
        current_active = {'en': self.lang_en.isChecked(), 'ru': self.lang_ru.isChecked(), 'zh': self.lang_zh.isChecked()}
        active_count = sum(1 for checked in current_active.values() if checked)
        if active_count == 1 and current_active[language] and not getattr(self, f'lang_{language}').isChecked():
            getattr(self, f'lang_{language}').setChecked(True)
        else:
            self.lang_en.setChecked(language == 'en')
            self.lang_ru.setChecked(language == 'ru')
            self.lang_zh.setChecked(language == 'zh')
            self.change_language(language)
        self.block_language_checkbox_signals(False)

    def block_language_checkbox_signals(self, block):
        self.lang_en.blockSignals(block)
        self.lang_ru.blockSignals(block)
        self.lang_zh.blockSignals(block)

    def show_help(self):
        help_text = tr("To move magnifying glasses separately from the detection area - use WASD keys. To change the distance between magnifying glasses - use Q and E keys. If the distance between them becomes too small, they will merge.", self.current_language)
        QMessageBox.information(self, tr("Help", self.current_language), help_text)

    def update_language_checkboxes(self):
        self.lang_en.setChecked(self.current_language == 'en')
        self.lang_ru.setChecked(self.current_language == 'ru')
        self.lang_zh.setChecked(self.current_language == 'zh')

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_in_progress = True
        self.update_drag_overlays()
        self.resize_timer.start(200)

    def finish_resize(self):
        self.resize_in_progress = False
        if self.image1 and self.image2:
            self.update_comparison()

    def update_minimum_window_size(self):
        min_width = 300
        min_height = 0
        for i in range(self.layout().count()):
            item = self.layout().itemAt(i)
            if item.widget() and item.widget().isVisible() and item.widget() != self.image_label:
                height = item.widget().sizeHint().height()
                min_height += height
            elif item.layout() and item.layout().isEnabled():
                layout_height = 0
                for j in range(item.layout().count()):
                    sub_item = item.layout().itemAt(j)
                    if sub_item.widget() and sub_item.widget().isVisible():
                        sub_height = sub_item.widget().sizeHint().height()
                        layout_height += sub_height
                    elif sub_item.layout():
                        sub_layout_height = sub_item.layout().sizeHint().height()
                        layout_height += sub_layout_height
                min_height += layout_height
        min_height += self.image_label.minimumSize().height()
        self.setMinimumSize(min_width, min_height)

    def load_image(self, image_number):
        file_name, _ = QFileDialog.getOpenFileName(self, tr(f"Select Image {image_number}", self.current_language), "", "Image Files (*.png *.jpg *.bmp)")
        if file_name:
            try:
                image = Image.open(file_name)
            except Exception as e:
                QMessageBox.warning(self, tr("Error", self.current_language), tr("Failed to load image: ", self.current_language) + str(e))
                return

            if image_number == 1:
                self.image1 = image
                self.image1_path = file_name
                self.edit_name1.setText(os.path.basename(file_name))
            else:
                self.image2 = image
                self.image2_path = file_name
                self.edit_name2.setText(os.path.basename(file_name))

            if self.image1 and self.image2:
                resize_images_processor(self)
                self.update_comparison()
                self.update_file_names()
                self.label_pixmap_cache = None

    def swap_images(self):
        self.image1, self.image2 = self.image2, self.image1
        self.image1_path, self.image2_path = self.image2_path, self.image1_path
        name1 = self.edit_name1.text()
        name2 = self.edit_name2.text()
        self.edit_name1.setText(name2)
        self.edit_name2.setText(name1)
        if self.image1 and self.image2:
            resize_images_processor(self)
            self.update_comparison()
            self.update_file_names()
            self.label_pixmap_cache = None

    def update_comparison(self):
        if self.resize_in_progress:
            return
        update_comparison_processor(self)
        if self.image_label.pixmap():
            pixmap = self.image_label.pixmap()
            self.pixmap_width = pixmap.width()
            self.pixmap_height = pixmap.height()

    def toggle_orientation(self, state):
        self.is_horizontal = state == Qt.CheckState.Checked.value
        self.update_comparison()
        self.update_file_names()
        self.label_pixmap_cache = None

    def toggle_magnifier(self, state):
        self.use_magnifier = state == Qt.CheckState.Checked.value
        self.update_comparison()
        self.label_pixmap_cache = None

    def toggle_freeze_magnifier(self, state):
        self.freeze_magnifier = state == Qt.CheckState.Checked.value

    def update_file_names(self):
        name1 = os.path.basename(self.image1_path) if self.image1_path else "Image 1"
        name2 = os.path.basename(self.image2_path) if self.image2_path else "Image 2"
        if not self.is_horizontal:
            self.file_name_label1.setText(f"{tr('Left', self.current_language)}: {name1}")
            self.file_name_label2.setText(f"{tr('Right', self.current_language)}: {name2}")
        else:
            self.file_name_label1.setText(f"{tr('Top', self.current_language)}: {name1}")
            self.file_name_label2.setText(f"{tr('Bottom', self.current_language)}: {name2}")

    def update_magnifier_size(self, value):
        self.magnifier_size = value
        self.update_comparison()

    def update_capture_size(self, value):
        self.capture_size = value
        self.update_comparison()

    def update_movement_speed(self, value):
        self.movement_speed = value / 100

    def save_result(self):
        save_result_processor(self)

    def save_file_names_state(self, checked):
        self.save_setting("include_file_names", checked)

    def on_mouse_move(self, event):
        if self.image_label.pixmap() and not self.resize_in_progress and event.buttons() & Qt.MouseButton.LeftButton:
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
                self.split_position = adjusted_x / pixmap.width() if not self.is_horizontal else adjusted_y / pixmap.height()
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
        pixmap_width = self.pixmap_width if self.pixmap_width > 0 else pixmap.width()
        pixmap_height = self.pixmap_height if self.pixmap_height > 0 else pixmap.height()
        label_rect = self.image_label.rect()
        x_offset = (label_rect.width() - pixmap_width) // 2
        y_offset = (label_rect.height() - pixmap_height) // 2
        interaction_area = QRect(x_offset, y_offset, pixmap_width, pixmap_height)
        return interaction_area.contains(pos)

    def update_magnifier_position(self):
        if not self.use_magnifier or self.resize_in_progress:
            return
        needs_update = False
        dx = dy = 0
        if Qt.Key.Key_A in self.active_keys: dx -= self.movement_speed
        if Qt.Key.Key_D in self.active_keys: dx += self.movement_speed
        if Qt.Key.Key_W in self.active_keys: dy -= self.movement_speed
        if Qt.Key.Key_S in self.active_keys: dy += self.movement_speed
        if Qt.Key.Key_Q in self.active_keys:
            self.magnifier_spacing = max(0, self.magnifier_spacing - 2)
            needs_update = True
        if Qt.Key.Key_E in self.active_keys:
            self.magnifier_spacing += 2
            needs_update = True
        if dx != 0 or dy != 0:
            if dx != 0 and dy != 0:
                dx /= math.sqrt(2)
                dy /= math.sqrt(2)
            self.magnifier_position = QPoint(self.magnifier_position.x() + int(dx), self.magnifier_position.y() + int(dy))
            needs_update = True
        if needs_update:
            self.update_comparison()

    def keyPressEvent(self, event):
        if self.use_magnifier:
            key = event.key()
            if key in [Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_Q, Qt.Key.Key_E] and key not in self.active_keys:
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
            self.drag_overlay1.raise_()
            self.drag_overlay2.raise_()

    def dragLeaveEvent(self, event):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & (Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMaximized):
                self.previous_geometry = self.geometry()
            else:
                if self.previous_geometry:
                    self.update_minimum_window_size()
                    min_size = self.minimumSize()
                    prev_rect = self.previous_geometry
                    new_width = max(prev_rect.width(), min_size.width())
                    new_height = max(prev_rect.height(), min_size.height())
                    self.setGeometry(prev_rect.x(), prev_rect.y(), new_width, new_height)
                    self.previous_geometry = None
                    self.adjustSize()
                    QTimer.singleShot(100, self.update_comparison)

    def dropEvent(self, event: QDropEvent):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if file_path:
                    drop_pos = event.position().toPoint()
                    self.load_image_from_path(file_path, 1 if self.is_in_left_area(drop_pos) else 2)

    def load_image_from_path(self, file_path, image_number):
        try:
            image = Image.open(file_path)
            if image_number == 1:
                self.image1 = image
                self.image1_path = file_path
                self.edit_name1.setText(os.path.basename(file_path))
            else:
                self.image2 = image
                self.image2_path = file_path
                self.edit_name2.setText(os.path.basename(file_path))
            if self.image1 and self.image2:
                resize_images_processor(self)
                self.update_comparison()
                self.update_file_names()
                self.label_pixmap_cache = None
        except Exception as e:
            QMessageBox.warning(self, tr("Error", self.current_language), tr("Failed to load image: ", self.current_language) + str(e))

    def update_drag_overlays(self):
        if not hasattr(self, 'drag_overlay1') or not hasattr(self, 'drag_overlay2'):
            return
        label_geometry = self.image_label.geometry()
        label_x, label_y = label_geometry.x(), label_geometry.y()
        label_width, label_height = label_geometry.width(), label_geometry.height()
        overlay_width = label_width // 2 - 10
        overlay_height = label_height - 20
        self.drag_overlay1.setGeometry(label_x + 5, label_y + 10, overlay_width, overlay_height)
        self.drag_overlay2.setGeometry(label_x + label_width // 2 + 5, label_y + 10, overlay_width, overlay_height)

    def is_in_left_area(self, pos):
        label_geometry = self.image_label.geometry()
        return pos.x() < (label_geometry.x() + label_geometry.width() // 2)

    def change_language(self, language):
        self.current_language = language
        self.update_translations()
        self.update_file_names()
        self.update_language_checkboxes()
        self.save_setting("language", language)

    def update_translations(self):
        if hasattr(self, 'drag_overlay1') and hasattr(self, 'drag_overlay2'):
            self.drag_overlay1.setText(tr("Drop Image 1 Here", self.current_language))
            self.drag_overlay2.setText(tr("Drop Image 2 Here", self.current_language))
        self.btn_image1.setText(tr('Select Image 1', self.current_language))
        self.btn_image2.setText(tr('Select Image 2', self.current_language))
        self.checkbox_horizontal.setText(tr('Horizontal Split', self.current_language))
        self.checkbox_magnifier.setText(tr('Use Magnifier', self.current_language))
        self.freeze_button.setText(tr('Freeze Magnifier', self.current_language))
        self.checkbox_file_names.setText(tr('Include file names in saved image', self.current_language))
        self.btn_save.setText(tr('Save Result', self.current_language))
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        self.btn_swap.setText(tr('⇄', self.current_language))

        if hasattr(self, 'label_magnifier_size'):
            self.label_magnifier_size.setText(tr("Magnifier Size:", self.current_language))
        if hasattr(self, 'label_capture_size'):
            self.label_capture_size.setText(tr("Capture Size:", self.current_language))
        if hasattr(self, 'label_movement_speed'):
            self.label_movement_speed.setText(tr("Movement Speed:", self.current_language))

        if hasattr(self, 'edit_layout'):
            self.edit_name1.setPlaceholderText(tr("Edit Image 1 Name", self.current_language))
            self.edit_name2.setPlaceholderText(tr("Edit Image 2 Name", self.current_language))
            self.edit_layout.itemAt(0).widget().setText(tr("Name 1:", self.current_language))
            self.edit_layout.itemAt(2).widget().setText(tr("Name 2:", self.current_language))
            self.edit_layout.itemAt(4).widget().setText(tr("Font Size (%):", self.current_language))

    def closeEvent(self, event):
        if not (self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)):
            self.settings.setValue("window_geometry", self.saveGeometry())
        super().closeEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageComparisonApp()
    window.show()
    sys.exit(app.exec())
