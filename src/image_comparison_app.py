import base64
import os
import math
import sys
import importlib
import traceback
from PIL import Image, UnidentifiedImageError
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel, QFileDialog, QSizePolicy, QMessageBox, QLineEdit, QDialog, QApplication, QColorDialog, QComboBox, QStyle
from PyQt6.QtGui import QPixmap, QIcon, QColor, QPainter, QBrush, QImage
from PyQt6.QtCore import Qt, QPoint, QTimer, QPointF, QEvent, QSize, QSettings, QLocale, QElapsedTimer, QRectF, QByteArray
try:
    from settings_dialog import SettingsDialog
    settings_dialog_available = True
except ImportError:
    print('Warning: settings_dialog.py not found. Settings button will be disabled.')
    SettingsDialog = None
    settings_dialog_available = False

def load_module(mod_name):
    try:
        module = importlib.import_module(mod_name)
        return module
    except ImportError as e:
        print(f'Error: Could not import module {mod_name}. File might be missing or contain errors: {e}')
        return None
    except Exception as e:
        print(f'Unexpected error importing module {mod_name}: {e}')
        traceback.print_exc()
        return None
translations_mod = load_module('translations')
flag_icons_mod = load_module('icons')
image_processing_mod = load_module('image_processing')
clickable_label_mod = load_module('clickable_label')
if not all([translations_mod, flag_icons_mod, image_processing_mod, clickable_label_mod]):
    missing_modules = [name for name, mod in [('translations', translations_mod), ('icons', flag_icons_mod), ('image_processing', image_processing_mod), ('clickable_label', clickable_label_mod)] if mod is None]
    error_message = f"Critical error: Could not load required Python modules: {', '.join(missing_modules)}.\nCheck console output and ensure files exist and are error-free.\nExiting."
    print(error_message)
    try:
        temp_app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, 'Startup Error', error_message)
    except Exception as e:
        print(f'GUI Error message failed: {e}')
        pass
    sys.exit(1)
tr = getattr(translations_mod, 'tr', lambda text, lang='en', *args, **kwargs: text)
FLAG_ICONS = getattr(flag_icons_mod, 'FLAG_ICONS', {})
resize_images_processor = getattr(image_processing_mod, 'resize_images_processor', lambda app: print('Error: resize_images_processor not loaded'))
display_result_processor = getattr(image_processing_mod, 'display_result_processor', lambda app: print('Error: display_result_processor not loaded'))
save_result_processor = getattr(image_processing_mod, 'save_result_processor', lambda app: print('Error: save_result_processor not loaded'))
get_scaled_pixmap_dimensions = getattr(image_processing_mod, 'get_scaled_pixmap_dimensions', lambda app: (0, 0))
get_original_coords = getattr(image_processing_mod, 'get_original_coords', lambda app, *args: (None,) * 7)
ClickableLabel = getattr(clickable_label_mod, 'ClickableLabel', QLabel)
script_dir = os.path.dirname(os.path.abspath(__file__))
font_file_name = 'SourceSans3-Regular.ttf'
font_file = os.path.join(script_dir, 'font', font_file_name)
BASE_PIXEL_SPEED_FROZEN = 150.0
BASE_RELATIVE_SPEED_UNFROZEN = 0.3
if not os.path.exists(font_file):
    print(f'WARNING: Font file not found at expected path: {font_file}. Will rely on system default.')

