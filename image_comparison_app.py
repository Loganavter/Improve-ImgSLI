import base64
import os
import math
import sys

from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel,
                             QFileDialog, QSizePolicy, QMessageBox, QLineEdit, QInputDialog, QApplication,
                             QColorDialog)
from PyQt6.QtGui import QPixmap, QIcon, QFont, QColor, QPainter, QBrush, QPen
from PyQt6.QtCore import (Qt, QPoint, QTimer, QPointF, QRect, QEvent, QSize, QSettings, QLocale,
                          QElapsedTimer, QRectF, QByteArray)
from translations import tr
from flag_icons import FLAG_ICONS
from clickable_label import ClickableLabel
from image_processing import (resize_images_processor, update_comparison_processor, save_result_processor,
                              get_scaled_pixmap_dimensions, get_original_coords)


class ImageComparisonApp(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MyCompany", "ImageComparisonApp")

        self._load_settings()
        self._init_state()
        self._init_timers()
        self._build_ui()
        self._apply_initial_settings_to_ui()
        self._connect_signals()
        self._restore_geometry()

        self.update_file_names() # Initial call
        self.update_minimum_window_size()
        self.update_comparison_if_needed()

    # --- Initialization Methods ---

    def _load_settings(self):
        """Loads settings from QSettings with type conversion handling."""
        self.settings = QSettings("MyCompany", "ImageComparisonApp")

        def get_setting(key, default, target_type):
            value = self.settings.value(key, default)
            if value is None: return default
            try:
                if target_type == int: return int(value) if isinstance(value, (int, str, float)) else default # Allow float conversion to int
                elif target_type == float: return float(value) if isinstance(value, (int, float, str)) else default
                elif target_type == bool:
                    if isinstance(value, str): # Handle "true"/"false" strings
                        if value.lower() == 'true': return True
                        if value.lower() == 'false': return False
                    return bool(value) if isinstance(value, (bool, int)) else default # Standard bool/int conversion
                elif target_type == str: return str(value)
                elif target_type == QColor:
                    color_val = str(value)
                    if QColor.isValidColorName(color_val): return QColor(color_val)
                    test_color = QColor(color_val)
                    if test_color.isValid(): return test_color
                    return default
                # Handle QByteArray specifically for geometry
                elif target_type == QByteArray:
                     if isinstance(value, QByteArray): return value
                     return default # Return default (which should be None or appropriate type)
                return value # Return as is for other types
            except (ValueError, TypeError) as e:
                 return default

        self.capture_pos_rel_x = get_setting("capture_relative_x", 0.5, float)
        self.capture_pos_rel_y = get_setting("capture_relative_y", 0.5, float)
        self.magnifier_offset_x = get_setting("magnifier_offset_pixels_x", 0.0, float)
        self.magnifier_offset_y = get_setting("magnifier_offset_pixels_y", -100.0, float)

        saved_lang = get_setting("language", None, str)
        if isinstance(saved_lang, bytes): saved_lang = saved_lang.decode()
        default_lang = QLocale.system().name()[:2]
        if default_lang not in ['en', 'ru', 'zh']: default_lang = 'en'
        self.loaded_language = saved_lang or default_lang

        self.loaded_max_name_length = get_setting("max_name_length", 30, int)
        self.loaded_file_names_state = get_setting("include_file_names", False, bool)
        self.loaded_magnifier_size = get_setting("magnifier_size", 250, int)
        self.loaded_capture_size = get_setting("capture_size", 120, int)
        self.loaded_magnifier_spacing = get_setting("magnifier_spacing", 10, int)
        self.loaded_movement_speed = get_setting("movement_speed_per_sec", 150, int)
        self.loaded_spacing_speed = get_setting("spacing_speed_per_sec", 300, int)
        self.loaded_geometry = self.settings.value("window_geometry", None)
        default_color_name = QColor(255, 0, 0, 255).name(QColor.NameFormat.HexArgb)
        self.loaded_filename_color_name = get_setting("filename_color", default_color_name, str)

    def _init_state(self):
        """Initializes internal application state variables."""
        self.original_image1 = None
        self.original_image2 = None
        self.image1 = None
        self.image2 = None
        self.image1_path = None
        self.image2_path = None
        self.result_image = None
        self.is_horizontal = False
        self.use_magnifier = False
        self.freeze_magnifier = False
        self.split_position = 0.5

        self.capture_position_relative = QPointF(self.capture_pos_rel_x, self.capture_pos_rel_y)
        self.magnifier_offset_float = QPointF(self.magnifier_offset_x, self.magnifier_offset_y)
        self.magnifier_offset_float_visual = QPointF(self.magnifier_offset_x, self.magnifier_offset_y)
        self.magnifier_offset_pixels = QPoint(round(self.magnifier_offset_x), round(self.magnifier_offset_y))
        self.frozen_magnifier_position_relative = None

        self.magnifier_size = self.loaded_magnifier_size
        self.capture_size = self.loaded_capture_size
        self.MIN_MAGNIFIER_SPACING = 0.0
        clamped_loaded_spacing = max(int(self.MIN_MAGNIFIER_SPACING), self.loaded_magnifier_spacing)
        self.magnifier_spacing = clamped_loaded_spacing
        self._magnifier_spacing_float = float(clamped_loaded_spacing)
        self._magnifier_spacing_float_visual = float(clamped_loaded_spacing)

        self.movement_speed_per_sec = self.loaded_movement_speed
        self.spacing_speed_per_sec = self.loaded_spacing_speed

        self.smoothing_factor_pos = 0.25
        self.smoothing_factor_spacing = 0.25
        self.lerp_stop_threshold = 0.1
        self.max_target_delta_per_tick = 15.0

        self.current_language = self.loaded_language
        self.max_name_length = self.loaded_max_name_length # Correctly assigned here
        self.resize_in_progress = False
        self.previous_geometry = None # Should store QByteArray
        self.pixmap_width = 0
        self.pixmap_height = 0
        self.active_keys = set()
        self._is_dragging_split_line = False

        self.file_name_color = QColor(self.loaded_filename_color_name)
        if not self.file_name_color.isValid():
            self.file_name_color = QColor(255, 0, 0, 255)

    def _init_timers(self):
        self.movement_timer = QTimer(self)
        self.movement_timer.setInterval(16)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._finish_resize)

    # --- UI Creation Helpers ---
    def _build_ui(self):
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        self.setAcceptDrops(True)
        self._init_drag_overlays()
        self._init_warning_label()
        main_layout = QVBoxLayout(self)
        main_layout.addLayout(self._create_button_layout())
        main_layout.addLayout(self._create_checkbox_layout())
        main_layout.addLayout(self._create_slider_layout())
        main_layout.addWidget(self._create_image_label())
        main_layout.addWidget(self.length_warning_label)
        main_layout.addLayout(self._create_file_names_layout())
        main_layout.addLayout(self._create_edit_layout())
        main_layout.addWidget(self._create_save_button())
        self.setLayout(main_layout)
        self.update_translations()

    def _apply_initial_settings_to_ui(self):
        if hasattr(self, 'slider_size'): self.slider_size.setValue(self.magnifier_size)
        if hasattr(self, 'slider_capture'): self.slider_capture.setValue(self.capture_size)
        if hasattr(self, 'slider_speed'): self.slider_speed.setValue(self.movement_speed_per_sec)
        if hasattr(self, 'checkbox_file_names'): self.checkbox_file_names.setChecked(self.loaded_file_names_state)
        if hasattr(self, 'edit_layout'): self.toggle_edit_layout_visibility(self.loaded_file_names_state)
        self.update_language_checkboxes()
        if hasattr(self, 'btn_color_picker'): self._update_color_button_tooltip()

        mag_widgets_visible = self.use_magnifier
        if hasattr(self, 'slider_size'): self.slider_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'slider_capture'): self.slider_capture.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_magnifier_size'): self.label_magnifier_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_capture_size'): self.label_capture_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'freeze_button'): self.freeze_button.setEnabled(mag_widgets_visible)
        if hasattr(self, 'slider_speed'): self.slider_speed.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_movement_speed'): self.label_movement_speed.setVisible(mag_widgets_visible)

    def _connect_signals(self):
        if hasattr(self, 'btn_image1'): self.btn_image1.clicked.connect(lambda: self.load_image(1))
        if hasattr(self, 'btn_image2'): self.btn_image2.clicked.connect(lambda: self.load_image(2))
        if hasattr(self, 'btn_swap'): self.btn_swap.clicked.connect(self.swap_images)
        if hasattr(self, 'btn_save'): self.btn_save.clicked.connect(self._save_result_with_error_handling)
        if hasattr(self, 'help_button'): self.help_button.clicked.connect(self._show_help_dialog)
        if hasattr(self, 'btn_color_picker'): self.btn_color_picker.clicked.connect(self._open_color_dialog)
        if hasattr(self, 'checkbox_horizontal'): self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        if hasattr(self, 'checkbox_magnifier'): self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)
        if hasattr(self, 'freeze_button'): self.freeze_button.stateChanged.connect(self.toggle_freeze_magnifier)
        if hasattr(self, 'checkbox_file_names'):
            self.checkbox_file_names.toggled.connect(self._save_file_names_state)
            self.checkbox_file_names.toggled.connect(self.toggle_edit_layout_visibility)
            self.checkbox_file_names.toggled.connect(self.update_comparison_if_needed)
        if hasattr(self, 'lang_en'): self.lang_en.toggled.connect(lambda: self._on_language_changed('en'))
        if hasattr(self, 'lang_ru'): self.lang_ru.toggled.connect(lambda: self._on_language_changed('ru'))
        if hasattr(self, 'lang_zh'): self.lang_zh.toggled.connect(lambda: self._on_language_changed('zh'))
        if hasattr(self, 'slider_size'): self.slider_size.valueChanged.connect(self.update_magnifier_size)
        if hasattr(self, 'slider_capture'): self.slider_capture.valueChanged.connect(self.update_capture_size)
        if hasattr(self, 'slider_speed'): self.slider_speed.valueChanged.connect(self.update_movement_speed)
        if hasattr(self, 'font_size_slider'): self.font_size_slider.valueChanged.connect(lambda: self.update_comparison_if_needed() if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked() else None)

        # --- MODIFIED: Connect edit boxes to update_file_names ---
        if hasattr(self, 'edit_name1'):
            # Remove old connection if it exists (optional, good practice)
            # try: self.edit_name1.textChanged.disconnect(self.check_name_lengths)
            # except TypeError: pass # Ignore if not connected
            self.edit_name1.textChanged.connect(self.update_file_names) # Connect to update function
        if hasattr(self, 'edit_name2'):
            # Remove old connection if it exists (optional, good practice)
            # try: self.edit_name2.textChanged.disconnect(self.check_name_lengths)
            # except TypeError: pass # Ignore if not connected
            self.edit_name2.textChanged.connect(self.update_file_names) # Connect to update function
        # --- END MODIFICATION ---

        if hasattr(self, 'movement_timer'): self.movement_timer.timeout.connect(self._update_magnifier_position_by_keys)
        if hasattr(self, 'length_warning_label'): self.length_warning_label.mousePressEvent = self._edit_length_dialog

        if hasattr(self, 'image_label'):
            if hasattr(self.image_label, 'mousePressed'):
                self.image_label.mousePressed.connect(self.on_mouse_press)
            if hasattr(self.image_label, 'mouseMoved'):
                self.image_label.mouseMoved.connect(self.on_mouse_move)
            if hasattr(self.image_label, 'mouseReleased'):
                self.image_label.mouseReleased.connect(self.on_mouse_release)

    def _restore_geometry(self):
        """Restores window geometry from settings."""
        if self.loaded_geometry:
            try:
                if isinstance(self.loaded_geometry, QByteArray):
                    if not self.restoreGeometry(self.loaded_geometry):
                         self.setGeometry(100, 100, 800, 900)
                elif isinstance(self.loaded_geometry, (bytes, bytearray)):
                     if not self.restoreGeometry(self.loaded_geometry):
                         self.setGeometry(100, 100, 800, 900)
                else:
                     self.setGeometry(100, 100, 800, 900)
            except Exception as e:
                 self.setGeometry(100, 100, 800, 900)
        else:
            self.setGeometry(100, 100, 800, 900) # Default geometry

        self.update_minimum_window_size()
        min_size = self.minimumSize()
        current_size = self.size()
        new_width = max(current_size.width(), min_size.width())
        new_height = max(current_size.height(), min_size.height())
        if current_size.width() < min_size.width() or current_size.height() < min_size.height():
            self.resize(new_width, new_height)

    def _init_drag_overlays(self):
        style = "background-color: rgba(0,0,0,0.5); color: white; font-size: 24px; border-radius: 15px; padding: 10px;"
        self.drag_overlay1 = QLabel(self); self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter); self.drag_overlay1.setStyleSheet(style); self.drag_overlay1.setWordWrap(True); self.drag_overlay1.hide()
        self.drag_overlay2 = QLabel(self); self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter); self.drag_overlay2.setStyleSheet(style); self.drag_overlay2.setWordWrap(True); self.drag_overlay2.hide()

    def _init_warning_label(self):
        self.length_warning_label = QLabel(self); self.length_warning_label.setStyleSheet("color: red;"); self.length_warning_label.setVisible(False); self.length_warning_label.setCursor(Qt.CursorShape.PointingHandCursor)

    def _create_button_layout(self):
        layout = QHBoxLayout(); self.btn_image1 = QPushButton(); self.btn_image2 = QPushButton(); self.btn_swap = QPushButton(); self.btn_swap.setFixedSize(20, 20)
        layout.addWidget(self.btn_image1); layout.addWidget(self.btn_swap); layout.addWidget(self.btn_image2); return layout

    def _create_checkbox_layout(self):
        layout = QHBoxLayout(); self.checkbox_horizontal = QCheckBox(); self.checkbox_magnifier = QCheckBox(); self.freeze_button = QCheckBox(); self.checkbox_file_names = QCheckBox()
        self.help_button = QPushButton('?'); self.help_button.setFixedSize(24, 24)
        self.lang_en, self.lang_ru, self.lang_zh = self._create_language_checkboxes()
        layout.addWidget(self.checkbox_horizontal); layout.addWidget(self.checkbox_magnifier); layout.addWidget(self.freeze_button); layout.addWidget(self.checkbox_file_names)
        layout.addStretch(); layout.addWidget(self.lang_en); layout.addWidget(self.lang_ru); layout.addWidget(self.lang_zh); layout.addWidget(self.help_button); return layout

    def _create_language_checkboxes(self):
        en, ru, zh = QCheckBox(), QCheckBox(), QCheckBox()
        flags = {'en': en, 'ru': ru, 'zh': zh}
        size = QSize(24, 16); style = 'QCheckBox{padding:2px;border:none;}QCheckBox::indicator{width:24px;height:16px;}'
        for code, cb in flags.items():
            if code in FLAG_ICONS: cb.setIcon(self._create_flag_icon(FLAG_ICONS[code]))
            cb.setIconSize(size); cb.setText(''); cb.setStyleSheet(style)
        return en, ru, zh

    def _create_slider_layout(self):
        layout = QHBoxLayout(); self.label_magnifier_size = QLabel(); self.slider_size = QSlider(Qt.Orientation.Horizontal, minimum=50, maximum=1500) # Min size reduced
        self.label_capture_size = QLabel(); self.slider_capture = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=500) # Max size increased
        self.label_movement_speed = QLabel(); self.slider_speed = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=500)
        layout.addWidget(self.label_magnifier_size); layout.addWidget(self.slider_size); layout.addWidget(self.label_capture_size); layout.addWidget(self.slider_capture); layout.addWidget(self.label_movement_speed); layout.addWidget(self.slider_speed); return layout

    def _create_image_label(self):
        self.image_label = ClickableLabel(self)
        self.image_label.setMinimumSize(300, 200)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMouseTracking(True)
        return self.image_label

    def _create_file_names_layout(self):
        layout = QHBoxLayout(); self.file_name_label1 = QLabel(); self.file_name_label2 = QLabel()
        layout.addWidget(self.file_name_label1); layout.addStretch(); layout.addWidget(self.file_name_label2); return layout

    def _create_edit_layout(self):
        self.edit_layout = QHBoxLayout(); self.label_edit_name1 = QLabel(); self.edit_name1 = QLineEdit(); self.label_edit_name2 = QLabel(); self.edit_name2 = QLineEdit()
        self.label_edit_font_size = QLabel(); self.font_size_slider = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=1000, value=200)
        self.btn_color_picker = QPushButton(); icon_size = QSize(20, 20); self.btn_color_picker.setIcon(self._create_color_wheel_icon(icon_size)); self.btn_color_picker.setIconSize(icon_size)
        self.btn_color_picker.setFixedSize(26, 26); self.btn_color_picker.setStyleSheet("QPushButton{border:1px solid grey; border-radius:13px;}")
        self.edit_layout.addWidget(self.label_edit_name1); self.edit_layout.addWidget(self.edit_name1); self.edit_layout.addWidget(self.label_edit_name2); self.edit_layout.addWidget(self.edit_name2)
        self.edit_layout.addWidget(self.label_edit_font_size); self.edit_layout.addWidget(self.font_size_slider); self.edit_layout.addWidget(self.btn_color_picker); return self.edit_layout

    def _create_color_wheel_icon(self, size: QSize) -> QIcon:
        pixmap = QPixmap(size); pixmap.fill(Qt.GlobalColor.transparent); painter = QPainter(pixmap); painter.setRenderHint(QPainter.RenderHint.Antialiasing); painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(0.5, 0.5, size.width() - 1, size.height() - 1); num_segments = 6; angle_step = 360 / num_segments
        for i in range(num_segments):
            color = QColor.fromHsvF(i / num_segments, 1.0, 1.0, 1.0); painter.setBrush(QBrush(color))
            painter.drawPie(rect, int(i * angle_step) * 16, int(angle_step) * 16)
        painter.end(); return QIcon(pixmap)

    def _create_save_button(self):
        self.btn_save = QPushButton(); return self.btn_save

    # --- Event Handlers ---
    def resizeEvent(self, event):
        super().resizeEvent(event); self.resize_in_progress = True; self._update_drag_overlays(); self.resize_timer.start(250)

    def _finish_resize(self):
        self.resize_in_progress = False; self.update_comparison_if_needed()

    def keyPressEvent(self, event):
        if self.use_magnifier:
            key = event.key(); valid_keys = {Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_Q, Qt.Key.Key_E}
            if key in valid_keys and not event.isAutoRepeat():
                self.active_keys.add(key)
                if not self.movement_timer.isActive(): self.movement_elapsed_timer.start(); self.last_update_elapsed = self.movement_elapsed_timer.elapsed(); self.movement_timer.start()
        else: super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        if not event.isAutoRepeat() and key in self.active_keys:
            self.active_keys.remove(key)
            if not self.active_keys:
                if not self.freeze_magnifier: self.magnifier_offset_float.setX(self.magnifier_offset_float_visual.x()); self.magnifier_offset_float.setY(self.magnifier_offset_float_visual.y())
        else: super().keyReleaseEvent(event)

    def on_mouse_press(self, event):
        """Handles mouse presses on the image label."""
        if not self.original_image1 or not self.original_image2:
            return
        if self.use_magnifier:
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_split_line = True
            self._update_split_or_capture_position(event.position())

    def on_mouse_move(self, event):
        """Handles mouse movements over the image label."""
        if self.resize_in_progress:
            return
        if not self.original_image1 or not self.original_image2:
            return

        should_update_split = not self.use_magnifier and self._is_dragging_split_line and (event.buttons() & Qt.MouseButton.LeftButton)
        should_update_capture = self.use_magnifier and (event.buttons() & Qt.MouseButton.LeftButton)

        if should_update_split or should_update_capture:
            self._update_split_or_capture_position(event.position())

    def on_mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_split_line = False

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): event.acceptProposedAction(); self._update_drag_overlays(); self.drag_overlay1.setText(tr("Drop Image 1 Here", self.current_language)); self.drag_overlay2.setText(tr("Drop Image 2 Here", self.current_language)); self.drag_overlay1.show(); self.drag_overlay2.show(); self.drag_overlay1.raise_(); self.drag_overlay2.raise_()

    def dragLeaveEvent(self, event):
        self.drag_overlay1.hide(); self.drag_overlay2.hide()

    def dropEvent(self, event):
        self.drag_overlay1.hide(); self.drag_overlay2.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls:
                file_path = urls[0].toLocalFile()
                if os.path.isfile(file_path) and file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                     target_image_num = 1 if self._is_in_left_area(event.position().toPoint()) else 2
                     self._load_image_from_path(file_path, target_image_num)
                elif not os.path.isfile(file_path): QMessageBox.warning(self, tr("Error", self.current_language), tr("Invalid file path.", self.current_language))
                else: QMessageBox.warning(self, tr("Error", self.current_language), tr("Unsupported file type.", self.current_language))

    def changeEvent(self, event):
        """Handles language changes and window state changes."""
        if event.type() == QEvent.Type.LanguageChange:
            self.update_translations()
        elif event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & (Qt.WindowState.WindowFullScreen | Qt.WindowState.WindowMaximized):
                if not self.previous_geometry:
                     self.previous_geometry = self.saveGeometry() # QByteArray
            elif self.previous_geometry:
                try:
                    if isinstance(self.previous_geometry, QByteArray):
                        if not self.restoreGeometry(self.previous_geometry):
                            pass
                    QTimer.singleShot(10, lambda: setattr(self, 'previous_geometry', None))
                    QTimer.singleShot(50, self.update_comparison_if_needed)
                except Exception as e:
                    self.previous_geometry = None
        super().changeEvent(event)

    def closeEvent(self, event):
        """Saves settings on application close."""
        geometry_to_save = None
        if not (self.windowState() & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)):
            geometry_to_save = self.saveGeometry() # QByteArray
        elif self.previous_geometry and isinstance(self.previous_geometry, QByteArray):
             geometry_to_save = self.previous_geometry

        if isinstance(geometry_to_save, QByteArray):
            self.save_setting("window_geometry", geometry_to_save)

        self.save_setting("capture_relative_x", self.capture_position_relative.x())
        self.save_setting("capture_relative_y", self.capture_position_relative.y())
        self.save_setting("magnifier_offset_pixels_x", self.magnifier_offset_float.x())
        self.save_setting("magnifier_offset_pixels_y", self.magnifier_offset_float.y())
        self.save_setting("magnifier_size", self.magnifier_size)
        self.save_setting("capture_size", self.capture_size)
        clamped_final_spacing = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float)
        self.save_setting("magnifier_spacing", round(clamped_final_spacing))
        self.save_setting("movement_speed_per_sec", self.movement_speed_per_sec)
        self.save_setting("spacing_speed_per_sec", self.spacing_speed_per_sec)
        self.save_setting("language", self.current_language)
        self.save_setting("max_name_length", self.max_name_length)
        if hasattr(self, 'checkbox_file_names'): self.save_setting("include_file_names", self.checkbox_file_names.isChecked())
        self.save_setting("filename_color", self.file_name_color.name(QColor.NameFormat.HexArgb))
        super().closeEvent(event)

    # --- Core Logic & Actions ---
    def update_comparison(self):
        if not self.resize_in_progress and self.image1 and self.image2:
            try: update_comparison_processor(self)
            except Exception as e:
                QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to update comparison view:', self.current_language)}\n{e}")

    def update_comparison_if_needed(self):
        if self.image1 and self.image2: self.update_comparison()

    def load_image(self, image_number):
        file_name, _ = QFileDialog.getOpenFileName(self, tr(f"Select Image {image_number}", self.current_language), "", "Image Files (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)")
        if file_name: self._load_image_from_path(file_name, image_number)

    def _load_image_from_path(self, file_path, image_number):
        try:
            with Image.open(file_path) as img: temp_image = img.copy().convert('RGBA')
            if image_number == 1: self.original_image1 = temp_image; self.image1_path = file_path; self.image1 = None; self.edit_name1.setText(os.path.basename(file_path))
            else: self.original_image2 = temp_image; self.image2_path = file_path; self.image2 = None; self.edit_name2.setText(os.path.basename(file_path))
            # update_file_names is implicitly called by edit_nameX.setText signals
            if self.original_image1 and self.original_image2: resize_images_processor(self); self.update_comparison()
            else: self.image_label.clear(); self.result_image = None; self.image1 = None; self.image2 = None
        except Exception as e:
            QMessageBox.warning(self, tr("Error", self.current_language), f"{tr('Failed to load image:', self.current_language)}\n{file_path}\n{e}")
            if image_number == 1: self.original_image1, self.image1_path, self.image1 = None, None, None; self.edit_name1.clear()
            else: self.original_image2, self.image2_path, self.image2 = None, None, None; self.edit_name2.clear()
            self.image_label.clear(); self.result_image = None; self.update_file_names() # Explicit call needed on error/clear

    def swap_images(self):
        self.original_image1, self.original_image2 = self.original_image2, self.original_image1
        self.image1_path, self.image2_path = self.image2_path, self.image1_path
        self.image1 = None; self.image2 = None # Reset work copies
        # Block signals temporarily while swapping text to avoid extra updates
        self.edit_name1.blockSignals(True); self.edit_name2.blockSignals(True)
        name1 = self.edit_name1.text(); name2 = self.edit_name2.text()
        self.edit_name1.setText(name2); self.edit_name2.setText(name1)
        self.edit_name1.blockSignals(False); self.edit_name2.blockSignals(False)
        self.update_file_names() # Call once after swapping text
        # self.check_name_lengths() # update_file_names calls this
        if self.original_image1 and self.original_image2: resize_images_processor(self); self.update_comparison_if_needed()
        else: self.image_label.clear(); self.result_image = None

    def _save_result_with_error_handling(self):
        try:
            if not self.original_image1 or not self.original_image2: QMessageBox.warning(self, tr("Warning", self.current_language), tr("Please load both images first.", self.current_language)); return
            save_result_processor(self)
        except Exception as e:
            QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{str(e)}")

    def _update_magnifier_position_by_keys(self):
        target_pos_changed = visual_pos_moved = target_spacing_changed = visual_spacing_moved = False
        epsilon = 1e-6; delta_x = delta_y = delta_spacing = 0.0 # Init deltas

        if self.active_keys:
            current_elapsed = self.movement_elapsed_timer.elapsed(); delta_time_ms = current_elapsed - self.last_update_elapsed
            if delta_time_ms <= 0: delta_time_ms = self.movement_timer.interval()
            delta_time_sec = delta_time_ms / 1000.0; self.last_update_elapsed = current_elapsed
            dx_dir = (Qt.Key.Key_D in self.active_keys) - (Qt.Key.Key_A in self.active_keys)
            dy_dir = (Qt.Key.Key_S in self.active_keys) - (Qt.Key.Key_W in self.active_keys)
            d_spacing_dir = (Qt.Key.Key_E in self.active_keys) - (Qt.Key.Key_Q in self.active_keys)
            length_sq = dx_dir*dx_dir + dy_dir*dy_dir
            if length_sq > 1.0 + epsilon: inv_length = 1.0/math.sqrt(length_sq); dx_dir *= inv_length; dy_dir *= inv_length
            raw_dx = dx_dir * self.movement_speed_per_sec * delta_time_sec; raw_dy = dy_dir * self.movement_speed_per_sec * delta_time_sec
            raw_ds = d_spacing_dir * self.spacing_speed_per_sec * delta_time_sec
            clamped_dx = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_dx))
            clamped_dy = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_dy))
            clamped_ds = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_ds))

            if abs(clamped_dx) > epsilon or abs(clamped_dy) > epsilon:
                 if self.freeze_magnifier and self.frozen_magnifier_position_relative:
                     px_w, px_h = self.pixmap_width, self.pixmap_height; dx_rel = clamped_dx / px_w if px_w > 0 else 0; dy_rel = clamped_dy / px_h if px_h > 0 else 0
                     new_x = max(0.0, min(1.0, self.frozen_magnifier_position_relative.x() + dx_rel)); new_y = max(0.0, min(1.0, self.frozen_magnifier_position_relative.y() + dy_rel))
                     if not math.isclose(new_x, self.frozen_magnifier_position_relative.x(), abs_tol=epsilon) or not math.isclose(new_y, self.frozen_magnifier_position_relative.y(), abs_tol=epsilon):
                         self.frozen_magnifier_position_relative.setX(new_x); self.frozen_magnifier_position_relative.setY(new_y); target_pos_changed = True
                 elif not self.freeze_magnifier: self.magnifier_offset_float.setX(self.magnifier_offset_float.x() + clamped_dx); self.magnifier_offset_float.setY(self.magnifier_offset_float.y() + clamped_dy); target_pos_changed = True

            if abs(clamped_ds) > epsilon:
                new_target_spacing = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float + clamped_ds)
                if not math.isclose(new_target_spacing, self._magnifier_spacing_float, abs_tol=epsilon): self._magnifier_spacing_float = new_target_spacing; target_spacing_changed = True

        # --- Interpolation ---
        if not self.freeze_magnifier:
            delta_x = self.magnifier_offset_float.x() - self.magnifier_offset_float_visual.x(); delta_y = self.magnifier_offset_float.y() - self.magnifier_offset_float_visual.y()
            if abs(delta_x) < self.lerp_stop_threshold and abs(delta_y) < self.lerp_stop_threshold:
                if not math.isclose(self.magnifier_offset_float_visual.x(), self.magnifier_offset_float.x()) or not math.isclose(self.magnifier_offset_float_visual.y(), self.magnifier_offset_float.y()):
                    self.magnifier_offset_float_visual.setX(self.magnifier_offset_float.x()); self.magnifier_offset_float_visual.setY(self.magnifier_offset_float.y()); visual_pos_moved = True
            else: self.magnifier_offset_float_visual.setX(self.magnifier_offset_float_visual.x() + delta_x * self.smoothing_factor_pos); self.magnifier_offset_float_visual.setY(self.magnifier_offset_float_visual.y() + delta_y * self.smoothing_factor_pos); visual_pos_moved = True

        target_spacing_clamped = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float)
        delta_spacing = target_spacing_clamped - self._magnifier_spacing_float_visual
        if abs(delta_spacing) < self.lerp_stop_threshold:
             if not math.isclose(self._magnifier_spacing_float_visual, target_spacing_clamped): self._magnifier_spacing_float_visual = target_spacing_clamped; visual_spacing_moved = True
        else: new_visual_spacing = self._magnifier_spacing_float_visual + delta_spacing * self.smoothing_factor_spacing; self._magnifier_spacing_float_visual = max(self.MIN_MAGNIFIER_SPACING, new_visual_spacing); visual_spacing_moved = True

        # --- Update state & redraw ---
        needs_redraw = visual_pos_moved or visual_spacing_moved or (target_pos_changed and self.freeze_magnifier)
        if needs_redraw:
            new_offset_pixels = QPoint(round(self.magnifier_offset_float_visual.x()), round(self.magnifier_offset_float_visual.y()))
            new_spacing_int = round(self._magnifier_spacing_float_visual)
            if not self.freeze_magnifier and self.magnifier_offset_pixels != new_offset_pixels: self.magnifier_offset_pixels = new_offset_pixels
            if self.magnifier_spacing != new_spacing_int: self.magnifier_spacing = new_spacing_int
            if not self.resize_in_progress: self.update_comparison()

        # --- Stop timer ---
        if not self.active_keys:
            pos_is_close = (self.freeze_magnifier or (abs(delta_x) < self.lerp_stop_threshold and abs(delta_y) < self.lerp_stop_threshold))
            spacing_is_close = abs(target_spacing_clamped - self._magnifier_spacing_float_visual) < self.lerp_stop_threshold
            if pos_is_close and spacing_is_close:
                self.movement_timer.stop()
                # Final sync & save
                final_offset_x_f = self.magnifier_offset_float.x(); final_offset_y_f = self.magnifier_offset_float.y(); final_spacing_f_clamped = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float)
                self.magnifier_offset_float_visual.setX(final_offset_x_f); self.magnifier_offset_float_visual.setY(final_offset_y_f); self._magnifier_spacing_float_visual = final_spacing_f_clamped
                final_offset_pixels = QPoint(round(final_offset_x_f), round(final_offset_y_f)); final_spacing_int_clamped = round(final_spacing_f_clamped)
                save_offset = self.magnifier_offset_pixels != final_offset_pixels; save_spacing = self.magnifier_spacing != final_spacing_int_clamped
                if save_offset: self.magnifier_offset_pixels = final_offset_pixels; self.save_setting("magnifier_offset_pixels_x", final_offset_x_f); self.save_setting("magnifier_offset_pixels_y", final_offset_y_f)
                if save_spacing: self.magnifier_spacing = final_spacing_int_clamped; self.save_setting("magnifier_spacing", final_spacing_int_clamped)

    # --- UI Control Callbacks / Toggles ---
    def toggle_orientation(self, state): self.is_horizontal = state == Qt.CheckState.Checked.value; self.update_file_names(); self.update_comparison_if_needed()
    def toggle_magnifier(self, state):
        self.use_magnifier = state == Qt.CheckState.Checked.value; visible = self.use_magnifier
        if hasattr(self, 'slider_size'): self.slider_size.setVisible(visible)
        if hasattr(self, 'slider_capture'): self.slider_capture.setVisible(visible)
        if hasattr(self, 'label_magnifier_size'): self.label_magnifier_size.setVisible(visible)
        if hasattr(self, 'label_capture_size'): self.label_capture_size.setVisible(visible)
        if hasattr(self, 'freeze_button'): self.freeze_button.setEnabled(visible)
        if hasattr(self, 'slider_speed'): self.slider_speed.setVisible(visible)
        if hasattr(self, 'label_movement_speed'): self.label_movement_speed.setVisible(visible)
        if not self.use_magnifier: self.active_keys.clear(); self.movement_timer.stop();
        if self.freeze_magnifier and not self.use_magnifier:
             if hasattr(self, 'freeze_button'): self.freeze_button.setChecked(False) # Will trigger unfreeze logic
             else: self.freeze_magnifier = False; self.frozen_magnifier_position_relative = None
        self.update_comparison_if_needed()

    def toggle_freeze_magnifier(self, state):
        new_freeze_state = state == Qt.CheckState.Checked.value
        if new_freeze_state:
            if self.use_magnifier and self.original_image1 and self.original_image2:
                was_frozen = self.freeze_magnifier; self.freeze_magnifier = False # Temp unfreeze
                _, __, magnifier_pos_orig_current = get_original_coords(self) # Use index 2 for magnifier center
                self.freeze_magnifier = new_freeze_state # Restore intended
                if magnifier_pos_orig_current and self.original_image1.size[0] > 0:
                    w, h = self.original_image1.size
                    self.frozen_magnifier_position_relative = QPointF(magnifier_pos_orig_current.x() / w, magnifier_pos_orig_current.y() / h)
                    self.freeze_magnifier = True;
                else: self.frozen_magnifier_position_relative = None; self.freeze_magnifier = False; self.freeze_button.setChecked(False);
            else: self.frozen_magnifier_position_relative = None; self.freeze_magnifier = False; self.freeze_button.setChecked(False);
        else: # Unfreezing
            self.freeze_magnifier = False
            if self.frozen_magnifier_position_relative and self.original_image1:
                w, h = self.original_image1.size; frozen_x = self.frozen_magnifier_position_relative.x() * w; frozen_y = self.frozen_magnifier_position_relative.y() * h
                cap_orig1, _, __ = get_original_coords(self) # Use index 0 for capture 1 center
                if cap_orig1:
                    off_x_orig = frozen_x - cap_orig1.x(); off_y_orig = frozen_y - cap_orig1.y()
                    sw, sh = get_scaled_pixmap_dimensions(self); sx = sw / w if w > 0 else 0; sy = sh / h if h > 0 else 0
                    off_x_scaled = off_x_orig * sx; off_y_scaled = off_y_orig * sy
                    self.magnifier_offset_float.setX(off_x_scaled); self.magnifier_offset_float.setY(off_y_scaled)
                    self.magnifier_offset_float_visual.setX(off_x_scaled); self.magnifier_offset_float_visual.setY(off_y_scaled) # Sync visual
                    self.magnifier_offset_pixels = QPoint(round(off_x_scaled), round(off_y_scaled)) # Sync int
                    cur_vis_space = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float_visual)
                    self._magnifier_spacing_float = cur_vis_space # Sync target space
                    self.magnifier_spacing = round(cur_vis_space) # Sync int space
                    if not self.movement_timer.isActive(): self.movement_elapsed_timer.start(); self.last_update_elapsed = self.movement_elapsed_timer.elapsed(); self.movement_timer.start()
            self.frozen_magnifier_position_relative = None
        self.update_comparison_if_needed()

    def update_magnifier_size(self, value): self.magnifier_size = value; self.save_setting("magnifier_size", value); self.update_comparison_if_needed()
    def update_capture_size(self, value): self.capture_size = value; self.save_setting("capture_size", value); self.update_comparison_if_needed()
    def update_movement_speed(self, value): self.movement_speed_per_sec = value; self.save_setting("movement_speed_per_sec", value); self.slider_speed.setToolTip(f"{value} {tr('px/sec', self.current_language)}")

    def toggle_edit_layout_visibility(self, checked):
        if not hasattr(self, 'edit_layout'): return
        is_visible = bool(checked)
        for i in range(self.edit_layout.count()):
            item = self.edit_layout.itemAt(i)
            if item and item.widget(): item.widget().setVisible(is_visible)
        self.update_minimum_window_size()
        if is_visible: self.update_comparison_if_needed()

    def _open_color_dialog(self):
        color = QColorDialog.getColor(self.file_name_color, self, tr("Select Filename Color", self.current_language), options=QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid(): self.file_name_color = color; self._update_color_button_tooltip(); self.save_setting("filename_color", color.name(QColor.NameFormat.HexArgb)); self.update_comparison_if_needed()

    def _update_color_button_tooltip(self):
        if hasattr(self, 'btn_color_picker'): self.btn_color_picker.setToolTip(f"{tr('Change Filename Color', self.current_language)}\n{tr('Current:', self.current_language)} {self.file_name_color.name(QColor.NameFormat.HexArgb)}")

    # --- Settings & Persistence ---
    def save_setting(self, key, value):
        try: self.settings.setValue(key, value)
        except Exception as e: pass
    def _save_file_names_state(self, checked): self.save_setting("include_file_names", bool(checked))

    # --- Internationalization & Help ---
    def change_language(self, language):
        if language not in ['en', 'ru', 'zh']: language = 'en'
        self.current_language = language; self.update_translations(); self.update_file_names(); self.update_language_checkboxes(); self.save_setting("language", language)
        if hasattr(self, 'length_warning_label') and self.length_warning_label.isVisible(): self.check_name_lengths()

    def update_translations(self):
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        if hasattr(self, 'btn_image1'): self.btn_image1.setText(tr('Select Image 1', self.current_language))
        if hasattr(self, 'btn_image2'): self.btn_image2.setText(tr('Select Image 2', self.current_language))
        if hasattr(self, 'btn_swap'): self.btn_swap.setToolTip(tr('Swap Images', self.current_language))
        if hasattr(self, 'btn_save'): self.btn_save.setText(tr('Save Result', self.current_language))
        if hasattr(self, 'checkbox_horizontal'): self.checkbox_horizontal.setText(tr('Horizontal Split', self.current_language))
        if hasattr(self, 'checkbox_magnifier'): self.checkbox_magnifier.setText(tr('Use Magnifier', self.current_language))
        if hasattr(self, 'freeze_button'): self.freeze_button.setText(tr('Freeze Magnifier', self.current_language))
        if hasattr(self, 'checkbox_file_names'): self.checkbox_file_names.setText(tr('Include file names in saved image', self.current_language))
        if hasattr(self, 'label_magnifier_size'): self.label_magnifier_size.setText(tr("Magnifier Size:", self.current_language))
        if hasattr(self, 'label_capture_size'): self.label_capture_size.setText(tr("Capture Size:", self.current_language))
        if hasattr(self, 'label_movement_speed'): self.label_movement_speed.setText(tr("Move Speed:", self.current_language))
        if hasattr(self, 'label_edit_name1'): self.label_edit_name1.setText(tr("Name 1:", self.current_language))
        if hasattr(self, 'edit_name1'): self.edit_name1.setPlaceholderText(tr("Edit Image 1 Name", self.current_language))
        if hasattr(self, 'label_edit_name2'): self.label_edit_name2.setText(tr("Name 2:", self.current_language))
        if hasattr(self, 'edit_name2'): self.edit_name2.setPlaceholderText(tr("Edit Image 2 Name", self.current_language))
        if hasattr(self, 'label_edit_font_size'): self.label_edit_font_size.setText(tr("Font Size (%):", self.current_language))
        if hasattr(self, 'slider_speed'): self.slider_speed.setToolTip(f"{self.movement_speed_per_sec} {tr('px/sec', self.current_language)}")
        if hasattr(self, 'slider_size'): self.slider_size.setToolTip(f"{self.magnifier_size} px")
        if hasattr(self, 'slider_capture'): self.slider_capture.setToolTip(f"{self.capture_size} px")
        self._update_color_button_tooltip()
        if hasattr(self, 'drag_overlay1') and self.drag_overlay1.isVisible(): self.drag_overlay1.setText(tr("Drop Image 1 Here", self.current_language))
        if hasattr(self, 'drag_overlay2') and self.drag_overlay2.isVisible(): self.drag_overlay2.setText(tr("Drop Image 2 Here", self.current_language))
        if hasattr(self, 'length_warning_label') and self.length_warning_label.isVisible(): self.check_name_lengths() # Re-check warning on language change

    def _on_language_changed(self, language):
        if self.current_language == language:
             cb = getattr(self, f'lang_{language}', None)
             if cb and not cb.isChecked(): self._block_language_checkbox_signals(True); cb.setChecked(True); self._block_language_checkbox_signals(False)
             return
        self._block_language_checkbox_signals(True)
        if hasattr(self, 'lang_en'): self.lang_en.setChecked(language == 'en')
        if hasattr(self, 'lang_ru'): self.lang_ru.setChecked(language == 'ru')
        if hasattr(self, 'lang_zh'): self.lang_zh.setChecked(language == 'zh')
        self.change_language(language)
        self._block_language_checkbox_signals(False)

    def _block_language_checkbox_signals(self, block):
        if hasattr(self, 'lang_en'): self.lang_en.blockSignals(block)
        if hasattr(self, 'lang_ru'): self.lang_ru.blockSignals(block)
        if hasattr(self, 'lang_zh'): self.lang_zh.blockSignals(block)

    def update_language_checkboxes(self):
        self._block_language_checkbox_signals(True)
        if hasattr(self, 'lang_en'): self.lang_en.setChecked(self.current_language == 'en')
        if hasattr(self, 'lang_ru'): self.lang_ru.setChecked(self.current_language == 'ru')
        if hasattr(self, 'lang_zh'): self.lang_zh.setChecked(self.current_language == 'zh')
        self._block_language_checkbox_signals(False)

    def _show_help_dialog(self):
        help_text = tr("""
**General Usage:**
- Load two images using the 'Select Image' buttons or by dragging and dropping files onto the corresponding left/right drop zones.
- The images will be resized to fit the window while maintaining aspect ratio.
- A comparison view is shown in the main area.

**Split Line Mode (Default):**
- A vertical (or horizontal) line splits the view between Image 1 and Image 2.
- **Click and drag** the mouse over the image area to move the split line.
- Check the 'Horizontal Split' box to change the split orientation.

**Magnifier Mode:**
- Check the 'Use Magnifier' box to activate this mode.
- A magnified view of a small area from both images will be displayed side-by-side.
- **Click and drag** the mouse over the main image area to select the area to be magnified (the 'capture' area).
- Use the **W, A, S, D keys** to smoothly move the magnified views relative to the capture area.
- Use the **Q and E keys** to adjust the spacing between the two magnified views.
- The 'Magnifier Size' slider controls the display size of each magnified view.
- The 'Capture Size' slider controls the size of the source area being magnified.
- The 'Move Speed' slider controls the speed of W/A/S/D movement.
- Check the **'Freeze Magnifier'** box to lock the position being magnified. While frozen:
    - Clicking/dragging on the main image moves the *frozen point*.
    - W/A/S/D keys move the *frozen point*.
    - Q/E keys still adjust spacing.
    - Unchecking 'Freeze Magnifier' restores the relative offset based on the last frozen point.

**Saving:**
- Click 'Save Result' to save the current comparison view (what you see in the main area, including the split line or magnifier) as a single image file.
- Check 'Include file names' to optionally render the specified file names onto the saved image.
    - You can edit the names in the text boxes that appear.
    - Adjust the font size using the 'Font Size (%)' slider.
    - Click the color wheel button to change the text color.
    - A warning appears if names are too long; click the warning to adjust the length limit.

**Other Controls:**
- 'Swap Images' button: Swaps Image 1 and Image 2.
- Language Flags/Checkboxes: Change the interface language (English, Russian, Chinese).
- '?': Shows this help dialog.

**Settings:**
- Window size, language, magnifier/capture sizes, offsets, speeds, and filename options are saved automatically when closing the application.
        """, self.current_language)
        QMessageBox.information(self, tr("Help", self.current_language), help_text)

    # --- Helper Methods ---
    def _update_split_or_capture_position(self, cursor_pos_f: QPointF):
        if self.pixmap_width <= 0 or self.pixmap_height <= 0:
            return

        cursor_pos = cursor_pos_f.toPoint()
        label_rect = self.image_label.rect()
        x_offset = (label_rect.width() - self.pixmap_width)//2
        y_offset = (label_rect.height() - self.pixmap_height)//2

        raw_x = cursor_pos.x() - x_offset
        raw_y = cursor_pos.y() - y_offset
        rel_x = max(0.0, min(1.0, raw_x / self.pixmap_width if self.pixmap_width > 0 else 0))
        rel_y = max(0.0, min(1.0, raw_y / self.pixmap_height if self.pixmap_height > 0 else 0))

        needs_update = False
        if not self.use_magnifier:
            new_split = rel_x if not self.is_horizontal else rel_y
            if not math.isclose(self.split_position, new_split, abs_tol=1e-4):
                self.split_position = new_split
                needs_update = True
        else:
            new_rel = QPointF(rel_x, rel_y)
            current_rel = self.capture_position_relative
            if not math.isclose(current_rel.x(), new_rel.x(), abs_tol=1e-4) or not math.isclose(current_rel.y(), new_rel.y(), abs_tol=1e-4):
                self.capture_position_relative = new_rel
                needs_update = True

        if needs_update:
            self.update_comparison()

    # --- MODIFIED update_file_names ---
    def update_file_names(self):
        """Updates the file name labels in the UI, truncating based on max_name_length."""
        name1 = (hasattr(self, 'edit_name1') and self.edit_name1.text()) or (os.path.basename(self.image1_path) if self.image1_path else tr("Image 1", self.current_language))
        name2 = (hasattr(self, 'edit_name2') and self.edit_name2.text()) or (os.path.basename(self.image2_path) if self.image2_path else tr("Image 2", self.current_language))

        # Use the current max_name_length for UI display truncation
        max_len = self.max_name_length
        dn1 = (name1[:max_len-3]+"...") if len(name1) > max_len else name1
        dn2 = (name2[:max_len-3]+"...") if len(name2) > max_len else name2

        if hasattr(self, 'file_name_label1') and hasattr(self, 'file_name_label2'):
            if not self.is_horizontal:
                self.file_name_label1.setText(f"{tr('Left',self.current_language)}: {dn1}")
                self.file_name_label2.setText(f"{tr('Right',self.current_language)}: {dn2}")
            else:
                self.file_name_label1.setText(f"{tr('Top',self.current_language)}: {dn1}")
                self.file_name_label2.setText(f"{tr('Bottom',self.current_language)}: {dn2}")

        # Update the length warning based on the *full* names
        self.check_name_lengths()
    # --- END MODIFICATION ---

    def check_name_lengths(self):
        """Checks full name lengths against the limit and updates the warning label."""
        if not hasattr(self, 'length_warning_label'): return
        # Get the full, untruncated names for checking
        name1 = (hasattr(self, 'edit_name1') and self.edit_name1.text()) or (os.path.basename(self.image1_path) if self.image1_path else "")
        name2 = (hasattr(self, 'edit_name2') and self.edit_name2.text()) or (os.path.basename(self.image2_path) if self.image2_path else "")
        len1, len2 = len(name1), len(name2)
        if len1 > self.max_name_length or len2 > self.max_name_length:
            longest = max(len1, len2)
            tooltip = tr("One or both names exceed the current limit of {max_length} characters (longest is {length}).\nClick here to change the limit.", self.current_language).format(length=longest, max_length=self.max_name_length)
            self.length_warning_label.setText(tr("Reduce Length!", self.current_language)); self.length_warning_label.setToolTip(tooltip); self.length_warning_label.setVisible(True)
        else: self.length_warning_label.setVisible(False); self.length_warning_label.setToolTip("")

    # --- MODIFIED _edit_length_dialog ---
    def _edit_length_dialog(self, event):
        new_limit, ok = QInputDialog.getInt(self, tr("Edit Length Limit", self.current_language), tr("Enter new maximum length (10-100):", self.current_language), value=self.max_name_length, min=10, max=100)
        if ok:
            self.max_name_length = new_limit
            self.save_setting("max_name_length", new_limit)
            self.update_file_names() # Call this to update labels and warning
    # --- END MODIFICATION ---

    def _create_flag_icon(self, base64_data):
        try: pixmap = QPixmap(); pixmap.loadFromData(base64.b64decode(base64_data)); return QIcon(pixmap)
        except Exception as e:
            return QIcon()

    def update_minimum_window_size(self):
        min_w, min_h = 400, 0; layout = self.layout()
        if not layout: return
        for i in range(layout.count()):
            item = layout.itemAt(i); h = 0; spacing = layout.spacing() if layout.spacing() > -1 else 10
            if item.widget() and item.widget().isVisible():
                widget = item.widget(); h = (widget.minimumSizeHint().height() if widget == self.image_label else widget.sizeHint().height()) + spacing
            elif item.layout():
                sub_layout = item.layout(); sub_visible = False
                for j in range(sub_layout.count()):
                    sub_item = sub_layout.itemAt(j)
                    if sub_item and sub_item.widget() and sub_item.widget().isVisible(): sub_visible = True; break
                if sub_visible: h = sub_layout.sizeHint().height() + spacing
            min_h += h
        min_h += 10 # Bottom padding
        try: self.setMinimumSize(min_w, min_h)
        except Exception as e: pass

    def _update_drag_overlays(self):
        if not hasattr(self, 'drag_overlay1') or not hasattr(self, 'image_label'): return
        g = self.image_label.geometry(); m = 10; w = g.width()//2-m-m//2; h = g.height()-2*m; w=max(10,w); h=max(10,h)
        self.drag_overlay1.setGeometry(g.x()+m, g.y()+m, w, h)
        self.drag_overlay2.setGeometry(g.x()+g.width()//2+m//2, g.y()+m, w, h)

    def _is_in_left_area(self, pos: QPoint):
        if not hasattr(self, 'image_label'): return True
        g = self.image_label.geometry(); return pos.x() < (g.x() + g.width() // 2)

# --- Main Execution ---
if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Use placeholder files from a subdirectory if they don't exist in the main dir
    placeholder_dir = "placeholders"
    os.makedirs(placeholder_dir, exist_ok=True)
    placeholder_files = {
        'translations.py': os.path.join(placeholder_dir, 'translations.py'),
        'flag_icons.py': os.path.join(placeholder_dir, 'flag_icons.py'),
        'image_processing.py': os.path.join(placeholder_dir, 'image_processing.py'),
        'clickable_label.py': os.path.join(placeholder_dir, 'clickable_label.py'),
        'SourceSans3-Regular.ttf': os.path.join(placeholder_dir, 'SourceSans3-Regular.ttf') # Add font
    }

    needs_reload = False
    for main_path, placeholder_path in placeholder_files.items():
        if not os.path.exists(main_path):
            needs_reload = True
            # Create placeholder content
            content = ""
            if main_path == 'translations.py':
                content = "def tr(text, lang='en', *args, **kwargs):\n    return text # Basic placeholder\n"
            elif main_path == 'flag_icons.py':
                content = "FLAG_ICONS = {}\n"
            elif main_path == 'image_processing.py':
                 content = ("from PyQt6.QtCore import QPoint, QPointF\n" # Add necessary imports for placeholders
                           "from PIL import Image\n"
                           "def resize_images_processor(app): pass\n"
                           "def update_comparison_processor(app): pass\n"
                           "def save_result_processor(app): pass\n"
                           "def display_result_processor(app): pass\n" # Add this one
                           "def get_scaled_pixmap_dimensions(app): return 0, 0\n"
                           "def get_original_coords(app): return None, None, None\n" # Expects 3 return values now
                           "def draw_file_names_on_image(self, draw, image, split_pos_abs, orig_width, orig_height, line_width, line_height, text_color_tuple): pass\n")
            elif main_path == 'clickable_label.py':
                content = ("from PyQt6.QtWidgets import QLabel\n"
                           "from PyQt6.QtCore import pyqtSignal, Qt\n"
                           "class ClickableLabel(QLabel):\n"
                           "    mousePressed = pyqtSignal(object)\n"
                           "    mouseMoved = pyqtSignal(object)\n"
                           "    mouseReleased = pyqtSignal(object)\n"
                           "    def __init__(self, parent=None):\n"
                           "        super().__init__(parent)\n"
                           "        self.setMouseTracking(True)\n"
                           "    def mousePressEvent(self, event):\n"
                           "        self.mousePressed.emit(event)\n"
                           "        super().mousePressEvent(event)\n"
                           "    def mouseMoveEvent(self, event):\n"
                           "        self.mouseMoved.emit(event)\n"
                           "        super().mouseMoveEvent(event)\n"
                           "    def mouseReleaseEvent(self, event):\n"
                           "        self.mouseReleased.emit(event)\n"
                           "        super().mouseReleaseEvent(event)\n")
            elif main_path == 'SourceSans3-Regular.ttf':
                # Create an empty file as a placeholder, actual font needed separately
                content = ""

            # Write the placeholder file
            try:
                with open(placeholder_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                # Copy placeholder to main directory
                import shutil
                shutil.copy2(placeholder_path, main_path)
                print(f"Created placeholder file: {main_path}")
            except Exception as e:
                print(f"Error creating placeholder {main_path}: {e}")


    # Dynamically import or reload modules
    import importlib
    modules_to_load = ['translations', 'flag_icons', 'image_processing', 'clickable_label']
    loaded_modules = {}

    for mod_name in modules_to_load:
        try:
            if mod_name in sys.modules and needs_reload:
                loaded_modules[mod_name] = importlib.reload(sys.modules[mod_name])
                print(f"Reloaded module: {mod_name}")
            else:
                loaded_modules[mod_name] = importlib.import_module(mod_name)
                print(f"Imported module: {mod_name}")
        except ImportError as e:
            print(f"Error importing/reloading module {mod_name}: {e}")
            # Attempt to load placeholder functions/classes directly if import fails
            if mod_name == 'translations':
                def tr(text, lang='en', *args, **kwargs): return text
                loaded_modules['translations'] = type('module', (object,), {'tr': tr})()
            elif mod_name == 'flag_icons':
                loaded_modules['flag_icons'] = type('module', (object,), {'FLAG_ICONS': {}})()
            elif mod_name == 'image_processing':
                 def _placeholder_func(*args, **kwargs): pass
                 def _placeholder_coords(*args, **kwargs): return None, None, None
                 def _placeholder_dims(*args, **kwargs): return 0,0
                 loaded_modules['image_processing'] = type('module', (object,), {
                    'resize_images_processor': _placeholder_func,
                    'update_comparison_processor': _placeholder_func,
                    'save_result_processor': _placeholder_func,
                    'display_result_processor': _placeholder_func,
                    'get_scaled_pixmap_dimensions': _placeholder_dims,
                    'get_original_coords': _placeholder_coords,
                    'draw_file_names_on_image': _placeholder_func,
                 })()
            elif mod_name == 'clickable_label':
                 from PyQt6.QtWidgets import QLabel
                 from PyQt6.QtCore import pyqtSignal
                 class ClickableLabelPlaceholder(QLabel):
                     mousePressed = pyqtSignal(object)
                     mouseMoved = pyqtSignal(object)
                     mouseReleased = pyqtSignal(object)
                     def __init__(self, parent=None): super().__init__(parent)
                     def mousePressEvent(self, event): self.mousePressed.emit(event)
                     def mouseMoveEvent(self, event): self.mouseMoved.emit(event)
                     def mouseReleaseEvent(self, event): self.mouseReleased.emit(event)
                 loaded_modules['clickable_label'] = type('module', (object,), {'ClickableLabel': ClickableLabelPlaceholder})()

    # Make loaded modules/functions available globally in this script's context
    # This is a bit hacky but necessary since the class definition uses them directly
    tr = loaded_modules['translations'].tr
    FLAG_ICONS = loaded_modules['flag_icons'].FLAG_ICONS
    resize_images_processor = loaded_modules['image_processing'].resize_images_processor
    update_comparison_processor = loaded_modules['image_processing'].update_comparison_processor
    save_result_processor = loaded_modules['image_processing'].save_result_processor
    get_scaled_pixmap_dimensions = loaded_modules['image_processing'].get_scaled_pixmap_dimensions
    get_original_coords = loaded_modules['image_processing'].get_original_coords
    ClickableLabel = loaded_modules['clickable_label'].ClickableLabel


    window = ImageComparisonApp()
    window.show()
    sys.exit(app.exec())