class ImageComparisonApp(QWidget):
    MIN_NAME_LENGTH_LIMIT = 10
    MAX_NAME_LENGTH_LIMIT = 150
    DEFAULT_MAGNIFIER_SIZE_RELATIVE = 0.2
    DEFAULT_CAPTURE_SIZE_RELATIVE = 0.1
    DEFAULT_CAPTURE_POS_RELATIVE = QPointF(0.5, 0.5)
    DEFAULT_MAGNIFIER_OFFSET_RELATIVE = QPointF(0.0, -0.5)
    DEFAULT_MAGNIFIER_SPACING_RELATIVE = 0.1
    DEFAULT_JPEG_QUALITY = 93

    def __init__(self):
        super().__init__()
        self._determine_font_path()
        self.settings = QSettings('MyCompany', 'ImageComparisonApp')
        self._load_settings()
        self._init_state()
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        self._init_timers()
        self._build_ui()
        self._apply_initial_settings_to_ui()
        self._connect_signals()
        self._restore_geometry()
        self._update_combobox(1)
        self._update_combobox(2)
        QTimer.singleShot(0, self._perform_initial_image_setup)

    def _determine_font_path(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.font_file_name = 'SourceSans3-Regular.ttf'
        self.font_path_absolute = None
        flatpak_exists = False
        relative_exists = False
        ip_fallback_direct_exists = False
        ip_fallback_subdir_exists = False

        flatpak_font_path = f'/app/share/fonts/truetype/{self.font_file_name}'
        try:
            flatpak_exists = os.path.exists(flatpak_font_path)
            if flatpak_exists:
                self.font_path_absolute = flatpak_font_path
                return
        except Exception:
            flatpak_exists = False

        expected_font_path = os.path.join(self.script_dir, 'font', self.font_file_name)
        try:
            relative_exists = os.path.exists(expected_font_path)
            if relative_exists:
                self.font_path_absolute = expected_font_path
                return
        except Exception:
            relative_exists = False

        fallback_path_direct = None
        fallback_path_subdir = None
        try:
            if image_processing_mod and hasattr(image_processing_mod, '__file__') and image_processing_mod.__file__:
                ip_module_path = os.path.abspath(image_processing_mod.__file__)
                ip_module_dir = os.path.dirname(ip_module_path)

                fallback_path_direct = os.path.join(ip_module_dir, self.font_file_name)
                try:
                    ip_fallback_direct_exists = os.path.exists(fallback_path_direct)
                    if ip_fallback_direct_exists:
                        self.font_path_absolute = fallback_path_direct
                        return
                except Exception:
                    ip_fallback_direct_exists = False

                fallback_path_subdir = os.path.join(ip_module_dir, 'font', self.font_file_name)
                try:
                    ip_fallback_subdir_exists = os.path.exists(fallback_path_subdir)
                    if ip_fallback_subdir_exists:
                        self.font_path_absolute = fallback_path_subdir
                        return
                except Exception:
                    ip_fallback_subdir_exists = False

        except Exception:
            pass

        if self.font_path_absolute is None:
            checked_paths = [
                f"Flatpak ('{flatpak_font_path}', exists={flatpak_exists})",
                f"Relative ('{expected_font_path}', exists={relative_exists})"
            ]
            if fallback_path_direct:
                checked_paths.append(f"Fallback Direct ('{fallback_path_direct}', exists={ip_fallback_direct_exists})")
            if fallback_path_subdir:
                checked_paths.append(f"Fallback Subdir ('{fallback_path_subdir}', exists={ip_fallback_subdir_exists})")

            checked_paths_str = ",\n  ".join(checked_paths)
            print(f'CRITICAL FONT INFO: No valid custom font path found after checking:\n  {checked_paths_str}\nRelying on system fonts (Arial/Default).')

    def _perform_initial_image_setup(self):
        self._set_current_image(1, trigger_update=False)
        self._set_current_image(2, trigger_update=False)
        self.update_file_names()
        self._update_resolution_labels()
        self.update_minimum_window_size()
        self.update_comparison_if_needed()

    def _load_settings(self):
        self.settings = QSettings('MyCompany', 'ImageComparisonApp')

        def get_setting(key, default, target_type):
            value = self.settings.value(key)
            if value is None:
                return default
            try:
                if target_type == int:
                    return int(value)
                elif target_type == float:
                    return float(value)
                elif target_type == bool:
                    if isinstance(value, str):
                        if value.lower() == 'true':
                            return True
                        if value.lower() == 'false':
                            return False
                    return bool(int(value)) if value in ('0', '1') else bool(value)
                elif target_type == str:
                    return str(value)
                elif target_type == QColor:
                    color_val = str(value)
                    if QColor.isValidColorName(color_val):
                        return QColor(color_val)
                    test_color = QColor(color_val)
                    if test_color.isValid():
                        return test_color
                    if color_val.startswith('#'):
                        if len(color_val) == 7:
                            try:
                                return QColor(color_val)
                            except ValueError:
                                pass
                        elif len(color_val) == 9:
                            try:
                                return QColor(color_val)
                            except ValueError:
                                pass
                    print(f"Warning: Invalid color format '{color_val}' for key '{key}'. Using default.")
                    return default
                elif target_type == QByteArray:
                    if isinstance(value, QByteArray):
                        return value
                    if isinstance(value, str):
                        try:
                            if not value:
                                return default
                            missing_padding = len(value) % 4
                            if missing_padding:
                                value += '=' * (4 - missing_padding)
                            byte_data = base64.b64decode(value.encode('ascii'))
                            return QByteArray(byte_data)
                        except (base64.binascii.Error, ValueError, TypeError) as e_b64:
                            print(f"Warning: Error decoding Base64 QByteArray for key '{key}'. Value: '{value[:50]}...', Error: {e_b64}")
                            return default
                    elif isinstance(value, (bytes, bytearray)):
                        return QByteArray(value)
                    print(f"Warning: Unexpected type '{type(value)}' for QByteArray key '{key}'. Using default.")
                    return default
                elif target_type == QPointF:
                    if isinstance(value, QPointF):
                        return value
                    try:
                        if isinstance(value, str):
                            parts = value.split(',')
                            if len(parts) == 2:
                                return QPointF(float(parts[0]), float(parts[1]))
                        elif isinstance(value, (list, tuple)) and len(value) == 2:
                            return QPointF(float(value[0]), float(value[1]))
                    except (ValueError, TypeError) as e_point:
                        print(f"Warning: Error decoding QPointF for key '{key}'. Value: '{value}', Error: {e_point}")
                    return default
                return value
            except (ValueError, TypeError) as e_conv:
                print(f"Warning: Could not convert setting '{key}' to {target_type.__name__}, using default. Value: '{value}', Error: {e_conv}")
                return default
        self.loaded_capture_pos_rel_x = get_setting('capture_relative_x', self.DEFAULT_CAPTURE_POS_RELATIVE.x(), float)
        self.loaded_capture_pos_rel_y = get_setting('capture_relative_y', self.DEFAULT_CAPTURE_POS_RELATIVE.y(), float)
        saved_lang = get_setting('language', None, str)
        valid_languages = ['en', 'ru', 'zh', 'pt_BR']
        default_lang = QLocale.system().name()[:2]
        if default_lang not in valid_languages:
            default_lang = 'en'
        self.loaded_language = saved_lang if saved_lang in valid_languages else default_lang
        self.loaded_max_name_length = get_setting('max_name_length', 30, int)
        self.loaded_file_names_state = get_setting('include_file_names', False, bool)
        self.loaded_movement_speed = get_setting('movement_speed_per_sec', 2.0, float)
        self.loaded_magnifier_size_relative = get_setting('magnifier_size_relative', self.DEFAULT_MAGNIFIER_SIZE_RELATIVE, float)
        self.loaded_capture_size_relative = get_setting('capture_size_relative', self.DEFAULT_CAPTURE_SIZE_RELATIVE, float)
        self.loaded_magnifier_offset_relative = get_setting('magnifier_offset_relative', self.DEFAULT_MAGNIFIER_OFFSET_RELATIVE, QPointF)
        self.loaded_magnifier_spacing_relative = get_setting('magnifier_spacing_relative', self.DEFAULT_MAGNIFIER_SPACING_RELATIVE, float)
        self.loaded_geometry = get_setting('window_geometry', QByteArray(), QByteArray)
        self.loaded_was_maximized = get_setting('window_was_maximized', False, bool)
        default_color = QColor(255, 0, 0, 255)
        self.loaded_filename_color_name = get_setting('filename_color', default_color.name(QColor.NameFormat.HexArgb), str)
        self.loaded_image1_paths = get_setting('image_list1_paths', [], list)
        self.loaded_image2_paths = get_setting('image_list2_paths', [], list)
        self.loaded_current_index1 = get_setting('current_index1', -1, int)
        self.loaded_current_index2 = get_setting('current_index2', -1, int)
        self.loaded_jpeg_quality = get_setting('jpeg_quality', self.DEFAULT_JPEG_QUALITY, int)

    def _init_state(self):
        self.image_list1 = []
        self.image_list2 = []
        self.current_index1 = -1
        self.current_index2 = -1
        self.original_image1 = None
        self.original_image2 = None
        self.image1_path = None
        self.image2_path = None
        self.image1 = None
        self.image2 = None
        self.result_image = None
        self.is_horizontal = False
        self.use_magnifier = False
        self.split_position = 0.5
        self.magnifier_size_relative = max(0.05, min(1.0, self.DEFAULT_MAGNIFIER_SIZE_RELATIVE))
        self.capture_size_relative = max(0.01, min(0.5, self.DEFAULT_CAPTURE_SIZE_RELATIVE))
        self.capture_position_relative = QPointF(max(0.0, min(1.0, self.loaded_capture_pos_rel_x)), max(0.0, min(1.0, self.loaded_capture_pos_rel_y)))
        self.magnifier_offset_relative = QPointF(self.DEFAULT_MAGNIFIER_OFFSET_RELATIVE)
        self.magnifier_spacing_relative = max(0.0, min(0.5, self.DEFAULT_MAGNIFIER_SPACING_RELATIVE))
        self.movement_speed_per_sec = max(0.1, min(5.0, self.loaded_movement_speed))
        self.current_language = self.loaded_language
        self.max_name_length = max(self.MIN_NAME_LENGTH_LIMIT, min(self.MAX_NAME_LENGTH_LIMIT, self.loaded_max_name_length))
        self.file_name_color = QColor(self.loaded_filename_color_name)
        if not self.file_name_color.isValid():
            print(f"Warning: Loaded filename color '{self.loaded_filename_color_name}' is invalid. Using default red.")
            self.file_name_color = QColor(255, 0, 0, 255)
        self.spacing_speed_per_sec_qe = 3.0
        self.smoothing_factor_pos = 0.25
        self.smoothing_factor_spacing = 0.25
        self.lerp_stop_threshold = 0.001
        self.max_target_delta_per_tick = 0.15
        self.freeze_magnifier = False
        self.frozen_magnifier_position_relative = None
        self.magnifier_offset_relative_visual = QPointF(self.magnifier_offset_relative)
        self.magnifier_spacing_relative_visual = self.magnifier_spacing_relative
        self.resize_in_progress = False
        self.active_keys = set()
        self._is_dragging_split_line = False
        self._is_dragging_capture_point = False
        self.previous_geometry = None
        self._intend_to_close_maximized = False
        self.pixmap_width = 0
        self.pixmap_height = 0
        self.jpeg_quality = max(1, min(100, self.loaded_jpeg_quality))

    def _init_timers(self):
        self.movement_timer = QTimer(self)
        self.movement_timer.setInterval(16)
        self.movement_timer.timeout.connect(self._update_magnifier_position_by_keys)
        self.movement_elapsed_timer = QElapsedTimer()
        self.last_update_elapsed = 0
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._finish_resize)

    def _build_ui(self):
        self.setAcceptDrops(True)
        self._create_image_label()
        self._init_drag_overlays()
        self._init_warning_label()
        self.resolution_label1 = QLabel('--x--')
        self.resolution_label2 = QLabel('--x--')
        resolution_label_style = 'color: grey; font-size: 9pt;'
        self.resolution_label1.setStyleSheet(resolution_label_style)
        self.resolution_label2.setStyleSheet(resolution_label_style)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        selection_layout = QVBoxLayout()
        selection_layout.setSpacing(2)
        selection_layout.addLayout(self._create_button_layout())
        selection_layout.addLayout(self._create_combobox_layout())
        main_layout.addLayout(selection_layout)
        main_layout.addLayout(self._create_checkbox_layout())
        main_layout.addLayout(self._create_slider_layout())
        main_layout.addWidget(self.image_label)
        resolution_layout = QHBoxLayout()
        resolution_layout.addWidget(self.resolution_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        resolution_layout.addStretch()
        resolution_layout.addWidget(self.resolution_label2, alignment=Qt.AlignmentFlag.AlignRight)
        resolution_layout.setContentsMargins(5, 0, 5, 2)
        main_layout.addLayout(resolution_layout)
        main_layout.addWidget(self.length_warning_label)
        main_layout.addLayout(self._create_file_names_layout())
        main_layout.addLayout(self._create_edit_layout())
        main_layout.addWidget(self._create_save_button())
        self.setLayout(main_layout)
        self.update_translations()

    def _create_button_layout(self):
        layout = QHBoxLayout()
        self.btn_image1 = QPushButton()
        self.btn_image2 = QPushButton()
        self.btn_swap = QPushButton()
        self.btn_clear_list1 = QPushButton()
        self.btn_clear_list2 = QPushButton()
        swap_icon = self._get_icon('swap', fallback_text='⇄')
        self.btn_swap.setIcon(swap_icon)
        self.btn_swap.setIconSize(QSize(20, 20))
        self.btn_swap.setFixedSize(24, 24)
        clear_icon = self._get_icon('trash', use_standard_fallback=QStyle.StandardPixmap.SP_TrashIcon)
        icon_size = QSize(18, 18)
        clear_button_size = QSize(24, 24)
        self.btn_clear_list1.setIcon(clear_icon)
        self.btn_clear_list1.setIconSize(icon_size)
        self.btn_clear_list1.setFixedSize(clear_button_size)
        self.btn_clear_list2.setIcon(clear_icon)
        self.btn_clear_list2.setIconSize(icon_size)
        self.btn_clear_list2.setFixedSize(clear_button_size)
        layout.addWidget(self.btn_image1)
        layout.addWidget(self.btn_clear_list1)
        layout.addWidget(self.btn_swap)
        layout.addWidget(self.btn_image2)
        layout.addWidget(self.btn_clear_list2)
        return layout

    def _create_combobox_layout(self):
        layout = QHBoxLayout()
        self.combo_image1 = QComboBox()
        self.combo_image2 = QComboBox()
        layout.addWidget(self.combo_image1)
        layout.addWidget(self.combo_image2)
        return layout

    def _create_checkbox_layout(self):
        layout = QHBoxLayout()
        self.checkbox_horizontal = QCheckBox()
        self.checkbox_magnifier = QCheckBox()
        self.freeze_button = QCheckBox()
        self.checkbox_file_names = QCheckBox()
        self.help_button = QPushButton()
        help_icon = self._get_icon('help', fallback_text='?')
        self.help_button.setIcon(help_icon)
        self.help_button.setIconSize(QSize(20, 20))
        self.help_button.setFixedSize(24, 24)
        self.btn_settings = QPushButton()
        settings_icon = self._get_icon('settings', fallback_text='...')
        self.btn_settings.setIcon(settings_icon)
        self.btn_settings.setIconSize(QSize(20, 20))
        self.btn_settings.setFixedSize(24, 24)
        layout.addWidget(self.checkbox_horizontal)
        layout.addWidget(self.checkbox_magnifier)
        layout.addWidget(self.freeze_button)
        layout.addWidget(self.checkbox_file_names)
        layout.addStretch()
        layout.addWidget(self.btn_settings)
        layout.addWidget(self.help_button)
        return layout

    def _get_icon(self, icon_key, fallback_text='', use_standard_fallback=None):
        icon = QIcon()
        if icon_key in FLAG_ICONS:
            try:
                image_data = base64.b64decode(FLAG_ICONS[icon_key])
                pixmap = QPixmap()
                if pixmap.loadFromData(image_data):
                    icon = QIcon(pixmap)
                else:
                    img = QImage()
                    if img.loadFromData(image_data):
                        pixmap = QPixmap.fromImage(img)
                        if not pixmap.isNull():
                            icon = QIcon(pixmap)
                        else:
                            print(f"Warning: QPixmap from QImage is null for icon '{icon_key}'.")
                    else:
                        print(f"Warning: Failed to load QImage from data for icon '{icon_key}'.")
            except Exception as e:
                print(f"Error decoding/loading icon '{icon_key}': {e}")
        if icon.isNull() and use_standard_fallback:
            std_icon = self.style().standardIcon(use_standard_fallback)
            if not std_icon.isNull():
                icon = std_icon
            else:
                print(f'Warning: Standard fallback icon {use_standard_fallback} is also null.')
        return icon

    def _create_slider_layout(self):
        layout = QHBoxLayout()
        self.label_magnifier_size = QLabel()
        self.slider_size = QSlider(Qt.Orientation.Horizontal, minimum=5, maximum=100)
        self.label_capture_size = QLabel()
        self.slider_capture = QSlider(Qt.Orientation.Horizontal, minimum=1, maximum=50)
        self.label_movement_speed = QLabel()
        self.slider_speed = QSlider(Qt.Orientation.Horizontal, minimum=1, maximum=50)
        layout.addWidget(self.label_magnifier_size)
        layout.addWidget(self.slider_size)
        layout.addWidget(self.label_capture_size)
        layout.addWidget(self.slider_capture)
        layout.addWidget(self.label_movement_speed)
        layout.addWidget(self.slider_speed)
        return layout

    def _create_image_label(self):
        self.image_label = ClickableLabel(self)
        self.image_label.setMinimumSize(200, 150)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMouseTracking(True)
        return self.image_label

    def _create_file_names_layout(self):
        layout = QHBoxLayout()
        self.file_name_label1 = QLabel('--')
        self.file_name_label2 = QLabel('--')
        self.file_name_label1.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_name_label2.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.file_name_label1, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        layout.addWidget(self.file_name_label2, alignment=Qt.AlignmentFlag.AlignRight)
        layout.setContentsMargins(5, 0, 5, 0)
        return layout

    def _create_edit_layout(self):
        self.edit_layout = QHBoxLayout()
        self.label_edit_name1 = QLabel()
        self.edit_name1 = QLineEdit()
        self.label_edit_name2 = QLabel()
        self.edit_name2 = QLineEdit()
        self.label_edit_font_size = QLabel()
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=1000, value=200)
        self.btn_color_picker = QPushButton()
        icon_size = QSize(20, 20)
        self.btn_color_picker.setIcon(self._create_color_wheel_icon(icon_size))
        self.btn_color_picker.setIconSize(icon_size)
        self.btn_color_picker.setFixedSize(26, 26)
        self.btn_color_picker.setStyleSheet('QPushButton { border: 1px solid grey; border-radius: 13px; }')
        self.edit_layout.addWidget(self.label_edit_name1)
        self.edit_layout.addWidget(self.edit_name1)
        self.edit_layout.addWidget(self.label_edit_name2)
        self.edit_layout.addWidget(self.edit_name2)
        self.edit_layout.addWidget(self.label_edit_font_size)
        self.edit_layout.addWidget(self.font_size_slider)
        self.edit_layout.addWidget(self.btn_color_picker)
        return self.edit_layout

    def _create_color_wheel_icon(self, size: QSize) -> QIcon:
        pixmap = QPixmap(size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        rect = QRectF(0.5, 0.5, size.width() - 1, size.height() - 1)
        num_segments = 12
        angle_step = 360.0 / num_segments
        for i in range(num_segments):
            hue = i / num_segments
            color = QColor.fromHsvF(hue, 1.0, 1.0, 1.0)
            painter.setBrush(QBrush(color))
            start_angle = int((i * angle_step - 90 + angle_step / 2) * 16)
            span_angle = int(angle_step * 16)
            painter.drawPie(rect, start_angle, span_angle)
        painter.end()
        return QIcon(pixmap)

    def _create_save_button(self):
        self.btn_save = QPushButton()
        return self.btn_save

    def _apply_initial_settings_to_ui(self):
        if hasattr(self, 'slider_size'):
            slider_val = int(self.magnifier_size_relative * 100)
            self.slider_size.setValue(slider_val)
            self.slider_size.setToolTip(f'{slider_val}%')
        if hasattr(self, 'slider_capture'):
            slider_val = int(self.capture_size_relative * 100)
            self.slider_capture.setValue(slider_val)
            self.slider_capture.setToolTip(f'{slider_val}%')
        if hasattr(self, 'slider_speed'):
            slider_val = int(self.movement_speed_per_sec * 10)
            self.slider_speed.setValue(slider_val)
        if hasattr(self, 'checkbox_file_names'):
            is_checked = self.loaded_file_names_state
            self.checkbox_file_names.setChecked(is_checked)
            self.toggle_edit_layout_visibility(is_checked)
        if hasattr(self, 'btn_color_picker'):
            self._update_color_button_tooltip()
        mag_widgets_visible = self.use_magnifier
        if hasattr(self, 'slider_size'):
            self.slider_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'slider_capture'):
            self.slider_capture.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_magnifier_size'):
            self.label_magnifier_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_capture_size'):
            self.label_capture_size.setVisible(mag_widgets_visible)
        if hasattr(self, 'freeze_button'):
            self.freeze_button.setEnabled(mag_widgets_visible)
        if hasattr(self, 'slider_speed'):
            self.slider_speed.setVisible(mag_widgets_visible)
        if hasattr(self, 'label_movement_speed'):
            self.label_movement_speed.setVisible(mag_widgets_visible)
        self.update_translations()

    def _connect_signals(self):
        if hasattr(self, 'btn_image1'):
            self.btn_image1.clicked.connect(lambda: self.load_image(1))
        if hasattr(self, 'btn_image2'):
            self.btn_image2.clicked.connect(lambda: self.load_image(2))
        if hasattr(self, 'btn_swap'):
            self.btn_swap.clicked.connect(self.swap_images)
        if hasattr(self, 'btn_clear_list1'):
            self.btn_clear_list1.clicked.connect(lambda: self.clear_image_list(1))
        if hasattr(self, 'btn_clear_list2'):
            self.btn_clear_list2.clicked.connect(lambda: self.clear_image_list(2))
        if hasattr(self, 'btn_save'):
            self.btn_save.clicked.connect(self._save_result_with_error_handling)
        if hasattr(self, 'help_button'):
            self.help_button.clicked.connect(self._show_help_dialog)
        if hasattr(self, 'btn_settings'):
            self.btn_settings.clicked.connect(self._open_settings_dialog)
            if not settings_dialog_available:
                self.btn_settings.setEnabled(False)
        if hasattr(self, 'checkbox_horizontal'):
            self.checkbox_horizontal.stateChanged.connect(self.toggle_orientation)
        if hasattr(self, 'checkbox_magnifier'):
            self.checkbox_magnifier.stateChanged.connect(self.toggle_magnifier)
        if hasattr(self, 'freeze_button'):
            self.freeze_button.stateChanged.connect(self.toggle_freeze_magnifier)
        if hasattr(self, 'checkbox_file_names'):
            self.checkbox_file_names.toggled.connect(self.toggle_edit_layout_visibility)
            self.checkbox_file_names.toggled.connect(self.update_comparison_if_needed)
        if hasattr(self, 'slider_size'):
            self.slider_size.valueChanged.connect(self.update_magnifier_size_relative)
        if hasattr(self, 'slider_capture'):
            self.slider_capture.valueChanged.connect(self.update_capture_size_relative)
        if hasattr(self, 'slider_speed'):
            self.slider_speed.valueChanged.connect(self.update_movement_speed)
        if hasattr(self, 'font_size_slider'):
            self.font_size_slider.valueChanged.connect(self._trigger_live_name_update)
        if hasattr(self, 'combo_image1'):
            self.combo_image1.currentIndexChanged.connect(lambda index: self._on_combobox_changed(1, index))
        if hasattr(self, 'combo_image2'):
            self.combo_image2.currentIndexChanged.connect(lambda index: self._on_combobox_changed(2, index))
        if hasattr(self, 'edit_name1'):
            self.edit_name1.editingFinished.connect(self._on_edit_name_changed)
            self.edit_name1.textChanged.connect(self._trigger_live_name_update)
            self.edit_name1.textChanged.connect(self.update_file_names)
        if hasattr(self, 'edit_name2'):
            self.edit_name2.editingFinished.connect(self._on_edit_name_changed)
            self.edit_name2.textChanged.connect(self._trigger_live_name_update)
            self.edit_name2.textChanged.connect(self.update_file_names)
        if hasattr(self, 'btn_color_picker'):
            self.btn_color_picker.clicked.connect(self._open_color_dialog)
        if hasattr(self, 'image_label'):
            if hasattr(self.image_label, 'mousePressed'):
                self.image_label.mousePressed.connect(self.on_mouse_press)
            if hasattr(self.image_label, 'mouseMoved'):
                self.image_label.mouseMoved.connect(self.on_mouse_move)
            if hasattr(self.image_label, 'mouseReleased'):
                self.image_label.mouseReleased.connect(self.on_mouse_release)

    def _restore_geometry(self):
        geom_setting = self.loaded_geometry
        was_maximized = self.loaded_was_maximized
        restored_from_settings = False
        if geom_setting and isinstance(geom_setting, QByteArray) and (not geom_setting.isEmpty()):
            try:
                restored_geom_ok = self.restoreGeometry(geom_setting)
                if not restored_geom_ok:
                    print('Warning: restoreGeometry returned false. Saved geometry might be invalid.')
                else:
                    restored_from_settings = True
                    if was_maximized:
                        QTimer.singleShot(0, self.showMaximized)
                    else:
                        self.showNormal()
                        self.previous_geometry = None
            except Exception as e:
                print(f'Error restoring geometry: {e}')
                traceback.print_exc()
                restored_from_settings = False
                self.previous_geometry = None
        else:
            print('No valid geometry found in settings.')
        if not restored_from_settings:
            print('Applying default window geometry.')
            self.setGeometry(100, 100, 800, 600)
            self.showNormal()
            self.previous_geometry = None
        QTimer.singleShot(10, self._ensure_minimum_size_after_restore)
        QTimer.singleShot(20, self.update_comparison_if_needed)

    def _ensure_minimum_size_after_restore(self):
        self.update_minimum_window_size()
        min_size = self.minimumSize()
        current_size = self.size()
        new_width = max(current_size.width(), min_size.width())
        new_height = max(current_size.height(), min_size.height())
        if new_width != current_size.width() or new_height != current_size.height():
            print(f'Adjusting window size to minimum: {new_width}x{new_height}')
            self.resize(new_width, new_height)

    def _init_drag_overlays(self):
        style = '\n            background-color: rgba(0, 100, 200, 0.6);\n            color: white;\n            font-size: 20px;\n            border-radius: 10px;\n            padding: 15px;\n            border: 1px solid rgba(255, 255, 255, 0.7);\n        '
        self.drag_overlay1 = QLabel(self.image_label)
        self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay1.setStyleSheet(style)
        self.drag_overlay1.setWordWrap(True)
        self.drag_overlay1.hide()
        self.drag_overlay2 = QLabel(self.image_label)
        self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.drag_overlay2.setStyleSheet(style)
        self.drag_overlay2.setWordWrap(True)
        self.drag_overlay2.hide()

    def _init_warning_label(self):
        self.length_warning_label = QLabel(self)
        self.length_warning_label.setStyleSheet('color: #FF4500; font-weight: bold;')
        self.length_warning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.length_warning_label.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.resize_in_progress:
            self.resize_in_progress = True
        self._update_drag_overlays()
        self.resize_timer.start(200)

    def _finish_resize(self):
        if self.resize_in_progress:
            self.resize_in_progress = False
            QTimer.singleShot(0, self.update_comparison_if_needed)

    def keyPressEvent(self, event):
        key = event.key()
        is_modifier = key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta)
        if self.use_magnifier and (not event.isAutoRepeat()) and (not is_modifier):
            valid_keys = {Qt.Key.Key_W, Qt.Key.Key_A, Qt.Key.Key_S, Qt.Key.Key_D, Qt.Key.Key_Q, Qt.Key.Key_E}
            if key in valid_keys:
                self.active_keys.add(key)
                if not self.movement_timer.isActive():
                    self.movement_elapsed_timer.start()
                    self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
                    self.movement_timer.start()
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        key = event.key()
        is_modifier = key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta)
        if not event.isAutoRepeat() and (not is_modifier) and (key in self.active_keys):
            self.active_keys.remove(key)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def on_mouse_press(self, event):
        if not self.original_image1 or not self.original_image2:
            return
        if self.resize_in_progress:
            return
        pos_f = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.use_magnifier:
                self._is_dragging_capture_point = True
                self._update_split_or_capture_position(pos_f)
                event.accept()
            else:
                self._is_dragging_split_line = True
                self._update_split_or_capture_position(pos_f)
                event.accept()

    def on_mouse_move(self, event):
        if self.resize_in_progress or not self.original_image1 or (not self.original_image2):
            return
        if not event.buttons() & Qt.MouseButton.LeftButton:
            self._is_dragging_capture_point = False
            self._is_dragging_split_line = False
            return
        pos_f = event.position()
        if self.use_magnifier:
            if self._is_dragging_capture_point:
                self._update_split_or_capture_position(pos_f)
                event.accept()
        elif self._is_dragging_split_line:
            self._update_split_or_capture_position(pos_f)
            event.accept()

    def on_mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            needs_final_redraw = False
            if self._is_dragging_split_line:
                self._is_dragging_split_line = False
                needs_final_redraw = True
                event.accept()
            if self._is_dragging_capture_point:
                self._is_dragging_capture_point = False
                needs_final_redraw = True
                self.save_setting('capture_relative_x', self.capture_position_relative.x())
                self.save_setting('capture_relative_y', self.capture_position_relative.y())
                event.accept()
            if needs_final_redraw and (not self.resize_in_progress):
                try:
                    display_result_processor(self)
                except Exception as e:
                    print(f'Error calling display_result_processor on mouse release: {e}')
                    traceback.print_exc()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_drag_overlays()
            self.drag_overlay1.setText(tr('Drop Image(s) 1 Here', self.current_language))
            self.drag_overlay2.setText(tr('Drop Image(s) 2 Here', self.current_language))
            self.drag_overlay1.show()
            self.drag_overlay2.show()
            self.drag_overlay1.raise_()
            self.drag_overlay2.raise_()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_drag_overlays()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()

    def dropEvent(self, event):
        self.drag_overlay1.hide()
        self.drag_overlay2.hide()
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return
        event.acceptProposedAction()
        drop_point = event.position().toPoint()
        target_image_num = 1 if self._is_in_left_area(drop_point) else 2
        local_file_paths = []
        non_local_urls = []
        unsupported_files = []
        errors = []
        supported_exts = ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff')
        for url in urls:
            if url.isLocalFile():
                try:
                    path_str = url.toLocalFile()
                    if not path_str:
                        unsupported_files.append(f"{url.toString()} ({tr('Conversion to local path failed', self.current_language)})")
                        continue
                    display_name = os.path.basename(path_str) or path_str
                    ext = os.path.splitext(path_str)[1].lower()
                    if ext in supported_exts:
                        if os.path.isfile(path_str):
                            local_file_paths.append(path_str)
                        else:
                            errors.append(f"{display_name}: {tr('File not found', self.current_language)}")
                    else:
                        unsupported_files.append(f"{display_name} ({tr('Unsupported extension', self.current_language)}: {ext})")
                except Exception as e:
                    errors.append(f"{display_name}: {tr('Error processing path', self.current_language)} - {e}")
            else:
                non_local_urls.append(url.toString())
        if not local_file_paths:
            reason_list = []
            if non_local_urls:
                reason_list.append(tr('Non-local files skipped:', self.current_language) + f' {len(non_local_urls)}')
            if unsupported_files:
                reason_list.append(tr('Unsupported/Invalid files skipped:', self.current_language) + f' {len(unsupported_files)}')
            if errors:
                reason_list.append(tr('Errors:', self.current_language) + f' {len(errors)}')
            reason_str = '\n - '.join(reason_list) if reason_list else tr('No supported local image files detected in drop.', self.current_language)
            QMessageBox.information(self, tr('Information', self.current_language), tr('No supported local image files could be processed from the dropped items.', self.current_language) + (f"\n\n{tr('Details:', self.current_language)}\n - {reason_str}" if reason_list else ''))
            return
        QTimer.singleShot(0, lambda: self._load_images_from_paths(local_file_paths, target_image_num))
        if errors:
            error_details = '\n - '.join(errors)
            QMessageBox.warning(self, tr('Warning', self.current_language), tr('Some errors occurred while processing dropped files:', self.current_language) + f"\n\n{tr('Details:', self.current_language)}\n - {error_details}")

    def changeEvent(self, event):
        event_type = event.type()
        if event_type == QEvent.Type.LanguageChange:
            print('LanguageChange event detected, updating translations.')
            self.update_translations()
        elif event_type == QEvent.Type.WindowStateChange:
            old_state = event.oldState()
            new_state = self.windowState()
            was_normal = not old_state & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen)
            is_max_or_full = bool(new_state & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
            if is_max_or_full and was_normal:
                current_normal_geom = self.saveGeometry()
                if current_normal_geom and (not current_normal_geom.isEmpty()):
                    self.previous_geometry = current_normal_geom
                    print(f'Saved previous geometry on maximize: {len(self.previous_geometry)} bytes')
                else:
                    print('Warning: Tried to save previous_geometry on maximize, but saveGeometry was empty.')
                    self.previous_geometry = None
            was_max_or_full = bool(old_state & (Qt.WindowState.WindowMaximized | Qt.WindowState.WindowFullScreen))
            is_normal_now = not is_max_or_full
            if is_normal_now and was_max_or_full:
                print('Window restored to normal state.')
                self.previous_geometry = None
                QTimer.singleShot(50, self.update_comparison_if_needed)
                QTimer.singleShot(60, self._ensure_minimum_size_after_restore)
        super().changeEvent(event)

    def closeEvent(self, event):
        current_state = self.windowState()
        should_save_as_maximized = getattr(self, '_intend_to_close_maximized', False)
        geometry_to_save = None
        save_maximized_flag = False
        if should_save_as_maximized:
            if self.previous_geometry and (not self.previous_geometry.isEmpty()):
                geometry_to_save = self.previous_geometry
                save_maximized_flag = True
            else:
                if self.settings.contains('window_geometry'):
                    try:
                        self.settings.remove('window_geometry')
                    except Exception as e:
                        print(f"Error removing 'window_geometry': {e}")
                if self.settings.contains('window_was_maximized'):
                    try:
                        self.settings.remove('window_was_maximized')
                    except Exception as e:
                        print(f"Error removing 'window_was_maximized': {e}")
        else:
            current_geometry = self.saveGeometry()
            if current_geometry and (not current_geometry.isEmpty()):
                geometry_to_save = current_geometry
                save_maximized_flag = False
            else:
                if self.settings.contains('window_geometry'):
                    try:
                        self.settings.remove('window_geometry')
                    except Exception as e:
                        print(f"Error removing 'window_geometry': {e}")
                if self.settings.contains('window_was_maximized'):
                    try:
                        self.settings.remove('window_was_maximized')
                    except Exception as e:
                        print(f"Error removing 'window_was_maximized': {e}")
        if geometry_to_save:
            self.save_setting('window_geometry', geometry_to_save)
            self.save_setting('window_was_maximized', save_maximized_flag)
        if self.settings.contains('previous_geometry'):
            try:
                self.settings.remove('previous_geometry')
            except Exception as e:
                print(f"Error removing 'previous_geometry' on close: {e}")
        self.save_setting('language', self.current_language)
        self.save_setting('max_name_length', self.max_name_length)
        self.save_setting('include_file_names', self.checkbox_file_names.isChecked() if hasattr(self, 'checkbox_file_names') else False)
        self.save_setting('movement_speed_per_sec', self.movement_speed_per_sec)
        self.save_setting('filename_color', self.file_name_color.name(QColor.NameFormat.HexArgb))
        self.save_setting('magnifier_size_relative', self.magnifier_size_relative)
        self.save_setting('capture_size_relative', self.capture_size_relative)
        self.save_setting('capture_relative_x', self.capture_position_relative.x())
        self.save_setting('capture_relative_y', self.capture_position_relative.y())
        self.save_setting('magnifier_offset_relative', self.magnifier_offset_relative)
        self.save_setting('magnifier_spacing_relative', self.magnifier_spacing_relative)
        self.save_setting('jpeg_quality', self.jpeg_quality)
        self.settings.sync()
        super().closeEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)

    def _update_resolution_labels(self):
        res1_text = '--x--'
        tooltip1 = tr('No image loaded', self.current_language)
        if self.original_image1 and hasattr(self.original_image1, 'size'):
            try:
                w, h = self.original_image1.size
                res1_text = f'{w}x{h}'
                tooltip1 = res1_text
            except Exception as e:
                print(f'Error getting size for image 1: {e}')
                res1_text = tr('Error', self.current_language)
                tooltip1 = tr('Error getting image size', self.current_language)
        res2_text = '--x--'
        tooltip2 = tr('No image loaded', self.current_language)
        if self.original_image2 and hasattr(self.original_image2, 'size'):
            try:
                w, h = self.original_image2.size
                res2_text = f'{w}x{h}'
                tooltip2 = res2_text
            except Exception as e:
                print(f'Error getting size for image 2: {e}')
                res2_text = tr('Error', self.current_language)
                tooltip2 = tr('Error getting image size', self.current_language)
        if hasattr(self, 'resolution_label1'):
            self.resolution_label1.setText(res1_text)
            self.resolution_label1.setToolTip(tooltip1)
        if hasattr(self, 'resolution_label2'):
            self.resolution_label2.setText(res2_text)
            self.resolution_label2.setToolTip(tooltip2)

    def update_comparison_if_needed(self):
        if self.resize_in_progress:
            return
        if self.original_image1 and self.original_image2:
            needs_resize = False
            if not self.image1 or not self.image2:
                needs_resize = True
            else:
                try:
                    max_w = max(self.original_image1.width, self.original_image2.width)
                    max_h = max(self.original_image1.height, self.original_image2.height)
                    if self.image1.size != (max_w, max_h) or self.image2.size != (max_w, max_h):
                        needs_resize = True
                except Exception as e:
                    print(f'Error checking image dimensions in update_comparison_if_needed: {e}')
                    needs_resize = True
            if needs_resize:
                try:
                    resize_images_processor(self)
                    if not self.image1 or not self.image2:
                        print('Resize failed or resulted in missing images.')
                        if hasattr(self, 'image_label'):
                            self.image_label.clear()
                        self.result_image = None
                        self.pixmap_width, self.pixmap_height = (0, 0)
                        return
                except Exception as e_resize:
                    print(f'ERROR during resize_images_processor call: {e_resize}')
                    traceback.print_exc()
                    QMessageBox.critical(self, tr('Error', self.current_language), f'Error during image resizing:\n{e_resize}')
                    if hasattr(self, 'image_label'):
                        self.image_label.clear()
                    self.result_image = None
                    self.pixmap_width, self.pixmap_height = (0, 0)
                    return
            if self.image1 and self.image2:
                try:
                    img1_rgba = self.image1
                    img2_rgba = self.image2
                    width, height = img1_rgba.size
                    result = Image.new('RGBA', (width, height))
                    split_pos_abs = 0
                    if not self.is_horizontal:
                        split_pos_abs = max(0, min(width, int(width * self.split_position)))
                        if split_pos_abs > 0:
                            result.paste(img1_rgba.crop((0, 0, split_pos_abs, height)), (0, 0))
                        if split_pos_abs < width:
                            result.paste(img2_rgba.crop((split_pos_abs, 0, width, height)), (split_pos_abs, 0))
                    else:
                        split_pos_abs = max(0, min(height, int(height * self.split_position)))
                        if split_pos_abs > 0:
                            result.paste(img1_rgba.crop((0, 0, width, split_pos_abs)), (0, 0))
                        if split_pos_abs < height:
                            result.paste(img2_rgba.crop((0, split_pos_abs, width, height)), (0, split_pos_abs))
                    self.result_image = result
                except Exception as e_combine:
                    print(f'Error combining images in update_comparison_if_needed: {e_combine}')
                    traceback.print_exc()
                    self.result_image = None
            else:
                print('Warning: Resized images (image1/image2) are missing after resize check.')
                self.result_image = None
            try:
                display_result_processor(self)
            except Exception as e_display:
                print(f'Error calling display_result_processor: {e_display}')
                traceback.print_exc()
                QMessageBox.critical(self, tr('Error', self.current_language), f"{tr('Failed to update comparison view:', self.current_language)}\n{e_display}")
        else:
            if hasattr(self, 'image_label'):
                self.image_label.clear()
            self.result_image = None
            self.image1 = None
            self.image2 = None
            self.pixmap_width, self.pixmap_height = (0, 0)

    def load_image(self, image_number):
        dialog_title = tr(f'Select Image(s) {image_number}', self.current_language)
        file_filter = f"{tr('Image Files', self.current_language)} (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;{tr('All Files', self.current_language)} (*)"
        file_names, _ = QFileDialog.getOpenFileNames(self, dialog_title, '', file_filter)
        if file_names:
            QTimer.singleShot(0, lambda: self._load_images_from_paths(file_names, image_number))

    def _load_images_from_paths(self, file_paths: list[str], image_number: int):
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        loaded_count = 0
        newly_added_indices = []
        paths_actually_added = []
        load_errors = []
        current_paths_in_list = {entry[1] for entry in target_list if len(entry) > 1 and entry[1]}
        target_selection_index = -1
        current_selected_index_before_load = self.current_index1 if image_number == 1 else self.current_index2
        if 0 <= current_selected_index_before_load < len(target_list):
            target_selection_index = current_selected_index_before_load
        for file_path in file_paths:
            if not isinstance(file_path, str) or not file_path:
                load_errors.append(f"{str(file_path)}: {tr('Invalid item type or empty path', self.current_language)}")
                continue
            try:
                normalized_path = os.path.normpath(file_path)
                original_path_for_display = os.path.basename(normalized_path) or tr('Unnamed File', self.current_language)
            except Exception as e_norm:
                load_errors.append(f'{file_path}: Error normalizing path - {e_norm}')
                continue
            if normalized_path in current_paths_in_list:
                print(f'Path {original_path_for_display} already exists. Finding and selecting it.')
                found_index = -1
                try:
                    for idx, item_data in enumerate(target_list):
                        if isinstance(item_data, tuple) and len(item_data) > 1 and (item_data[1] == normalized_path):
                            found_index = idx
                            break
                    if found_index != -1:
                        target_selection_index = found_index
                        print(f'Found at index {found_index}. Will select after processing all files.')
                    else:
                        print(f'Warning: Path {normalized_path} was in set but not found in list {image_number}.')
                        load_errors.append(f"{original_path_for_display}: {tr('Internal state inconsistency (path in set, not list)', self.current_language)}")
                except Exception as e_find:
                    print(f'Error finding existing index for {normalized_path}: {e_find}')
                    load_errors.append(f"{original_path_for_display}: {tr('Error finding existing item', self.current_language)} - {e_find}")
                continue
            try:
                if not os.path.isfile(normalized_path):
                    raise FileNotFoundError(f'File not found at path: {normalized_path}')
                with Image.open(normalized_path) as img:
                    if not hasattr(img, 'copy') or not hasattr(img, 'mode') or (not hasattr(img, 'size')):
                        raise TypeError(f'Image.open returned unexpected type: {type(img)}')
                    temp_image = img.copy()
                    temp_image.load()
                    if temp_image.mode != 'RGBA':
                        temp_image = temp_image.convert('RGBA')
                display_name = original_path_for_display
                target_list.append((temp_image, normalized_path, display_name))
                current_paths_in_list.add(normalized_path)
                newly_added_index = len(target_list) - 1
                newly_added_indices.append(newly_added_index)
                paths_actually_added.append(normalized_path)
                loaded_count += 1
                target_selection_index = newly_added_index
            except FileNotFoundError:
                error_detail = tr('File not found or inaccessible.', self.current_language)
                load_errors.append(f'{original_path_for_display}: {error_detail}')
            except UnidentifiedImageError:
                error_detail = tr('Cannot identify image file (unsupported format?).', self.current_language)
                load_errors.append(f'{original_path_for_display}: {error_detail}')
            except (OSError, IOError, MemoryError, TypeError, ValueError) as e:
                print(f"Error loading image '{original_path_for_display}': {e}")
                traceback.print_exc()
                error_detail = f'{type(e).__name__}: {str(e)[:100]}'
                load_errors.append(f'{original_path_for_display}: {error_detail}')
            except Exception as e:
                print(f"Unexpected error loading image '{original_path_for_display}': {e}")
                traceback.print_exc()
                error_detail = f'Unexpected {type(e).__name__}: {str(e)[:100]}'
                load_errors.append(f'{original_path_for_display}: {error_detail}')
        if loaded_count > 0 or target_selection_index != (self.current_index1 if image_number == 1 else self.current_index2):
            final_index_to_set = -1
            if 0 <= target_selection_index < len(target_list):
                final_index_to_set = target_selection_index
            elif len(target_list) > 0:
                if newly_added_indices:
                    final_index_to_set = newly_added_indices[-1]
                    print(f'Warning: Target index {target_selection_index} invalid, falling back to last added: {final_index_to_set}')
                else:
                    final_index_to_set = 0
                    print(f'Warning: Target index {target_selection_index} invalid and no new items, falling back to index 0.')
            if final_index_to_set != -1:
                if image_number == 1:
                    self.current_index1 = final_index_to_set
                else:
                    self.current_index2 = final_index_to_set
            else:
                print(f'No valid index to select for slot {image_number} after processing. Setting index to -1.')
                if image_number == 1:
                    self.current_index1 = -1
                else:
                    self.current_index2 = -1
            self._update_combobox(image_number)
            self._set_current_image(image_number, trigger_update=True)
        if load_errors:
            QMessageBox.warning(self, tr('Error Loading Images', self.current_language), tr('Some images could not be loaded:', self.current_language) + '\n\n - ' + '\n - '.join(load_errors))

    def _set_current_image(self, image_number, trigger_update=True):
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_index = self.current_index1 if image_number == 1 else self.current_index2
        edit_name_widget = self.edit_name1 if image_number == 1 else self.edit_name2
        old_orig1_size = self.original_image1.size if self.original_image1 and hasattr(self.original_image1, 'size') else None
        old_orig2_size = self.original_image2.size if self.original_image2 and hasattr(self.original_image2, 'size') else None
        reset_image = True
        new_pil_img = None
        new_path = None
        new_display_name = None
        if 0 <= current_index < len(target_list):
            try:
                img_data = target_list[current_index]
                if isinstance(img_data, tuple) and len(img_data) >= 3:
                    if isinstance(img_data[0], Image.Image) and hasattr(img_data[0], 'size'):
                        new_pil_img, new_path, new_display_name = img_data[:3]
                        reset_image = False
                    else:
                        print(f'Warning: Invalid image object in list {image_number} at index {current_index}.')
                else:
                    print(f'Warning: Invalid data format in list {image_number} at index {current_index}. Expected tuple(Image, path, name).')
            except Exception as e:
                print(f'Error accessing image data for slot {image_number} at index {current_index}: {e}')
                traceback.print_exc()
        if reset_image:
            if image_number == 1:
                self.original_image1 = None
                self.image1_path = None
                self.image1 = None
            else:
                self.original_image2 = None
                self.image2_path = None
                self.image2 = None
            if edit_name_widget:
                edit_name_widget.blockSignals(True)
                edit_name_widget.clear()
                edit_name_widget.blockSignals(False)
        else:
            if image_number == 1:
                self.original_image1 = new_pil_img
                self.image1_path = new_path
                self.image1 = None
            else:
                self.original_image2 = new_pil_img
                self.image2_path = new_path
                self.image2 = None
            if edit_name_widget:
                edit_name_widget.blockSignals(True)
                edit_name_widget.setText(new_display_name or '')
                edit_name_widget.blockSignals(False)
        new_orig1_size = self.original_image1.size if self.original_image1 and hasattr(self.original_image1, 'size') else None
        new_orig2_size = self.original_image2.size if self.original_image2 and hasattr(self.original_image2, 'size') else None
        max_dims_changed = False
        old_max_w = max(old_orig1_size[0] if old_orig1_size else 0, old_orig2_size[0] if old_orig2_size else 0)
        old_max_h = max(old_orig1_size[1] if old_orig1_size else 0, old_orig2_size[1] if old_orig2_size else 0)
        new_max_w = max(new_orig1_size[0] if new_orig1_size else 0, new_orig2_size[0] if new_orig2_size else 0)
        new_max_h = max(new_orig1_size[1] if new_orig1_size else 0, new_orig2_size[1] if new_orig2_size else 0)
        if old_max_w != new_max_w or old_max_h != new_max_h:
            max_dims_changed = True
            self.image1 = None
            self.image2 = None
        self.update_file_names()
        self._update_resolution_labels()
        if trigger_update:
            self.update_comparison_if_needed()

    def _update_combobox(self, image_number):
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_internal_index = self.current_index1 if image_number == 1 else self.current_index2
        combobox.blockSignals(True)
        combobox.clear()
        for i, item_data in enumerate(target_list):
            display_name = tr('Invalid Data', self.current_language)
            if isinstance(item_data, tuple) and len(item_data) >= 3:
                display_name = item_data[2] or tr('Unnamed', self.current_language)
            elif isinstance(item_data, tuple) and len(item_data) >= 2 and item_data[1]:
                display_name = os.path.basename(item_data[1])
            else:
                print(f'Warning: Unexpected item format in list {image_number} at index {i}')
                pass
            max_cb_len = 60
            cb_name = display_name[:max_cb_len - 3] + '...' if len(display_name) > max_cb_len else display_name
            combobox.addItem(cb_name)
            combobox.setItemData(i, {'full_name': display_name, 'list_index': i}, Qt.ItemDataRole.UserRole)
            if len(display_name) > max_cb_len:
                combobox.setItemData(i, display_name, Qt.ItemDataRole.ToolTipRole)
        new_index_to_select = -1
        if 0 <= current_internal_index < len(target_list):
            new_index_to_select = current_internal_index
        elif len(target_list) > 0:
            print(f'Warning: Internal index {current_internal_index} invalid for list {image_number} (size {len(target_list)}). Selecting index 0.')
            new_index_to_select = 0
            if image_number == 1:
                self.current_index1 = 0
            else:
                self.current_index2 = 0
        if new_index_to_select != -1:
            combobox.setCurrentIndex(new_index_to_select)
        combobox.blockSignals(False)

    def _on_combobox_changed(self, image_number, index):
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_internal_index = self.current_index1 if image_number == 1 else self.current_index2
        if 0 <= index < len(target_list):
            if index != current_internal_index:
                print(f'Combobox {image_number} changed to index: {index}')
                if image_number == 1:
                    self.current_index1 = index
                else:
                    self.current_index2 = index
                self._set_current_image(image_number, trigger_update=True)
        elif index == -1:
            if current_internal_index != -1:
                print(f'Combobox {image_number} selection cleared (index -1)')
                if image_number == 1:
                    self.current_index1 = -1
                else:
                    self.current_index2 = -1
                self._set_current_image(image_number, trigger_update=True)

    def _on_edit_name_changed(self):
        sender_widget = self.sender()
        if sender_widget == self.edit_name1:
            image_number = 1
            target_list = self.image_list1
            current_index = self.current_index1
            combobox = self.combo_image1
        elif sender_widget == self.edit_name2:
            image_number = 2
            target_list = self.image_list2
            current_index = self.current_index2
            combobox = self.combo_image2
        else:
            return
        if 0 <= current_index < len(target_list):
            new_name = sender_widget.text().strip()
            try:
                old_img, old_path, old_name = target_list[current_index]
                if not new_name:
                    print(f"Name edit {image_number} reverted (empty input). Resetting to '{old_name}'.")
                    sender_widget.blockSignals(True)
                    sender_widget.setText(old_name)
                    sender_widget.blockSignals(False)
                    self.update_file_names()
                    return
                if new_name != old_name:
                    print(f"Updating name for image {image_number} from '{old_name}' to '{new_name}'")
                    target_list[current_index] = (old_img, old_path, new_name)
                    combobox.blockSignals(True)
                    max_cb_len = 60
                    cb_name = new_name[:max_cb_len - 3] + '...' if len(new_name) > max_cb_len else new_name
                    combobox.setItemText(current_index, cb_name)
                    combobox.setItemData(current_index, {'full_name': new_name, 'list_index': current_index}, Qt.ItemDataRole.UserRole)
                    if len(new_name) > max_cb_len:
                        combobox.setItemData(current_index, new_name, Qt.ItemDataRole.ToolTipRole)
                    else:
                        combobox.setItemData(current_index, None, Qt.ItemDataRole.ToolTipRole)
                    combobox.blockSignals(False)
                    self.update_file_names()
                    if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
                        self.update_comparison_if_needed()
            except IndexError:
                print(f'Error: Index {current_index} out of bounds for list {image_number} during name update.')
            except Exception as e:
                print(f'Error updating name for image {image_number}: {e}')
                traceback.print_exc()
        else:
            print(f'Warning: Cannot update name for slot {image_number}, index {current_index} is invalid.')

    def swap_images(self):
        self.image_list1, self.image_list2 = (self.image_list2, self.image_list1)
        self.current_index1, self.current_index2 = (self.current_index2, self.current_index1)
        self._update_combobox(1)
        self._update_combobox(2)
        self._set_current_image(1, trigger_update=False)
        self._set_current_image(2, trigger_update=True)

    def clear_image_list(self, image_number):
        print(f'Clearing image list {image_number}...')
        if image_number == 1:
            target_list = self.image_list1
            combobox = self.combo_image1 if hasattr(self, 'combo_image1') else None
            edit_name_widget = self.edit_name1 if hasattr(self, 'edit_name1') else None
            self.current_index1 = -1
            self.original_image1 = None
            self.image1_path = None
            self.image1 = None
        elif image_number == 2:
            target_list = self.image_list2
            combobox = self.combo_image2 if hasattr(self, 'combo_image2') else None
            edit_name_widget = self.edit_name2 if hasattr(self, 'edit_name2') else None
            self.current_index2 = -1
            self.original_image2 = None
            self.image2_path = None
            self.image2 = None
        else:
            print(f'Warning: Invalid image_number {image_number} passed to clear_image_list.')
            return
        target_list.clear()
        if combobox:
            combobox.blockSignals(True)
            combobox.clear()
            combobox.blockSignals(False)
        if edit_name_widget:
            edit_name_widget.blockSignals(True)
            edit_name_widget.clear()
            edit_name_widget.blockSignals(False)
        self.update_comparison_if_needed()
        self.update_file_names()
        self.check_name_lengths()
        self._update_resolution_labels()

    def _save_result_with_error_handling(self):
        try:
            if not self.original_image1 or not self.original_image2:
                QMessageBox.warning(self, tr('Warning', self.current_language), tr('Please load and select images in both slots first.', self.current_language))
                return
            if not self.image1 or not self.image2:
                print('Resized images missing before save, attempting resize...')
                resize_images_processor(self)
                if not self.image1 or not self.image2:
                    QMessageBox.warning(self, tr('Warning', self.current_language), tr('Resized images not available. Cannot save result. Please reload or select images.', self.current_language))
                    return
            save_result_processor(self)
        except Exception as e:
            print(f'ERROR during save_result_processor call: {e}')
            traceback.print_exc()
            QMessageBox.critical(self, tr('Error', self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{str(e)}")

    def _update_magnifier_position_by_keys(self):
        if not self.use_magnifier or self.resize_in_progress:
            if self.movement_timer.isActive():
                self.movement_timer.stop()
            return
        current_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_ms = current_elapsed - self.last_update_elapsed
        if delta_time_ms <= 0 or delta_time_ms > 100:
            delta_time_ms = self.movement_timer.interval()
        delta_time_sec = delta_time_ms / 1000.0
        self.last_update_elapsed = current_elapsed
        target_pos_changed = False
        target_spacing_changed = False
        visual_pos_moved = False
        visual_spacing_moved = False
        epsilon = 1e-06
        if self.active_keys:
            dx_dir = (Qt.Key.Key_D in self.active_keys) - (Qt.Key.Key_A in self.active_keys)
            dy_dir = (Qt.Key.Key_S in self.active_keys) - (Qt.Key.Key_W in self.active_keys)
            ds_dir = (Qt.Key.Key_E in self.active_keys) - (Qt.Key.Key_Q in self.active_keys)
            length_sq = dx_dir * dx_dir + dy_dir * dy_dir
            if length_sq > 1.0 + epsilon:
                inv_length = 1.0 / math.sqrt(length_sq)
                dx_dir *= inv_length
                dy_dir *= inv_length
            speed_multiplier = self.movement_speed_per_sec
            if dx_dir != 0 or dy_dir != 0:
                if self.freeze_magnifier:
                    if self.frozen_magnifier_position_relative and self.pixmap_width > 0 and (self.pixmap_height > 0):
                        pixel_speed = BASE_PIXEL_SPEED_FROZEN * speed_multiplier
                        target_pixel_dx = dx_dir * pixel_speed * delta_time_sec
                        target_pixel_dy = dy_dir * pixel_speed * delta_time_sec
                        current_frozen_pix_x = self.frozen_magnifier_position_relative.x() * self.pixmap_width
                        current_frozen_pix_y = self.frozen_magnifier_position_relative.y() * self.pixmap_height
                        new_frozen_pix_x = current_frozen_pix_x + target_pixel_dx
                        new_frozen_pix_y = current_frozen_pix_y + target_pixel_dy
                        new_x_rel = max(0.0, min(1.0, new_frozen_pix_x / self.pixmap_width))
                        new_y_rel = max(0.0, min(1.0, new_frozen_pix_y / self.pixmap_height))
                        if not math.isclose(new_x_rel, self.frozen_magnifier_position_relative.x(), abs_tol=epsilon) or not math.isclose(new_y_rel, self.frozen_magnifier_position_relative.y(), abs_tol=epsilon):
                            self.frozen_magnifier_position_relative.setX(new_x_rel)
                            self.frozen_magnifier_position_relative.setY(new_y_rel)
                            target_pos_changed = True
                else:
                    relative_speed = BASE_RELATIVE_SPEED_UNFROZEN * speed_multiplier
                    delta_offset_x = dx_dir * relative_speed * delta_time_sec
                    delta_offset_y = dy_dir * relative_speed * delta_time_sec
                    clamped_dx_rel = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, delta_offset_x))
                    clamped_dy_rel = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, delta_offset_y))
                    new_target_x = self.magnifier_offset_relative.x() + clamped_dx_rel
                    new_target_y = self.magnifier_offset_relative.y() + clamped_dy_rel
                    if not math.isclose(new_target_x, self.magnifier_offset_relative.x(), abs_tol=epsilon) or not math.isclose(new_target_y, self.magnifier_offset_relative.y(), abs_tol=epsilon):
                        self.magnifier_offset_relative.setX(new_target_x)
                        self.magnifier_offset_relative.setY(new_target_y)
                        target_pos_changed = True
            if ds_dir != 0:
                spacing_speed = self.spacing_speed_per_sec_qe
                delta_spacing = ds_dir * spacing_speed * delta_time_sec
                clamped_ds_rel = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, delta_spacing))
                new_target_spacing = self.magnifier_spacing_relative + clamped_ds_rel
                new_target_spacing_clamped = max(0.0, min(0.5, new_target_spacing))
                if not math.isclose(new_target_spacing_clamped, self.magnifier_spacing_relative, abs_tol=epsilon):
                    self.magnifier_spacing_relative = new_target_spacing_clamped
                    target_spacing_changed = True
        if not self.freeze_magnifier:
            delta_vx = self.magnifier_offset_relative.x() - self.magnifier_offset_relative_visual.x()
            delta_vy = self.magnifier_offset_relative.y() - self.magnifier_offset_relative_visual.y()
            if abs(delta_vx) < self.lerp_stop_threshold and abs(delta_vy) < self.lerp_stop_threshold:
                if not math.isclose(self.magnifier_offset_relative_visual.x(), self.magnifier_offset_relative.x(), abs_tol=epsilon) or not math.isclose(self.magnifier_offset_relative_visual.y(), self.magnifier_offset_relative.y(), abs_tol=epsilon):
                    self.magnifier_offset_relative_visual.setX(self.magnifier_offset_relative.x())
                    self.magnifier_offset_relative_visual.setY(self.magnifier_offset_relative.y())
                    visual_pos_moved = True
            else:
                new_visual_x = self.magnifier_offset_relative_visual.x() + delta_vx * self.smoothing_factor_pos
                new_visual_y = self.magnifier_offset_relative_visual.y() + delta_vy * self.smoothing_factor_pos
                self.magnifier_offset_relative_visual.setX(new_visual_x)
                self.magnifier_offset_relative_visual.setY(new_visual_y)
                visual_pos_moved = True
        delta_vs = self.magnifier_spacing_relative - self.magnifier_spacing_relative_visual
        if abs(delta_vs) < self.lerp_stop_threshold:
            if not math.isclose(self.magnifier_spacing_relative_visual, self.magnifier_spacing_relative, abs_tol=epsilon):
                self.magnifier_spacing_relative_visual = self.magnifier_spacing_relative
                visual_spacing_moved = True
        else:
            new_visual_spacing = self.magnifier_spacing_relative_visual + delta_vs * self.smoothing_factor_spacing
            self.magnifier_spacing_relative_visual = max(0.0, new_visual_spacing)
            visual_spacing_moved = True
        needs_redraw = target_pos_changed or target_spacing_changed or visual_pos_moved or visual_spacing_moved
        if needs_redraw and (not self.resize_in_progress):
            try:
                display_result_processor(self)
            except Exception as e:
                print(f'Error calling display_result_processor in _update_magnifier_position_by_keys: {e}')
                traceback.print_exc()
        if not self.active_keys:
            pos_is_settled = self.freeze_magnifier or (abs(delta_vx) < self.lerp_stop_threshold and abs(delta_vy) < self.lerp_stop_threshold)
            spacing_is_settled = abs(delta_vs) < self.lerp_stop_threshold
            if pos_is_settled and spacing_is_settled:
                self.movement_timer.stop()
                print('Magnifier movement timer stopped.')
                needs_final_set = False
                if not self.freeze_magnifier:
                    if not math.isclose(self.magnifier_offset_relative_visual.x(), self.magnifier_offset_relative.x(), abs_tol=epsilon) or not math.isclose(self.magnifier_offset_relative_visual.y(), self.magnifier_offset_relative.y(), abs_tol=epsilon):
                        self.magnifier_offset_relative_visual.setX(self.magnifier_offset_relative.x())
                        self.magnifier_offset_relative_visual.setY(self.magnifier_offset_relative.y())
                        needs_final_set = True
                if not math.isclose(self.magnifier_spacing_relative_visual, self.magnifier_spacing_relative, abs_tol=epsilon):
                    self.magnifier_spacing_relative_visual = self.magnifier_spacing_relative
                    needs_final_set = True
                if needs_final_set and (not self.resize_in_progress):
                    print('Performing final snap redraw for magnifier.')
                    try:
                        display_result_processor(self)
                    except Exception as e:
                        print(f'Error calling display_result_processor after movement stop: {e}')
                        traceback.print_exc()
                self.save_setting('magnifier_offset_relative', self.magnifier_offset_relative)
                self.save_setting('magnifier_spacing_relative', self.magnifier_spacing_relative)

    def toggle_orientation(self, state):
        new_state_bool = state == Qt.CheckState.Checked.value
        if new_state_bool != self.is_horizontal:
            self.is_horizontal = new_state_bool
            print(f"Split orientation changed to: {('Horizontal' if self.is_horizontal else 'Vertical')}")
            self.update_file_names()
            self.update_comparison_if_needed()

    def toggle_magnifier(self, state):
        new_state_bool = state == Qt.CheckState.Checked.value
        if new_state_bool == self.use_magnifier:
            return
        self.use_magnifier = new_state_bool
        print(f"Magnifier {('enabled' if self.use_magnifier else 'disabled')}")
        visible = self.use_magnifier
        if hasattr(self, 'slider_size'):
            self.slider_size.setVisible(visible)
        if hasattr(self, 'slider_capture'):
            self.slider_capture.setVisible(visible)
        if hasattr(self, 'label_magnifier_size'):
            self.label_magnifier_size.setVisible(visible)
        if hasattr(self, 'label_capture_size'):
            self.label_capture_size.setVisible(visible)
        if hasattr(self, 'freeze_button'):
            self.freeze_button.setEnabled(visible)
        if hasattr(self, 'slider_speed'):
            self.slider_speed.setVisible(visible)
        if hasattr(self, 'label_movement_speed'):
            self.label_movement_speed.setVisible(visible)
        if not self.use_magnifier:
            self.active_keys.clear()
            if self.movement_timer.isActive():
                self.movement_timer.stop()
            if self.freeze_magnifier:
                if hasattr(self, 'freeze_button'):
                    self.freeze_button.setChecked(False)
                else:
                    self._unfreeze_magnifier_logic()
        self.update_comparison_if_needed()

    def toggle_freeze_magnifier(self, state):
        if not self.use_magnifier:
            if state == Qt.CheckState.Checked.value and hasattr(self, 'freeze_button'):
                self.freeze_button.blockSignals(True)
                self.freeze_button.setChecked(False)
                self.freeze_button.blockSignals(False)
            return
        new_freeze_state = state == Qt.CheckState.Checked.value
        if new_freeze_state == self.freeze_magnifier:
            return
        if new_freeze_state:
            print('Attempting to freeze magnifier...')
            can_freeze = self.use_magnifier and self.original_image1 and self.original_image2 and self.result_image and (self.result_image.width > 0) and (self.result_image.height > 0) and (self.pixmap_width > 0) and (self.pixmap_height > 0)
            if can_freeze:
                try:
                    coords = get_original_coords(app=self, drawing_width=self.result_image.width, drawing_height=self.result_image.height, display_width=self.pixmap_width, display_height=self.pixmap_height, use_visual_offset=True)
                    if coords and coords[4] is not None:
                        magnifier_midpoint_drawing = coords[4]
                        rel_x = max(0.0, min(1.0, float(magnifier_midpoint_drawing.x()) / float(self.result_image.width)))
                        rel_y = max(0.0, min(1.0, float(magnifier_midpoint_drawing.y()) / float(self.result_image.height)))
                        self.frozen_magnifier_position_relative = QPointF(rel_x, rel_y)
                        self.freeze_magnifier = True
                        print(f'Magnifier frozen at relative position: ({rel_x:.3f}, {rel_y:.3f})')
                        self.magnifier_offset_relative_visual = QPointF(self.magnifier_offset_relative)
                        self.magnifier_spacing_relative_visual = self.magnifier_spacing_relative
                    else:
                        self.freeze_magnifier = False
                        print('Warning: Could not get valid magnifier coordinates to freeze.')
                except Exception as e_freeze_calc:
                    self.freeze_magnifier = False
                    print(f'Error calculating freeze position: {e_freeze_calc}')
                    traceback.print_exc()
            else:
                self.freeze_magnifier = False
                print('Warning: Cannot freeze magnifier (conditions not met - images loaded, view rendered?).')
            if not self.freeze_magnifier and hasattr(self, 'freeze_button') and self.freeze_button.isChecked():
                self.freeze_button.blockSignals(True)
                self.freeze_button.setChecked(False)
                self.freeze_button.blockSignals(False)
        else:
            print('Unfreezing magnifier...')
            self._unfreeze_magnifier_logic()
        self.update_comparison_if_needed()

    def _unfreeze_magnifier_logic(self):
        if not self.freeze_magnifier:
            return
        frozen_pos_rel = self.frozen_magnifier_position_relative
        self.freeze_magnifier = False
        self.frozen_magnifier_position_relative = None
        new_target_offset_rel = QPointF(0.0, -0.5)
        if frozen_pos_rel and self.pixmap_width > 0 and (self.pixmap_height > 0):
            try:
                target_min_dim = float(min(self.pixmap_width, self.pixmap_height))
                REFERENCE_MAGNIFIER_RELATIVE_SIZE = 0.2
                reference_magnifier_size_display = max(1.0, REFERENCE_MAGNIFIER_RELATIVE_SIZE * target_min_dim)
                frozen_x_pix = frozen_pos_rel.x() * self.pixmap_width
                frozen_y_pix = frozen_pos_rel.y() * self.pixmap_height
                cap_center_pix_x = self.capture_position_relative.x() * self.pixmap_width
                cap_center_pix_y = self.capture_position_relative.y() * self.pixmap_height
                required_offset_pixels_x = frozen_x_pix - cap_center_pix_x
                required_offset_pixels_y = frozen_y_pix - cap_center_pix_y
                if reference_magnifier_size_display > 0:
                    required_offset_rel_x = required_offset_pixels_x / reference_magnifier_size_display
                    required_offset_rel_y = required_offset_pixels_y / reference_magnifier_size_display
                    new_target_offset_rel = QPointF(required_offset_rel_x, required_offset_rel_y)
                    print(f'Calculated unfreeze target offset: ({required_offset_rel_x:.3f}, {required_offset_rel_y:.3f})')
                else:
                    print('Warning: Reference magnifier size is zero during unfreeze calculation.')
            except Exception as e:
                print(f'Error calculating offset during unfreeze: {e}')
                traceback.print_exc()
                new_target_offset_rel = QPointF(0.0, -0.5)
        else:
            print('Warning: Cannot calculate offset on unfreeze (missing frozen pos or pixmap dims). Using default.')
        self.magnifier_offset_relative = new_target_offset_rel
        self.magnifier_offset_relative_visual = QPointF(new_target_offset_rel)
        self.magnifier_spacing_relative_visual = self.magnifier_spacing_relative
        if self.active_keys and (not self.movement_timer.isActive()) and self.use_magnifier:
            print('Restarting movement timer after unfreeze.')
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()

    def update_magnifier_size_relative(self, value):
        new_relative_size = max(0.05, min(1.0, value / 100.0))
        if not math.isclose(new_relative_size, self.magnifier_size_relative):
            self.magnifier_size_relative = new_relative_size
            self.save_setting('magnifier_size_relative', self.magnifier_size_relative)
            if hasattr(self, 'slider_size'):
                self.slider_size.setToolTip(f'{value}%')
            self.update_comparison_if_needed()

    def update_capture_size_relative(self, value):
        new_relative_size = max(0.01, min(0.5, value / 100.0))
        if not math.isclose(new_relative_size, self.capture_size_relative):
            self.capture_size_relative = new_relative_size
            self.save_setting('capture_size_relative', self.capture_size_relative)
            if hasattr(self, 'slider_capture'):
                self.slider_capture.setToolTip(f'{value}%')
            self.update_comparison_if_needed()

    def update_movement_speed(self, value):
        new_speed = max(0.1, min(5.0, value / 10.0))
        if not math.isclose(new_speed, self.movement_speed_per_sec):
            self.movement_speed_per_sec = new_speed
            self.save_setting('movement_speed_per_sec', self.movement_speed_per_sec)
            if hasattr(self, 'slider_speed'):
                speed_tooltip = f"{self.movement_speed_per_sec:.1f} {tr('rel. units/sec', self.current_language)}"
                self.slider_speed.setToolTip(speed_tooltip)

    def toggle_edit_layout_visibility(self, checked):
        if not hasattr(self, 'edit_layout'):
            return
        is_visible = bool(checked)
        for i in range(self.edit_layout.count()):
            item = self.edit_layout.itemAt(i)
            if item and item.widget():
                item.widget().setVisible(is_visible)
        self.update_minimum_window_size()
        if is_visible and self.original_image1 and self.original_image2:
            self.update_comparison_if_needed()

    def _open_color_dialog(self):
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel
        color = QColorDialog.getColor(self.file_name_color, self, tr('Select Filename Color', self.current_language), options=options)
        if color.isValid() and color != self.file_name_color:
            self.file_name_color = color
            print(f'Filename color changed to: {color.name(QColor.NameFormat.HexArgb)}')
            self._update_color_button_tooltip()
            self.save_setting('filename_color', color.name(QColor.NameFormat.HexArgb))
            if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
                self.update_comparison_if_needed()

    def _update_color_button_tooltip(self):
        if hasattr(self, 'btn_color_picker'):
            tooltip_text = f"{tr('Change Filename Color', self.current_language)}\n{tr('Current:', self.current_language)} {self.file_name_color.name(QColor.NameFormat.HexArgb)}"
            self.btn_color_picker.setToolTip(tooltip_text)

    def save_setting(self, key, value):
        try:
            if isinstance(value, QPointF):
                value_to_save = f'{value.x()},{value.y()}'
            elif isinstance(value, QByteArray):
                value_to_save = value.toBase64().data().decode('ascii') if not value.isEmpty() else ''
            elif isinstance(value, QColor):
                value_to_save = value.name(QColor.NameFormat.HexArgb)
            else:
                value_to_save = value
            self.settings.setValue(key, value_to_save)
        except Exception as e:
            print(f"ERROR saving setting '{key}' (value type: {type(value)}): {e}")
            traceback.print_exc()

    def change_language(self, language_code):
        valid_languages = ['en', 'ru', 'zh', 'pt_BR']
        if language_code not in valid_languages:
            print(f"Warning: Invalid language '{language_code}' requested. Defaulting to 'en'.")
            language_code = 'en'
        if language_code == self.current_language:
            return
        print(f'Changing language to: {language_code}')
        self.current_language = language_code
        self.update_translations()
        self.update_file_names()
        self.save_setting('language', language_code)
        if hasattr(self, 'length_warning_label'):
            self.check_name_lengths()
        if hasattr(self, 'help_button'):
            self.help_button.setToolTip(tr('Show Help', self.current_language))
        if hasattr(self, 'slider_speed'):
            speed_tooltip = f"{self.movement_speed_per_sec:.1f} {tr('rel. units/sec', self.current_language)}"
            self.slider_speed.setToolTip(speed_tooltip)
        if hasattr(self, 'btn_settings'):
            tooltip = tr('Settings dialog module not found.', self.current_language) if not settings_dialog_available else tr('Open Application Settings', self.current_language)
            self.btn_settings.setToolTip(tooltip)
        self._update_color_button_tooltip()
        if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            self.update_comparison_if_needed()

    def update_translations(self):
        lang = self.current_language
        self.setWindowTitle(tr('Improve ImgSLI', lang))
        if hasattr(self, 'btn_image1'):
            self.btn_image1.setText(tr('Add Image(s) 1', lang))
        if hasattr(self, 'btn_image2'):
            self.btn_image2.setText(tr('Add Image(s) 2', lang))
        if hasattr(self, 'btn_swap'):
            self.btn_swap.setToolTip(tr('Swap Image Lists', lang))
        if hasattr(self, 'btn_clear_list1'):
            self.btn_clear_list1.setToolTip(tr('Clear Left Image List', lang))
        if hasattr(self, 'btn_clear_list2'):
            self.btn_clear_list2.setToolTip(tr('Clear Right Image List', lang))
        if hasattr(self, 'btn_save'):
            self.btn_save.setText(tr('Save Result', lang))
        if hasattr(self, 'help_button'):
            self.help_button.setToolTip(tr('Show Help', lang))
        if hasattr(self, 'btn_settings'):
            tooltip = tr('Settings dialog module not found.', lang) if not settings_dialog_available else tr('Open Application Settings', lang)
            self.btn_settings.setToolTip(tooltip)
        if hasattr(self, 'checkbox_horizontal'):
            self.checkbox_horizontal.setText(tr('Horizontal Split', lang))
        if hasattr(self, 'checkbox_magnifier'):
            self.checkbox_magnifier.setText(tr('Use Magnifier', lang))
        if hasattr(self, 'freeze_button'):
            self.freeze_button.setText(tr('Freeze Magnifier', lang))
        if hasattr(self, 'checkbox_file_names'):
            self.checkbox_file_names.setText(tr('Include file names in saved image', lang))
        if hasattr(self, 'label_magnifier_size'):
            self.label_magnifier_size.setText(tr('Magnifier Size (%):', lang))
        if hasattr(self, 'label_capture_size'):
            self.label_capture_size.setText(tr('Capture Size (%):', lang))
        if hasattr(self, 'label_movement_speed'):
            self.label_movement_speed.setText(tr('Move Speed:', lang))
        if hasattr(self, 'label_edit_name1'):
            self.label_edit_name1.setText(tr('Name 1:', lang))
        if hasattr(self, 'edit_name1'):
            self.edit_name1.setPlaceholderText(tr('Edit Current Image 1 Name', lang))
        if hasattr(self, 'label_edit_name2'):
            self.label_edit_name2.setText(tr('Name 2:', lang))
        if hasattr(self, 'edit_name2'):
            self.edit_name2.setPlaceholderText(tr('Edit Current Image 2 Name', lang))
        if hasattr(self, 'label_edit_font_size'):
            self.label_edit_font_size.setText(tr('Font Size (%):', lang))
        if hasattr(self, 'combo_image1'):
            self.combo_image1.setToolTip(tr('Select image for left/top side', lang))
        if hasattr(self, 'combo_image2'):
            self.combo_image2.setToolTip(tr('Select image for right/bottom side', lang))
        if hasattr(self, 'slider_speed'):
            speed_tooltip = f"{self.movement_speed_per_sec:.1f} {tr('rel. units/sec', lang)}"
            self.slider_speed.setToolTip(speed_tooltip)
        self._update_color_button_tooltip()
        if hasattr(self, 'drag_overlay1') and self.drag_overlay1.isVisible():
            self.drag_overlay1.setText(tr('Drop Image(s) 1 Here', lang))
        if hasattr(self, 'drag_overlay2') and self.drag_overlay2.isVisible():
            self.drag_overlay2.setText(tr('Drop Image(s) 2 Here', lang))
        if hasattr(self, 'length_warning_label') and self.length_warning_label.isVisible():
            self.check_name_lengths()
        self.update_file_names()
        self._update_resolution_labels()

    def _show_help_dialog(self):
        help_text = f"--- {tr('Improve ImgSLI Help', self.current_language)} ---\n\n**{tr('Loading Images:', self.current_language)}**\n- {tr('Use Add buttons or Drag-n-Drop images onto the left/right side.', self.current_language)}\n- {tr('Use the dropdown menus to select from loaded images.', self.current_language)}\n- {tr('Use the ⇄ button to swap the entire left and right image lists.', self.current_language)}\n- {tr('Use the Trash buttons (🗑️) to clear the corresponding image list.', self.current_language)}\n\n**{tr('Comparison View:', self.current_language)}**\n- {tr('Click and drag the separation line to adjust the split (when Magnifier is off).', self.current_language)}\n- {tr('Check [Horizontal Split] to change the split orientation.', self.current_language)}\n\n**{tr('Magnifier Tool (when checked):', self.current_language)}**\n- {tr('Click/drag on the main image to set the capture point (red circle).', self.current_language)}\n- {tr('Use WASD keys to move the zoomed-in view (magnifier) relative to the capture point.', self.current_language)}\n- {tr('Use QE keys to adjust the spacing between the two magnifier halves (when separated).', self.current_language)}\n- {tr('Sliders adjust Magnifier Size (zoom level), Capture Size (area sampled), and Move Speed.', self.current_language)}\n- {tr('Check [Freeze Magnifier] to lock the zoomed view position on screen (WASD moves the frozen view).', self.current_language)}\n\n**{tr('Output:', self.current_language)}**\n- {tr('Check [Include file names...] to enable options for saving names on the image.', self.current_language)}\n- {tr('Edit names, adjust font size, and pick text color in the bottom panel (visible when names are included).', self.current_language)}\n- {tr('Click [Save Result] to save the current view (including split, magnifier, names if enabled) as a PNG or JPG file.', self.current_language)}\n\n**{tr('Settings:', self.current_language)}**\n- {tr('Click the settings button (...) to change the application language, the maximum displayed name length, and JPEG quality.', self.current_language)}\n"
        QMessageBox.information(self, tr('Help', self.current_language), help_text)

    def _update_split_or_capture_position(self, cursor_pos_f: QPointF):
        if self.pixmap_width <= 0 or self.pixmap_height <= 0:
            return
        label_rect = self.image_label.rect()
        x_offset = max(0, (label_rect.width() - self.pixmap_width) // 2)
        y_offset = max(0, (label_rect.height() - self.pixmap_height) // 2)
        pixmap_x_f = cursor_pos_f.x() - x_offset
        pixmap_y_f = cursor_pos_f.y() - y_offset
        pixmap_x_clamped = max(0.0, min(float(self.pixmap_width), pixmap_x_f))
        pixmap_y_clamped = max(0.0, min(float(self.pixmap_height), pixmap_y_f))
        rel_x = pixmap_x_clamped / float(self.pixmap_width)
        rel_y = pixmap_y_clamped / float(self.pixmap_height)
        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))
        needs_update = False
        epsilon = 1e-06
        if not self.use_magnifier:
            new_split = rel_x if not self.is_horizontal else rel_y
            if not math.isclose(self.split_position, new_split, abs_tol=epsilon):
                self.split_position = new_split
                needs_update = True
        else:
            new_rel_pos = QPointF(rel_x, rel_y)
            current_rel_pos = self.capture_position_relative
            if not math.isclose(current_rel_pos.x(), new_rel_pos.x(), abs_tol=epsilon) or not math.isclose(current_rel_pos.y(), new_rel_pos.y(), abs_tol=epsilon):
                self.capture_position_relative = new_rel_pos
                needs_update = True
        if needs_update:
            try:
                if not self.use_magnifier:
                    self.update_comparison_if_needed()
                else:
                    display_result_processor(self)
            except Exception as e:
                context = 'split line drag' if not self.use_magnifier else 'capture point drag'
                print(f'Error calling update/display processor during {context}: {e}')
                traceback.print_exc()

    def _trigger_live_name_update(self):
        if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            if self.original_image1 and self.original_image2:
                self.update_comparison_if_needed()
        self.update_file_names()
        self.check_name_lengths()

    def update_file_names(self):
        name1_raw = ''
        edit1_text = self.edit_name1.text() if hasattr(self, 'edit_name1') else ''
        if 0 <= self.current_index1 < len(self.image_list1):
            try:
                _, _, display_name_from_list = self.image_list1[self.current_index1]
                name1_raw = edit1_text if edit1_text else display_name_from_list
            except (IndexError, TypeError, ValueError):
                name1_raw = edit1_text
        elif self.original_image1 is None:
            name1_raw = tr('Image 1', self.current_language)
        else:
            name1_raw = edit1_text
        name2_raw = ''
        edit2_text = self.edit_name2.text() if hasattr(self, 'edit_name2') else ''
        if 0 <= self.current_index2 < len(self.image_list2):
            try:
                _, _, display_name_from_list = self.image_list2[self.current_index2]
                name2_raw = edit2_text if edit2_text else display_name_from_list
            except (IndexError, TypeError, ValueError):
                name2_raw = edit2_text
        elif self.original_image2 is None:
            name2_raw = tr('Image 2', self.current_language)
        else:
            name2_raw = edit2_text
        max_len_ui = self.max_name_length
        display_name1 = name1_raw[:max_len_ui - 3] + '...' if len(name1_raw or '') > max_len_ui else name1_raw or ''
        display_name2 = name2_raw[:max_len_ui - 3] + '...' if len(name2_raw or '') > max_len_ui else name2_raw or ''
        if hasattr(self, 'file_name_label1') and hasattr(self, 'file_name_label2'):
            prefix1 = tr('Left', self.current_language) if not self.is_horizontal else tr('Top', self.current_language)
            prefix2 = tr('Right', self.current_language) if not self.is_horizontal else tr('Bottom', self.current_language)
            self.file_name_label1.setText(f'{prefix1}: {display_name1}')
            self.file_name_label2.setText(f'{prefix2}: {display_name2}')
            self.file_name_label1.setToolTip(name1_raw if len(name1_raw or '') > max_len_ui else '')
            self.file_name_label2.setToolTip(name2_raw if len(name2_raw or '') > max_len_ui else '')
        self.check_name_lengths(name1_raw, name2_raw)

    def check_name_lengths(self, name1=None, name2=None):
        if not hasattr(self, 'length_warning_label'):
            return
        if name1 is None or name2 is None:
            name1_raw = self.edit_name1.text() if hasattr(self, 'edit_name1') and self.edit_name1.text() else self.image_list1[self.current_index1][2] if 0 <= self.current_index1 < len(self.image_list1) else ''
            name2_raw = self.edit_name2.text() if hasattr(self, 'edit_name2') and self.edit_name2.text() else self.image_list2[self.current_index2][2] if 0 <= self.current_index2 < len(self.image_list2) else ''
            name1 = name1_raw
            name2 = name2_raw
        len1 = len(name1 or '')
        len2 = len(name2 or '')
        limit = self.max_name_length
        if len1 > limit or len2 > limit:
            longest = max(len1, len2)
            warning_text = tr('Name length limit ({limit}) exceeded!', self.current_language).format(limit=limit)
            tooltip_text = tr('One or both names exceed the current limit of {limit} characters (longest is {length}).\nChange the limit in the Settings dialog.', self.current_language).format(length=longest, limit=limit)
            self.length_warning_label.setText(warning_text)
            self.length_warning_label.setToolTip(tooltip_text)
            if not self.length_warning_label.isVisible():
                self.length_warning_label.setVisible(True)
        elif self.length_warning_label.isVisible():
            self.length_warning_label.setVisible(False)
            self.length_warning_label.setToolTip('')

    def update_minimum_window_size(self):
        layout = self.layout()
        if not layout or not hasattr(self, 'image_label'):
            return
        original_policy = self.image_label.sizePolicy()
        temp_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        temp_policy.setHeightForWidth(original_policy.hasHeightForWidth())
        temp_policy.setWidthForHeight(original_policy.hasWidthForHeight())
        temp_policy.setVerticalPolicy(QSizePolicy.Policy.Preferred if original_policy.verticalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)
        temp_policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred if original_policy.horizontalPolicy() != QSizePolicy.Policy.Ignored else QSizePolicy.Policy.Ignored)
        try:
            self.image_label.setSizePolicy(temp_policy)
            self.image_label.updateGeometry()
            layout.invalidate()
            layout.activate()
            layout_hint_size = layout.sizeHint()
            img_label_min_hint = self.image_label.minimumSizeHint()
            base_min_w = 250
            base_min_h = 300
            new_min_w = max(base_min_w, layout_hint_size.width())
            new_min_h = max(base_min_h, layout_hint_size.height())
            padding = 10
            new_min_w += padding
            new_min_h += padding
            current_min = self.minimumSize()
            if current_min.width() != new_min_w or current_min.height() != new_min_h:
                self.setMinimumSize(new_min_w, new_min_h)
        except Exception as e:
            print(f'ERROR in update_minimum_window_size during calculation: {e}')
            traceback.print_exc()
        finally:
            if hasattr(self, 'image_label') and self.image_label.sizePolicy() != original_policy:
                self.image_label.setSizePolicy(original_policy)
                self.image_label.updateGeometry()
                layout.invalidate()
                layout.activate()

    def _update_drag_overlays(self):
        if not hasattr(self, 'drag_overlay1') or not hasattr(self, 'image_label') or (not self.image_label.isVisible()):
            return
        try:
            label_geom = self.image_label.geometry()
            margin = 10
            half_width = label_geom.width() // 2
            overlay_w = max(1, half_width - margin - margin // 2)
            overlay_h = max(1, label_geom.height() - 2 * margin)
            overlay1_x = margin
            overlay1_y = margin
            self.drag_overlay1.setGeometry(overlay1_x, overlay1_y, overlay_w, overlay_h)
            overlay2_x = half_width + margin // 2
            overlay2_y = margin
            self.drag_overlay2.setGeometry(overlay2_x, overlay2_y, overlay_w, overlay_h)
        except Exception as e:
            print(f'Error updating drag overlays geometry: {e}')

    def _is_in_left_area(self, pos: QPoint) -> bool:
        if not hasattr(self, 'image_label'):
            return True
        try:
            label_geom = self.image_label.geometry()
            center_x_abs = label_geom.x() + label_geom.width() // 2
            return pos.x() < center_x_abs
        except Exception as e:
            print(f'Error in _is_in_left_area: {e}')
            return True

    def _open_settings_dialog(self):
        if not settings_dialog_available or SettingsDialog is None:
            QMessageBox.warning(self, self.tr('Error', self.current_language), self.tr('Settings dialog module could not be loaded.', self.current_language) + '\n(Ensure settings_dialog.py exists and is error-free)')
            return
        dialog = SettingsDialog(current_language=self.current_language, current_max_length=self.max_name_length, min_limit=self.MIN_NAME_LENGTH_LIMIT, max_limit=self.MAX_NAME_LENGTH_LIMIT, current_jpeg_quality=self.jpeg_quality, parent=self, tr_func=tr)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            try:
                new_lang, new_max_length_from_dialog, new_jpeg_quality_from_dialog = dialog.get_settings()
                new_max_length_validated = max(self.MIN_NAME_LENGTH_LIMIT, min(self.MAX_NAME_LENGTH_LIMIT, new_max_length_from_dialog))
                length_changed = False
                if new_max_length_validated != self.max_name_length:
                    self.max_name_length = new_max_length_validated
                    self.save_setting('max_name_length', self.max_name_length)
                    length_changed = True
                    print(f'Max name length changed to: {self.max_name_length}')
                    self.update_file_names()
                    self.check_name_lengths()
                new_jpeg_quality_validated = max(1, min(100, new_jpeg_quality_from_dialog))
                jpeg_quality_changed = False
                if new_jpeg_quality_validated != self.jpeg_quality:
                    self.jpeg_quality = new_jpeg_quality_validated
                    self.save_setting('jpeg_quality', self.jpeg_quality)
                    jpeg_quality_changed = True
                    print(f'JPEG quality changed to: {self.jpeg_quality}')
                if new_lang != self.current_language:
                    self.change_language(new_lang)
            except AttributeError:
                QMessageBox.warning(self, self.tr('Error', self.current_language), 'Failed to get settings from dialog (get_settings method missing or incorrect?).')
            except Exception as e:
                QMessageBox.warning(self, self.tr('Error', self.current_language), f'Error processing settings dialog results: {e}')
                traceback.print_exc()
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageComparisonApp()
    window.show()
    sys.exit(app.exec())
