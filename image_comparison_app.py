import base64
import os
import math
import sys
import importlib
import traceback

from PIL import Image
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QCheckBox, QSlider, QLabel,
                             QFileDialog, QSizePolicy, QMessageBox, QLineEdit, QInputDialog, QApplication,
                             QColorDialog, QComboBox)
from PyQt6.QtGui import QPixmap, QIcon, QFont, QColor, QPainter, QBrush, QPen
from PyQt6.QtCore import (Qt, QPoint, QTimer, QPointF, QRect, QEvent, QSize, QSettings, QLocale,
                          QElapsedTimer, QRectF, QByteArray)


placeholder_dir = "placeholders"

def load_module(mod_name, create_placeholder=True):
    """Пытается импортировать или перезагрузить модуль, создает плейсхолдер при необходимости."""
    global placeholder_dir
    main_path = f"{mod_name}.py"
    placeholder_path = os.path.join(placeholder_dir, main_path)
    needs_reload = False
    placeholder_created = False

    if not os.path.exists(main_path):
        needs_reload = True
        if create_placeholder:
            os.makedirs(placeholder_dir, exist_ok=True)
            content = ""
            if mod_name == 'translations':
                content = "def tr(text, lang='en', *args, **kwargs):\n    return text\n"
            elif mod_name == 'flag_icons':
                content = "FLAG_ICONS = {}\n"
            elif mod_name == 'image_processing':
                 content = ("from PyQt6.QtCore import QPoint, QPointF\n"
                           "from PIL import Image, ImageDraw, ImageFont\n"
                           "import math\n"
                           "class ImageProcessingError(Exception): pass\n"
                           "def resize_images_processor(app): pass\n"
                           "def update_comparison_processor(app): pass\n"
                           "def save_result_processor(app): pass\n"
                           "def display_result_processor(app): pass\n"
                           "def get_scaled_pixmap_dimensions(app): return 0, 0\n"
                           "def get_original_coords(app): return None, None, None\n"
                           "def draw_split_line_pil(draw, image, split_pos_ratio, is_horizontal, split_color=(0,0,0,128)): pass\n"
                           "def draw_magnifier_pil(draw, image_to_draw_on, image1, image2, orig1_size, orig2_size, "
                           "capture_pos1, capture_pos2, magnifier_midpoint_result, base_capture_size, magnifier_size, edge_spacing_input, app): pass\n"
                           "def draw_file_names_on_image(self, draw, image, split_position_abs, orig_width, orig_height, line_width, line_height, text_color_tuple): pass\n")
            elif mod_name == 'clickable_label':
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

            try:
                with open(placeholder_path, 'w', encoding='utf-8') as f: f.write(content)
                import shutil
                shutil.copy2(placeholder_path, main_path)
                placeholder_created = True
            except Exception as e:
                print(f"Error creating placeholder {main_path}: {e}")
                return None
        else:
             print(f"Error: Module file not found and placeholder creation disabled: {main_path}")
             return None

    try:
        if mod_name in sys.modules and (needs_reload or placeholder_created):
            module = importlib.reload(sys.modules[mod_name])
        else:
            module = importlib.import_module(mod_name)
        return module
    except ImportError as e:
        print(f"Error importing/reloading module {mod_name}: {e}")
        traceback.print_exc()
        return None
    except Exception as e:
        print(f"Unexpected error importing/reloading module {mod_name}: {e}")
        traceback.print_exc()
        return None


translations_mod = load_module('translations')
flag_icons_mod = load_module('flag_icons')
image_processing_mod = load_module('image_processing')
clickable_label_mod = load_module('clickable_label')

if not all([translations_mod, flag_icons_mod, image_processing_mod, clickable_label_mod]):
    print("Critical error: Could not load required modules. Exiting.")
    try:
        temp_app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "Startup Error", "Critical error: Could not load required Python modules (translations, flag_icons, image_processing, clickable_label).\nCheck console output and ensure files exist.\nExiting.")
    except:
        pass
    sys.exit(1)


tr = getattr(translations_mod, 'tr', lambda text, lang='en', *args, **kwargs: text)
FLAG_ICONS = getattr(flag_icons_mod, 'FLAG_ICONS', {})
resize_images_processor = getattr(image_processing_mod, 'resize_images_processor', lambda app: None)
update_comparison_processor = getattr(image_processing_mod, 'update_comparison_processor', lambda app: None)
save_result_processor = getattr(image_processing_mod, 'save_result_processor', lambda app: None)
get_scaled_pixmap_dimensions = getattr(image_processing_mod, 'get_scaled_pixmap_dimensions', lambda app: (0,0))
get_original_coords = getattr(image_processing_mod, 'get_original_coords', lambda app: (None, None, None))
ClickableLabel = getattr(clickable_label_mod, 'ClickableLabel', QLabel)


font_file = 'SourceSans3-Regular.ttf'
font_placeholder = os.path.join(placeholder_dir, font_file)
if not os.path.exists(font_file):
    os.makedirs(placeholder_dir, exist_ok=True)
    try:
        with open(font_placeholder, 'w') as f: pass
        import shutil
        shutil.copy2(font_placeholder, font_file)
    except Exception as e:
        print(f"Warning: Could not create placeholder font file {font_file}: {e}")

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

        self._update_combobox(1)
        self._update_combobox(2)
        QTimer.singleShot(0, self._perform_initial_image_setup)


    def _perform_initial_image_setup(self):
        """Sets initial images and performs first render after UI is shown."""
        self._set_current_image(1, trigger_update=False)
        self._set_current_image(2, trigger_update=False)

        self.update_file_names()
        self.update_minimum_window_size()
        self.update_comparison_if_needed()


    def _load_settings(self):
        """Loads settings from QSettings with type conversion handling."""
        self.settings = QSettings("MyCompany", "ImageComparisonApp")

        def get_setting(key, default, target_type):
            value = self.settings.value(key, default)
            if value is None: return default
            try:
                if target_type == int: return int(value) if isinstance(value, (int, str, float)) else default
                elif target_type == float: return float(value) if isinstance(value, (int, float, str)) else default
                elif target_type == bool:
                    if isinstance(value, str):
                        if value.lower() == 'true': return True
                        if value.lower() == 'false': return False
                    return bool(value) if isinstance(value, (bool, int)) else default
                elif target_type == str: return str(value)
                elif target_type == QColor:
                    color_val = str(value)
                    if QColor.isValidColorName(color_val): return QColor(color_val)
                    test_color = QColor(color_val)
                    if test_color.isValid(): return test_color
                    try:
                         if color_val.startswith('#') and len(color_val) == 9:
                             return QColor(color_val)
                    except: pass
                    return default
                elif target_type == QByteArray:
                     if isinstance(value, QByteArray): return value
                     try:
                         if isinstance(value, str):
                              return QByteArray.fromBase64(value.encode())
                         elif isinstance(value, (bytes, bytearray)):
                              return QByteArray(value)
                         return default
                     except:
                         return default
                return value
            except (ValueError, TypeError) as e:
                 return default

        self.capture_pos_rel_x = get_setting("capture_relative_x", 0.5, float)
        self.capture_pos_rel_y = get_setting("capture_relative_y", 0.5, float)

        saved_lang = get_setting("language", None, str)
        if isinstance(saved_lang, bytes): saved_lang = saved_lang.decode('utf-8', errors='ignore')

        default_lang = QLocale.system().name()[:2]
        if default_lang not in ['en', 'ru', 'zh']: default_lang = 'en'
        self.loaded_language = saved_lang if saved_lang in ['en', 'ru', 'zh'] else default_lang

        self.loaded_max_name_length = get_setting("max_name_length", 30, int)

        self.loaded_file_names_state = get_setting("include_file_names", False, bool)

        self.loaded_movement_speed = get_setting("movement_speed_per_sec", 150, int)

        geom_raw = self.settings.value("window_geometry")
        self.loaded_geometry = None
        if isinstance(geom_raw, QByteArray):
            self.loaded_geometry = geom_raw
        elif isinstance(geom_raw, str):
            try: self.loaded_geometry = QByteArray.fromBase64(geom_raw.encode())
            except: pass
        elif isinstance(geom_raw, (bytes, bytearray)):
            self.loaded_geometry = QByteArray(geom_raw)


        default_color = QColor(255, 0, 0, 255)
        self.loaded_filename_color_name = get_setting("filename_color", default_color.name(QColor.NameFormat.HexArgb), str)

        self.loaded_image1_paths = []
        self.loaded_image2_paths = []
        self.loaded_current_index1 = -1
        self.loaded_current_index2 = -1



    def _init_state(self):
        """Initializes internal application state variables."""
        self.image_list1 = []
        self.image_list2 = []

        self._preload_images(1, self.loaded_image1_paths)
        self._preload_images(2, self.loaded_image2_paths)

        self.current_index1 = self.loaded_current_index1
        self.current_index2 = self.loaded_current_index2
        if self.current_index1 != -1 and not (0 <= self.current_index1 < len(self.image_list1)):
             self.current_index1 = -1
        if self.current_index2 != -1 and not (0 <= self.current_index2 < len(self.image_list2)):
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
        self.freeze_magnifier = False
        self.split_position = 0.5

        default_magnifier_offset_x = 0.0
        default_magnifier_offset_y = -100.0
        default_magnifier_spacing = 10.0
        default_magnifier_size = 150
        default_capture_size = 150

        self.magnifier_offset_float = QPointF(default_magnifier_offset_x, default_magnifier_offset_y)
        self.magnifier_offset_float_visual = QPointF(default_magnifier_offset_x, default_magnifier_offset_y)
        self.magnifier_offset_pixels = QPoint(round(default_magnifier_offset_x), round(default_magnifier_offset_y))

        self.MIN_MAGNIFIER_SPACING = 0.0
        clamped_default_spacing = max(self.MIN_MAGNIFIER_SPACING, default_magnifier_spacing)
        self.magnifier_spacing = round(clamped_default_spacing)
        self._magnifier_spacing_float = clamped_default_spacing
        self._magnifier_spacing_float_visual = clamped_default_spacing

        self.magnifier_size = max(50, default_magnifier_size)
        self.capture_size = max(10, default_capture_size)

        self.capture_position_relative = QPointF(self.capture_pos_rel_x, self.capture_pos_rel_y)

        self.frozen_magnifier_position_relative = None

        self.movement_speed_per_sec = max(10, self.loaded_movement_speed)

        self.smoothing_factor_pos = 0.25
        self.smoothing_factor_spacing = 0.25
        self.lerp_stop_threshold = 0.1
        self.max_target_delta_per_tick = 15.0

        self.current_language = self.loaded_language
        self.max_name_length = max(10, self.loaded_max_name_length)
        self.resize_in_progress = False
        self.previous_geometry = None
        self.pixmap_width = 0
        self.pixmap_height = 0
        self.active_keys = set()
        self._is_dragging_split_line = False
        self.file_name_color = QColor(self.loaded_filename_color_name)
        if not self.file_name_color.isValid():
            print(f"Warning: Loaded filename color '{self.loaded_filename_color_name}' is invalid. Using default red.")
            self.file_name_color = QColor(255, 0, 0, 255)



    def _preload_images(self, image_number, paths):
        """Загружает изображения из списка путей при запуске.
           ПРИМЕЧАНИЕ: paths теперь всегда будет пустым из-за изменений в _load_settings."""
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        target_list.clear()
        if not isinstance(paths, list):
             paths = []

        for file_path in paths:
             if isinstance(file_path, str) and os.path.isfile(file_path):
                 try:
                     with Image.open(file_path) as img:
                         temp_image = img.copy()
                         if temp_image.mode != 'RGBA':
                             temp_image = temp_image.convert('RGBA')
                         else:
                             temp_image.load()

                     display_name = os.path.basename(file_path)
                     target_list.append((temp_image, file_path, display_name))
                 except FileNotFoundError:
                      print(f"Warning: Preload path not found during load: {file_path}")
                 except Exception as e:
                     print(f"Warning: Failed to preload image {file_path}: {e}")
             else:
                 print(f"Warning: Preload path invalid or not a file: {file_path}")


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
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        self.setAcceptDrops(True)
        self._init_drag_overlays()
        self._init_warning_label()
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
        main_layout.addWidget(self._create_image_label())
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
        self.btn_swap = QPushButton('⇄')
        self.btn_swap.setFixedSize(24, 24)
        self.btn_swap.setToolTip(tr('Swap Image Lists', self.current_language))
        layout.addWidget(self.btn_image1)
        layout.addWidget(self.btn_swap)
        layout.addWidget(self.btn_image2)
        return layout

    def _create_combobox_layout(self):
        """Создает layout с QComboBox для выбора изображений."""
        layout = QHBoxLayout()
        self.combo_image1 = QComboBox()
        self.combo_image2 = QComboBox()
        layout.addWidget(self.combo_image1)
        layout.addWidget(self.combo_image2)
        return layout

    def _create_checkbox_layout(self):
        layout = QHBoxLayout(); self.checkbox_horizontal = QCheckBox(); self.checkbox_magnifier = QCheckBox(); self.freeze_button = QCheckBox(); self.checkbox_file_names = QCheckBox()
        self.help_button = QPushButton('?'); self.help_button.setFixedSize(24, 24); self.help_button.setToolTip(tr("Show Help", self.current_language))
        self.lang_en, self.lang_ru, self.lang_zh = self._create_language_checkboxes()
        layout.addWidget(self.checkbox_horizontal); layout.addWidget(self.checkbox_magnifier); layout.addWidget(self.freeze_button); layout.addWidget(self.checkbox_file_names)
        layout.addStretch(); layout.addWidget(self.lang_en); layout.addWidget(self.lang_ru); layout.addWidget(self.lang_zh); layout.addWidget(self.help_button); return layout

    def _create_language_checkboxes(self):
        en, ru, zh = QCheckBox(), QCheckBox(), QCheckBox()
        flags = {'en': en, 'ru': ru, 'zh': zh}
        size = QSize(24, 16); style = 'QCheckBox{padding:2px;border:none;}QCheckBox::indicator{width:24px;height:16px;}'
        for code, cb in flags.items():
            tooltip_key = f"Switch language to {'English' if code == 'en' else 'Русский' if code == 'ru' else '中文'}"
            cb.setToolTip(tr(tooltip_key, self.current_language))
            if code in FLAG_ICONS:
                icon = self._create_flag_icon(FLAG_ICONS[code])
                if not icon.isNull():
                    cb.setIcon(icon)
            cb.setIconSize(size); cb.setText(''); cb.setStyleSheet(style)
        return en, ru, zh

    def _create_slider_layout(self):
        layout = QHBoxLayout(); self.label_magnifier_size = QLabel(); self.slider_size = QSlider(Qt.Orientation.Horizontal, minimum=50, maximum=400)
        self.label_capture_size = QLabel(); self.slider_capture = QSlider(Qt.Orientation.Horizontal, minimum=10, maximum=500)
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
        layout = QHBoxLayout(); self.file_name_label1 = QLabel("--"); self.file_name_label2 = QLabel("--")
        self.file_name_label1.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.file_name_label2.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
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
        rect = QRectF(0.5, 0.5, size.width() - 1, size.height() - 1); num_segments = 12; angle_step = 360 / num_segments
        for i in range(num_segments):
            color = QColor.fromHsvF(i / num_segments, 1.0, 1.0, 1.0); painter.setBrush(QBrush(color))
            painter.drawPie(rect, int((i * angle_step + angle_step/2 - 90) * 16), int(angle_step) * 16)
        painter.end(); return QIcon(pixmap)

    def _create_save_button(self):
        self.btn_save = QPushButton(); return self.btn_save

    def _apply_initial_settings_to_ui(self):
        if hasattr(self, 'slider_size'): self.slider_size.setValue(self.magnifier_size)
        if hasattr(self, 'slider_capture'): self.slider_capture.setValue(self.capture_size)
        if hasattr(self, 'slider_speed'): self.slider_speed.setValue(self.movement_speed_per_sec)

        if hasattr(self, 'checkbox_file_names'):
            self.checkbox_file_names.setChecked(self.loaded_file_names_state)

        if hasattr(self, 'edit_layout'):
            self.toggle_edit_layout_visibility(self.loaded_file_names_state)

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

        if hasattr(self, 'slider_speed'): self.slider_speed.setToolTip(f"{self.movement_speed_per_sec} {tr('px/sec', self.current_language)}")
        if hasattr(self, 'slider_size'): self.slider_size.setToolTip(f"{self.magnifier_size} {tr('px', self.current_language)}")
        if hasattr(self, 'slider_capture'): self.slider_capture.setToolTip(f"{self.capture_size} {tr('px', self.current_language)}")

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
            self.checkbox_file_names.toggled.connect(self.toggle_edit_layout_visibility)
            self.checkbox_file_names.toggled.connect(self.update_comparison_if_needed)

        if hasattr(self, 'lang_en'): self.lang_en.toggled.connect(lambda checked: self._on_language_changed('en') if checked else None)
        if hasattr(self, 'lang_ru'): self.lang_ru.toggled.connect(lambda checked: self._on_language_changed('ru') if checked else None)
        if hasattr(self, 'lang_zh'): self.lang_zh.toggled.connect(lambda checked: self._on_language_changed('zh') if checked else None)

        if hasattr(self, 'slider_size'): self.slider_size.valueChanged.connect(self.update_magnifier_size)
        if hasattr(self, 'slider_capture'): self.slider_capture.valueChanged.connect(self.update_capture_size)
        if hasattr(self, 'slider_speed'): self.slider_speed.valueChanged.connect(self.update_movement_speed)
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
        geom_setting = self.loaded_geometry
        restored = False
        if geom_setting and isinstance(geom_setting, QByteArray):
            try:
                restored = self.restoreGeometry(geom_setting)
                if not restored:
                     print("Warning: Failed to restore geometry from settings (restoreGeometry returned false).")
            except Exception as e:
                 print(f"Error restoring geometry: {e}")
                 restored = False
        else:
            pass

        if not restored:
            self.setGeometry(100, 100, 640, 480)

        QTimer.singleShot(0, self._ensure_minimum_size_after_restore)

    def _ensure_minimum_size_after_restore(self):
        """Checks and adjusts size if current size is below minimum."""
        self.update_minimum_window_size()
        min_size = self.minimumSize()
        current_size = self.size()
        new_width = max(current_size.width(), min_size.width())
        new_height = max(current_size.height(), min_size.height())
        if new_width != current_size.width() or new_height != current_size.height():
            self.resize(new_width, new_height)


    def _init_drag_overlays(self):
        style = ("background-color: rgba(0, 100, 200, 0.6); "
                 "color: white; font-size: 20px; border-radius: 10px; "
                 "padding: 15px; border: 1px solid rgba(255, 255, 255, 0.7);")
        self.drag_overlay1 = QLabel(self); self.drag_overlay1.setAlignment(Qt.AlignmentFlag.AlignCenter); self.drag_overlay1.setStyleSheet(style); self.drag_overlay1.setWordWrap(True); self.drag_overlay1.hide()
        self.drag_overlay2 = QLabel(self); self.drag_overlay2.setAlignment(Qt.AlignmentFlag.AlignCenter); self.drag_overlay2.setStyleSheet(style); self.drag_overlay2.setWordWrap(True); self.drag_overlay2.hide()

    def _init_warning_label(self):
        self.length_warning_label = QLabel(self); self.length_warning_label.setStyleSheet("color: #FF8C00; font-weight: bold;"); self.length_warning_label.setVisible(False); self.length_warning_label.setCursor(Qt.CursorShape.PointingHandCursor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.resize_in_progress:
             self.resize_in_progress = True
        self._update_drag_overlays()
        self.resize_timer.start(200)

    def _finish_resize(self):
        if self.resize_in_progress:
            self.resize_in_progress = False
            self.update_comparison_if_needed()

    def keyPressEvent(self, event):
        key = event.key()
        is_modifier = key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta)

        if self.use_magnifier and not event.isAutoRepeat() and not is_modifier:
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

        if not event.isAutoRepeat() and not is_modifier and key in self.active_keys:
            self.active_keys.remove(key)
            event.accept()
            return

        super().keyReleaseEvent(event)

    def on_mouse_press(self, event):
        """Handles mouse presses on the image label."""
        if not self.original_image1 or not self.original_image2: return
        pos = event.position()

        if self.use_magnifier:
            if event.button() == Qt.MouseButton.LeftButton:
                 self._update_split_or_capture_position(pos)
        else:
            if event.button() == Qt.MouseButton.LeftButton:
                 self._is_dragging_split_line = True
                 self._update_split_or_capture_position(pos)

    def on_mouse_move(self, event):
        """Handles mouse movements over the image label."""
        if self.resize_in_progress: return
        if not self.original_image1 or not self.original_image2: return

        pos = event.position()

        if event.buttons() & Qt.MouseButton.LeftButton:
            if self.use_magnifier:
                 self._update_split_or_capture_position(pos)
            elif self._is_dragging_split_line:
                 self._update_split_or_capture_position(pos)


    def on_mouse_release(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._is_dragging_split_line:
                self._is_dragging_split_line = False
            elif self.use_magnifier:
                pass

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._update_drag_overlays()
            self.drag_overlay1.setText(tr("Drop Image(s) 1 Here", self.current_language))
            self.drag_overlay2.setText(tr("Drop Image(s) 2 Here", self.current_language))
            self.drag_overlay1.show(); self.drag_overlay2.show()
            self.drag_overlay1.raise_(); self.drag_overlay2.raise_()

    def dragMoveEvent(self, event):
         if event.mimeData().hasUrls():
              event.acceptProposedAction()
         else:
              event.ignore()

    def dragLeaveEvent(self, event):
        self.drag_overlay1.hide(); self.drag_overlay2.hide()

    def dropEvent(self, event):
        """Обрабатывает перетаскивание файлов, теперь может добавлять несколько."""
        self.drag_overlay1.hide(); self.drag_overlay2.hide()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if not urls: return

            file_paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            valid_paths = []
            invalid_found = False
            unsupported_found = False


            for file_path in file_paths:
                if os.path.isfile(file_path):
                    ext = os.path.splitext(file_path)[1].lower()
                    if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'):
                        valid_paths.append(file_path)
                    else:
                        print(f"Unsupported file type: {file_path}")
                        unsupported_found = True
                else:
                    print(f"Invalid path (not a file): {file_path}")
                    invalid_found = True

            if invalid_found:
                QMessageBox.warning(self, tr("Warning", self.current_language), tr("One or more paths were invalid.", self.current_language))
            if unsupported_found:
                QMessageBox.warning(self, tr("Warning", self.current_language), tr("One or more files had unsupported types (supported: png, jpg, bmp, webp, tif).", self.current_language))

            if valid_paths:
                 drop_point = event.position().toPoint()
                 target_image_num = 1 if self._is_in_left_area(drop_point) else 2
                 self._load_images_from_paths(valid_paths, target_image_num)
            else:
                 pass


    def changeEvent(self, event):
        """Handles language changes and window state changes."""
        if event.type() == QEvent.Type.LanguageChange:
            self.update_translations()
        elif event.type() == QEvent.Type.WindowStateChange:
            old_state = event.oldState()
            new_state = self.windowState()
            is_maximized = new_state & Qt.WindowState.WindowMaximized
            is_fullscreen = new_state & Qt.WindowState.WindowFullScreen
            was_maximized = old_state & Qt.WindowState.WindowMaximized
            was_fullscreen = old_state & Qt.WindowState.WindowFullScreen


            if (is_maximized or is_fullscreen) and not (was_maximized or was_fullscreen):
                if not self.previous_geometry:
                     self.previous_geometry = self.saveGeometry()
            elif not (is_maximized or is_fullscreen) and (was_maximized or was_fullscreen):
                if self.previous_geometry:
                    try:
                        if not self.restoreGeometry(self.previous_geometry):
                            print("Warning: Failed to restore previous geometry after leaving max/fullscreen.")
                    except Exception as e:
                        print(f"Error restoring previous geometry: {e}")
                    self.previous_geometry = None
                    QTimer.singleShot(50, self.update_comparison_if_needed)
                else:
                    print("Warning: Was maximized/fullscreen, but no previous geometry to restore.")

        super().changeEvent(event)


    def closeEvent(self, event):
        """Saves settings on application close."""
        geometry_to_save = None
        is_maximized = self.windowState() & Qt.WindowState.WindowMaximized
        is_fullscreen = self.windowState() & Qt.WindowState.WindowFullScreen

        if not (is_maximized or is_fullscreen):
            geometry_to_save = self.saveGeometry()
        elif self.previous_geometry:
             geometry_to_save = self.previous_geometry
        else:
             geometry_to_save = self.saveGeometry()
             print("Warning: Saving maximized/fullscreen geometry as previous geometry was lost.")

        if isinstance(geometry_to_save, QByteArray):
            geom_b64 = geometry_to_save.toBase64().data().decode()
            self.save_setting("window_geometry", geom_b64)
        elif geometry_to_save:
             print(f"Warning: Geometry to save is not QByteArray: {type(geometry_to_save)}")
             self.save_setting("window_geometry", geometry_to_save)
        else:
             print("Warning: Could not get valid geometry to save.")


        self.save_setting("capture_relative_x", self.capture_position_relative.x())
        self.save_setting("capture_relative_y", self.capture_position_relative.y())


        self.save_setting("movement_speed_per_sec", self.movement_speed_per_sec)
        self.save_setting("language", self.current_language)
        self.save_setting("max_name_length", self.max_name_length)

        if hasattr(self, 'checkbox_file_names'):
            self.save_setting("include_file_names", self.checkbox_file_names.isChecked())

        self.save_setting("filename_color", self.file_name_color.name(QColor.NameFormat.HexArgb))

        try:
            self.settings.remove("image1_paths")
            self.settings.remove("image2_paths")
            self.settings.remove("current_index1")
            self.settings.remove("current_index2")
            self.settings.remove("magnifier_offset_pixels_x")
            self.settings.remove("magnifier_offset_pixels_y")
            self.settings.remove("magnifier_spacing")
            self.settings.remove("magnifier_size")
            self.settings.remove("capture_size")
        except Exception as e:
            print(f"Error removing settings: {e}")

        super().closeEvent(event)

    def update_comparison(self):
        """Triggers the processor to update the comparison image and display it."""
        if self.resize_in_progress:
             return

        if self.image1 and self.image2:
            try:
                update_comparison_processor(self)
            except Exception as e:
                print(f"Error during update_comparison_processor: {e}")
                traceback.print_exc()
                QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to update comparison view:', self.current_language)}\n{e}")
        elif not self.original_image1 or not self.original_image2:
             self.image_label.clear()
             self.result_image = None
             self.image1 = None
             self.image2 = None

    def update_comparison_if_needed(self):
        """Checks if comparison can be performed and triggers resize/update."""
        if self.resize_in_progress:
             return

        if self.original_image1 and self.original_image2:
            needs_resize = False
            if not self.image1 or not self.image2:
                 needs_resize = True
            else:
                 max_w = max(self.original_image1.width, self.original_image2.width)
                 max_h = max(self.original_image1.height, self.original_image2.height)
                 if self.image1.size != (max_w, max_h) or self.image2.size != (max_w, max_h):
                      needs_resize = True

            if needs_resize:
                 resize_images_processor(self)
                 if not self.image1 or not self.image2:
                      self.image_label.clear()
                      self.result_image = None
                      return

            self.update_comparison()
        else:
             self.image_label.clear()
             self.result_image = None
             self.image1 = None
             self.image2 = None

    def load_image(self, image_number):
        """Открывает диалог для выбора *нескольких* файлов."""
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            tr(f"Select Image(s) {image_number}", self.current_language),
            "",
            tr("Image Files", self.current_language) + " (*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff);;" + tr("All Files", self.current_language) + " (*)"
        )
        if file_names:
            self._load_images_from_paths(file_names, image_number)

    def _load_images_from_paths(self, file_paths, image_number):
        """Загружает изображения из списка путей и добавляет их в соответствующий список."""
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        loaded_count = 0
        newly_added_indices = []
        paths_actually_added = []

        for file_path in file_paths:
            if any(item[1] == file_path for item in target_list):
                continue

            try:
                with Image.open(file_path) as img:
                    temp_image = img.copy()
                    if temp_image.mode != 'RGBA':
                         temp_image = temp_image.convert('RGBA')
                    else:
                         temp_image.load()

                display_name = os.path.basename(file_path)
                target_list.append((temp_image, file_path, display_name))
                newly_added_indices.append(len(target_list) - 1)
                paths_actually_added.append(file_path)
                loaded_count += 1
            except Exception as e:
                print(f"Failed to load image: {file_path}\nError: {e}")
                traceback.print_exc()
                QMessageBox.warning(self, tr("Error", self.current_language), f"{tr('Failed to load image:', self.current_language)}\n{file_path}\n{e}")

        if loaded_count > 0:
            self._update_combobox(image_number)

            if newly_added_indices:
                new_index = newly_added_indices[-1]

                current_cb_index = combobox.currentIndex()
                needs_manual_set = (current_cb_index != new_index)

                if needs_manual_set:
                     combobox.blockSignals(True)
                     combobox.setCurrentIndex(new_index)
                     combobox.blockSignals(False)

                if image_number == 1:
                    if self.current_index1 != new_index:
                         self.current_index1 = new_index
                         self._set_current_image(1, trigger_update=True)
                    elif not needs_manual_set:
                         self._set_current_image(1, trigger_update=True)
                else:
                    if self.current_index2 != new_index:
                        self.current_index2 = new_index
                        self._set_current_image(2, trigger_update=True)
                    elif not needs_manual_set:
                        self._set_current_image(2, trigger_update=True)
            else:
                 print("Warning: loaded_count > 0 but newly_added_indices is empty.")

        elif not file_paths:
             pass
        else:
             pass


    def _set_current_image(self, image_number, trigger_update=True):
        """Устанавливает self.original_imageX и связанные переменные на основе текущего индекса."""
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_index = self.current_index1 if image_number == 1 else self.current_index2
        edit_name_widget = self.edit_name1 if image_number == 1 else self.edit_name2

        old_orig1_size = self.original_image1.size if self.original_image1 else None
        old_orig2_size = self.original_image2.size if self.original_image2 else None

        reset_image = True
        new_pil_img = None
        new_path = None
        new_display_name = None

        if 0 <= current_index < len(target_list):
            try:
                new_pil_img, new_path, new_display_name = target_list[current_index]
                reset_image = False
            except IndexError:
                 print(f"Error: Index {current_index} out of range for image list {image_number}.")
                 reset_image = True
            except Exception as e:
                print(f"Error accessing image {image_number} at index {current_index}: {e}")
                reset_image = True

        if reset_image:
            if image_number == 1:
                self.original_image1 = None
                self.image1_path = None
                self.image1 = None
            else:
                self.original_image2 = None
                self.image2_path = None
                self.image2 = None
            if edit_name_widget: edit_name_widget.clear()
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
                edit_name_widget.setText(new_display_name)
                edit_name_widget.blockSignals(False)


        new_orig1_size = self.original_image1.size if self.original_image1 else None
        new_orig2_size = self.original_image2.size if self.original_image2 else None

        max_dims_changed = False
        old_max_w, old_max_h = -1, -1
        new_max_w, new_max_h = -1, -1

        if old_orig1_size or old_orig2_size:
             old_max_w = max(old_orig1_size[0] if old_orig1_size else 0, old_orig2_size[0] if old_orig2_size else 0)
             old_max_h = max(old_orig1_size[1] if old_orig1_size else 0, old_orig2_size[1] if old_orig2_size else 0)
        if new_orig1_size or new_orig2_size:
             new_max_w = max(new_orig1_size[0] if new_orig1_size else 0, new_orig2_size[0] if new_orig2_size else 0)
             new_max_h = max(new_orig1_size[1] if new_orig1_size else 0, new_orig2_size[1] if new_orig2_size else 0)

        if old_max_w != new_max_w or old_max_h != new_max_h:
            max_dims_changed = True


        if self.original_image1 and self.original_image2:
            resize_images_processor(self)
            if trigger_update:
                self.update_comparison()
            else:
                pass
        elif trigger_update:
            self.image_label.clear()
            self.result_image = None
            self.image1 = None
            self.image2 = None
        else:
             pass

        self.update_file_names()


    def _update_combobox(self, image_number):
        """Обновляет элементы в QComboBox на основе соответствующего image_list."""
        combobox = self.combo_image1 if image_number == 1 else self.combo_image2
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_index = self.current_index1 if image_number == 1 else self.current_index2

        combobox.blockSignals(True)
        combobox.clear()
        for i, (_, _, display_name) in enumerate(target_list):
            max_cb_len = 60
            cb_name = (display_name[:max_cb_len-3] + "...") if len(display_name) > max_cb_len else display_name
            combobox.addItem(cb_name)


        new_index = -1
        if 0 <= current_index < len(target_list):
            new_index = current_index
        elif len(target_list) > 0:
             new_index = 0
        else:
            pass

        if new_index != -1:
            combobox.setCurrentIndex(new_index)

        if image_number == 1:
            if self.current_index1 != new_index:
                self.current_index1 = new_index
        else:
            if self.current_index2 != new_index:
                self.current_index2 = new_index

        combobox.blockSignals(False)


    def _on_combobox_changed(self, image_number, index):
        """Обработчик смены выбора в QComboBox."""
        target_list = self.image_list1 if image_number == 1 else self.image_list2
        current_internal_index = self.current_index1 if image_number == 1 else self.current_index2

        if 0 <= index < len(target_list):
            if index != current_internal_index:
                if image_number == 1:
                    self.current_index1 = index
                else:
                    self.current_index2 = index
                self._set_current_image(image_number, trigger_update=True)
            else:
                pass
        elif index == -1 and current_internal_index != -1:
             if image_number == 1:
                 self.current_index1 = -1
             else:
                 self.current_index2 = -1
             self._set_current_image(image_number, trigger_update=True)
        else:
             pass


    def _on_edit_name_changed(self):
        """Обновляет имя в списке и комбо-боксе при завершении редактирования в QLineEdit."""
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
            if not new_name:
                 print(f"Warning: Empty name entered for image {image_number}, ignoring change.")
                 _, _, old_name = target_list[current_index]
                 sender_widget.blockSignals(True)
                 sender_widget.setText(old_name)
                 sender_widget.blockSignals(False)
                 return

            try:
                old_img, old_path, old_name = target_list[current_index]
                if new_name != old_name:
                    target_list[current_index] = (old_img, old_path, new_name)

                    combobox.blockSignals(True)
                    max_cb_len = 60
                    cb_name = (new_name[:max_cb_len-3] + "...") if len(new_name) > max_cb_len else new_name
                    combobox.setItemText(current_index, cb_name)
                    combobox.blockSignals(False)

                    self.update_file_names()
                else:
                    pass

            except IndexError:
                 print(f"Error: Index {current_index} out of range when editing name for image {image_number}.")
            except Exception as e:
                 print(f"Error updating name for image {image_number}: {e}")
                 traceback.print_exc()


    def swap_images(self):
        self.image_list1, self.image_list2 = self.image_list2, self.image_list1
        self.current_index1, self.current_index2 = self.current_index2, self.current_index1

        self._update_combobox(1)
        self._update_combobox(2)

        self._set_current_image(1, trigger_update=False)
        self._set_current_image(2, trigger_update=True)

    def _save_result_with_error_handling(self):
        try:
            if not self.original_image1 or not self.original_image2:
                 QMessageBox.warning(self, tr("Warning", self.current_language), tr("Please load and select images in both slots first.", self.current_language))
                 return
            if not self.image1 or not self.image2:
                 QMessageBox.warning(self, tr("Warning", self.current_language), tr("Resized images not available. Please reload or select images.", self.current_language))
                 return

            save_result_processor(self)
        except Exception as e:
            print(f"ERROR during save_result_processor: {e}")
            traceback.print_exc()
            QMessageBox.critical(self, tr("Error", self.current_language), f"{tr('Failed to save image:', self.current_language)}\n{str(e)}")


    def _update_magnifier_position_by_keys(self):
        """Updates magnifier target offset and visual offset based on active keys and interpolation."""
        current_elapsed = self.movement_elapsed_timer.elapsed()
        delta_time_ms = current_elapsed - self.last_update_elapsed
        if delta_time_ms <= 0 or delta_time_ms > 100:
            delta_time_ms = self.movement_timer.interval()
        delta_time_sec = delta_time_ms / 1000.0
        self.last_update_elapsed = current_elapsed

        epsilon = 1e-6

        target_pos_changed = False
        target_spacing_changed = False
        raw_dx, raw_dy, raw_ds = 0.0, 0.0, 0.0

        spacing_speed_per_sec_qe = 300

        if self.active_keys:
            dx_dir = (Qt.Key.Key_D in self.active_keys) - (Qt.Key.Key_A in self.active_keys)
            dy_dir = (Qt.Key.Key_S in self.active_keys) - (Qt.Key.Key_W in self.active_keys)
            ds_dir = (Qt.Key.Key_E in self.active_keys) - (Qt.Key.Key_Q in self.active_keys)

            length_sq = dx_dir*dx_dir + dy_dir*dy_dir
            if length_sq > 1.0 + 1e-6:
                 inv_length = 1.0 / math.sqrt(length_sq)
                 dx_dir *= inv_length
                 dy_dir *= inv_length

            raw_dx = dx_dir * self.movement_speed_per_sec * delta_time_sec
            raw_dy = dy_dir * self.movement_speed_per_sec * delta_time_sec
            raw_ds = ds_dir * spacing_speed_per_sec_qe * delta_time_sec

            clamped_dx = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_dx))
            clamped_dy = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_dy))
            clamped_ds = max(-self.max_target_delta_per_tick, min(self.max_target_delta_per_tick, raw_ds))

            if abs(clamped_dx) > epsilon or abs(clamped_dy) > epsilon:
                 if self.freeze_magnifier:
                     if self.frozen_magnifier_position_relative and self.pixmap_width > 0 and self.pixmap_height > 0:
                         dx_rel = clamped_dx / self.pixmap_width
                         dy_rel = clamped_dy / self.pixmap_height
                         new_x = max(0.0, min(1.0, self.frozen_magnifier_position_relative.x() + dx_rel))
                         new_y = max(0.0, min(1.0, self.frozen_magnifier_position_relative.y() + dy_rel))
                         if not math.isclose(new_x, self.frozen_magnifier_position_relative.x(), abs_tol=epsilon) or \
                            not math.isclose(new_y, self.frozen_magnifier_position_relative.y(), abs_tol=epsilon):
                             self.frozen_magnifier_position_relative.setX(new_x)
                             self.frozen_magnifier_position_relative.setY(new_y)
                             target_pos_changed = True
                 else:
                     new_target_x = self.magnifier_offset_float.x() + clamped_dx
                     new_target_y = self.magnifier_offset_float.y() + clamped_dy
                     if not math.isclose(new_target_x, self.magnifier_offset_float.x(), abs_tol=epsilon) or \
                        not math.isclose(new_target_y, self.magnifier_offset_float.y(), abs_tol=epsilon):
                          self.magnifier_offset_float.setX(new_target_x)
                          self.magnifier_offset_float.setY(new_target_y)
                          target_pos_changed = True

            if abs(clamped_ds) > epsilon:
                new_target_spacing = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float + clamped_ds)
                if not math.isclose(new_target_spacing, self._magnifier_spacing_float, abs_tol=epsilon):
                    self._magnifier_spacing_float = new_target_spacing
                    target_spacing_changed = True

        visual_pos_moved = False
        if not self.freeze_magnifier:
            delta_vx = self.magnifier_offset_float.x() - self.magnifier_offset_float_visual.x()
            delta_vy = self.magnifier_offset_float.y() - self.magnifier_offset_float_visual.y()

            if abs(delta_vx) < self.lerp_stop_threshold and abs(delta_vy) < self.lerp_stop_threshold:
                if not math.isclose(self.magnifier_offset_float_visual.x(), self.magnifier_offset_float.x()) or \
                   not math.isclose(self.magnifier_offset_float_visual.y(), self.magnifier_offset_float.y()):
                    self.magnifier_offset_float_visual.setX(self.magnifier_offset_float.x())
                    self.magnifier_offset_float_visual.setY(self.magnifier_offset_float.y())
                    visual_pos_moved = True
            else:
                new_visual_x = self.magnifier_offset_float_visual.x() + delta_vx * self.smoothing_factor_pos
                new_visual_y = self.magnifier_offset_float_visual.y() + delta_vy * self.smoothing_factor_pos
                self.magnifier_offset_float_visual.setX(new_visual_x)
                self.magnifier_offset_float_visual.setY(new_visual_y)
                visual_pos_moved = True


        visual_spacing_moved = False
        target_spacing_clamped = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float)
        delta_vs = target_spacing_clamped - self._magnifier_spacing_float_visual

        if abs(delta_vs) < self.lerp_stop_threshold:
             if not math.isclose(self._magnifier_spacing_float_visual, target_spacing_clamped):
                  self._magnifier_spacing_float_visual = target_spacing_clamped
                  visual_spacing_moved = True
        else:
             new_visual_spacing = self._magnifier_spacing_float_visual + delta_vs * self.smoothing_factor_spacing
             self._magnifier_spacing_float_visual = max(self.MIN_MAGNIFIER_SPACING, new_visual_spacing)
             visual_spacing_moved = True

        needs_redraw = False
        new_offset_pixels = QPoint(round(self.magnifier_offset_float_visual.x()), round(self.magnifier_offset_float_visual.y()))
        if not self.freeze_magnifier and self.magnifier_offset_pixels != new_offset_pixels:
            self.magnifier_offset_pixels = new_offset_pixels
            needs_redraw = True

        new_spacing_int = round(self._magnifier_spacing_float_visual)
        if self.magnifier_spacing != new_spacing_int:
             self.magnifier_spacing = new_spacing_int
             needs_redraw = True

        if self.freeze_magnifier and target_pos_changed:
            needs_redraw = True

        if needs_redraw:
            if not self.resize_in_progress:
                self.update_comparison()

        if not self.active_keys:
            pos_is_close = self.freeze_magnifier or \
                           (abs(self.magnifier_offset_float.x() - self.magnifier_offset_float_visual.x()) < self.lerp_stop_threshold and
                            abs(self.magnifier_offset_float.y() - self.magnifier_offset_float_visual.y()) < self.lerp_stop_threshold)

            spacing_is_close = abs(target_spacing_clamped - self._magnifier_spacing_float_visual) < self.lerp_stop_threshold

            if pos_is_close and spacing_is_close:
                self.movement_timer.stop()

                final_offset_x_f = self.magnifier_offset_float.x()
                final_offset_y_f = self.magnifier_offset_float.y()
                final_spacing_f_clamped = target_spacing_clamped

                if not self.freeze_magnifier:
                     self.magnifier_offset_float_visual.setX(final_offset_x_f)
                     self.magnifier_offset_float_visual.setY(final_offset_y_f)
                self._magnifier_spacing_float_visual = final_spacing_f_clamped

                final_offset_pixels = QPoint(round(final_offset_x_f), round(final_offset_y_f))
                final_spacing_int_clamped = round(final_spacing_f_clamped)

                self.magnifier_offset_pixels = final_offset_pixels
                self.magnifier_spacing = final_spacing_int_clamped


    def toggle_orientation(self, state):
        new_state = (state == Qt.CheckState.Checked.value)
        if new_state != self.is_horizontal:
            self.is_horizontal = new_state
            self.update_file_names()
            self.update_comparison_if_needed()

    def toggle_magnifier(self, state):
        new_state = (state == Qt.CheckState.Checked.value)
        if new_state == self.use_magnifier: return

        self.use_magnifier = new_state
        visible = self.use_magnifier

        if hasattr(self, 'slider_size'): self.slider_size.setVisible(visible)
        if hasattr(self, 'slider_capture'): self.slider_capture.setVisible(visible)
        if hasattr(self, 'label_magnifier_size'): self.label_magnifier_size.setVisible(visible)
        if hasattr(self, 'label_capture_size'): self.label_capture_size.setVisible(visible)
        if hasattr(self, 'freeze_button'): self.freeze_button.setEnabled(visible)
        if hasattr(self, 'slider_speed'): self.slider_speed.setVisible(visible)
        if hasattr(self, 'label_movement_speed'): self.label_movement_speed.setVisible(visible)

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
        new_freeze_state = (state == Qt.CheckState.Checked.value)
        if new_freeze_state == self.freeze_magnifier: return

        if new_freeze_state:
            if self.use_magnifier and self.original_image1 and self.original_image2:
                was_frozen = self.freeze_magnifier
                self.freeze_magnifier = False
                result_width, result_height = (0, 0)
                if self.result_image:
                    result_width, result_height = self.result_image.size

                if result_width > 0 and result_height > 0:
                    cap_orig1, _, magnifier_pos_result_current = get_original_coords(self)

                    if magnifier_pos_result_current and cap_orig1:
                        rel_x = max(0.0, min(1.0, magnifier_pos_result_current.x() / result_width))
                        rel_y = max(0.0, min(1.0, magnifier_pos_result_current.y() / result_height))
                        self.frozen_magnifier_position_relative = QPointF(rel_x, rel_y)
                        self.freeze_magnifier = True
                        self.magnifier_offset_float_visual.setX(self.magnifier_offset_float.x())
                        self.magnifier_offset_float_visual.setY(self.magnifier_offset_float.y())
                        self._magnifier_spacing_float_visual = self._magnifier_spacing_float
                    else:
                         print("  Warning: Could not get valid magnifier/capture coordinates to freeze. Aborting freeze.")
                         self.frozen_magnifier_position_relative = None
                         self.freeze_magnifier = False
                         if hasattr(self, 'freeze_button'): self.freeze_button.setChecked(False)
                else:
                     print("  Warning: Cannot get magnifier coordinates, result_image invalid. Aborting freeze.")
                     self.frozen_magnifier_position_relative = None
                     self.freeze_magnifier = False
                     if hasattr(self, 'freeze_button'): self.freeze_button.setChecked(False)
            else:
                self.frozen_magnifier_position_relative = None
                self.freeze_magnifier = False
                if hasattr(self, 'freeze_button'): self.freeze_button.setChecked(False)
        else:
            self._unfreeze_magnifier_logic()

        self.update_comparison_if_needed()


    def _unfreeze_magnifier_logic(self):
        """Logic performed when unfreezing the magnifier."""
        if not self.freeze_magnifier:
            return

        frozen_pos_rel = self.frozen_magnifier_position_relative

        self.freeze_magnifier = False
        self.frozen_magnifier_position_relative = None

        new_offset_float_x = 0.0
        new_offset_float_y = 0.0

        try:
            current_scaled_width, current_scaled_height = get_scaled_pixmap_dimensions(self)
            current_result_width, current_result_height = (0, 0)
            if self.result_image:
                current_result_width, current_result_height = self.result_image.size


            if frozen_pos_rel and current_result_width > 0 and current_result_height > 0:

                frozen_x_res = frozen_pos_rel.x() * current_result_width
                frozen_y_res = frozen_pos_rel.y() * current_result_height
                frozen_point_res = QPoint(int(round(frozen_x_res)), int(round(frozen_y_res)))

                current_cap_center_res_x = int(self.capture_position_relative.x() * current_result_width)
                current_cap_center_res_y = int(self.capture_position_relative.y() * current_result_height)
                current_cap_center_res = QPoint(current_cap_center_res_x, current_cap_center_res_y)


                required_offset_res_x = frozen_point_res.x() - current_cap_center_res.x()
                required_offset_res_y = frozen_point_res.y() - current_cap_center_res.y()

                if current_scaled_width > 0 and current_scaled_height > 0:
                    scale_res_to_pix_x = float(current_scaled_width) / float(current_result_width)
                    scale_res_to_pix_y = float(current_scaled_height) / float(current_result_height)

                    new_offset_float_x = required_offset_res_x * scale_res_to_pix_x
                    new_offset_float_y = required_offset_res_y * scale_res_to_pix_y
                else:
                    pass
            else:
                 pass

        except Exception as e:
             print(f"    Error during unfreeze offset calculation: {e}")

        self.magnifier_offset_float.setX(new_offset_float_x)
        self.magnifier_offset_float.setY(new_offset_float_y)
        self.magnifier_offset_float_visual.setX(new_offset_float_x)
        self.magnifier_offset_float_visual.setY(new_offset_float_y)

        self.magnifier_offset_pixels = QPoint(round(new_offset_float_x), round(new_offset_float_y))

        cur_vis_space_clamped = max(self.MIN_MAGNIFIER_SPACING, self._magnifier_spacing_float_visual)
        self._magnifier_spacing_float = cur_vis_space_clamped
        self.magnifier_spacing = round(cur_vis_space_clamped)


        if self.active_keys and not self.movement_timer.isActive() and self.use_magnifier:
            self.movement_elapsed_timer.start()
            self.last_update_elapsed = self.movement_elapsed_timer.elapsed()
            self.movement_timer.start()


    def update_magnifier_size(self, value):
        new_size = max(50, value)
        if new_size != self.magnifier_size:
            self.magnifier_size = new_size
            if hasattr(self, 'slider_size'): self.slider_size.setToolTip(f"{self.magnifier_size} {tr('px', self.current_language)}")
            self.update_comparison_if_needed()

    def update_capture_size(self, value):
        new_size = max(10, value)
        if new_size != self.capture_size:
            self.capture_size = new_size
            if hasattr(self, 'slider_capture'): self.slider_capture.setToolTip(f"{self.capture_size} {tr('px', self.current_language)}")
            self.update_comparison_if_needed()

    def update_movement_speed(self, value):
        new_speed = max(10, value)
        if new_speed != self.movement_speed_per_sec:
            self.movement_speed_per_sec = new_speed
            self.save_setting("movement_speed_per_sec", self.movement_speed_per_sec)
            if hasattr(self, 'slider_speed'): self.slider_speed.setToolTip(f"{self.movement_speed_per_sec} {tr('px/sec', self.current_language)}")

    def toggle_edit_layout_visibility(self, checked):
        if not hasattr(self, 'edit_layout'): return
        is_visible = bool(checked)
        for i in range(self.edit_layout.count()):
            item = self.edit_layout.itemAt(i)
            if item:
                 widget = item.widget()
                 if widget:
                     widget.setVisible(is_visible)
        self.update_minimum_window_size()
        QTimer.singleShot(0, self._ensure_minimum_size_after_restore)
        if is_visible and hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            self.update_comparison_if_needed()


    def _open_color_dialog(self):
        options = QColorDialog.ColorDialogOption.ShowAlphaChannel
        color = QColorDialog.getColor(self.file_name_color, self,
                                      tr("Select Filename Color", self.current_language),
                                      options=options)
        if color.isValid():
            if color != self.file_name_color:
                 self.file_name_color = color
                 self._update_color_button_tooltip()
                 self.save_setting("filename_color", color.name(QColor.NameFormat.HexArgb))
                 if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
                      self.update_comparison_if_needed()
            else:
                 pass
        else:
            print("Invalid color selected.")


    def _update_color_button_tooltip(self):
        if hasattr(self, 'btn_color_picker'):
            tooltip_text = (f"{tr('Change Filename Color', self.current_language)}\n"
                            f"{tr('Current:', self.current_language)} {self.file_name_color.name(QColor.NameFormat.HexArgb)}")
            self.btn_color_picker.setToolTip(tooltip_text)

    def save_setting(self, key, value):
        try:
            self.settings.setValue(key, value)
        except Exception as e:
            print(f"ERROR saving setting '{key}' (value: {value}): {e}")
            traceback.print_exc()

    def change_language(self, language):
        if language not in ['en', 'ru', 'zh']:
            print(f"Unsupported language '{language}', defaulting to 'en'.")
            language = 'en'
        if language == self.current_language:
             return

        self.current_language = language
        self.update_translations()
        self.update_file_names()
        self.update_language_checkboxes()
        self.save_setting("language", language)
        if hasattr(self, 'length_warning_label'): self.check_name_lengths()
        if hasattr(self, 'help_button'): self.help_button.setToolTip(tr("Show Help", self.current_language))
        if hasattr(self, 'lang_en'): self.lang_en.setToolTip(tr("Switch language to English", self.current_language))
        if hasattr(self, 'lang_ru'): self.lang_ru.setToolTip(tr("Switch language to Русский", self.current_language))
        if hasattr(self, 'lang_zh'): self.lang_zh.setToolTip(tr("Switch language to 中文", self.current_language))


    def update_translations(self):
        self.setWindowTitle(tr('Improve ImgSLI', self.current_language))
        if hasattr(self, 'btn_image1'): self.btn_image1.setText(tr('Add Image(s) 1', self.current_language))
        if hasattr(self, 'btn_image2'): self.btn_image2.setText(tr('Add Image(s) 2', self.current_language))
        if hasattr(self, 'btn_swap'): self.btn_swap.setToolTip(tr('Swap Image Lists', self.current_language))
        if hasattr(self, 'btn_save'): self.btn_save.setText(tr('Save Result', self.current_language))
        if hasattr(self, 'checkbox_horizontal'): self.checkbox_horizontal.setText(tr('Horizontal Split', self.current_language))
        if hasattr(self, 'checkbox_magnifier'): self.checkbox_magnifier.setText(tr('Use Magnifier', self.current_language))
        if hasattr(self, 'freeze_button'): self.freeze_button.setText(tr('Freeze Magnifier', self.current_language))
        if hasattr(self, 'checkbox_file_names'): self.checkbox_file_names.setText(tr('Include file names in saved image', self.current_language))
        if hasattr(self, 'label_magnifier_size'): self.label_magnifier_size.setText(tr("Magnifier Size:", self.current_language))
        if hasattr(self, 'label_capture_size'): self.label_capture_size.setText(tr("Capture Size:", self.current_language))
        if hasattr(self, 'label_movement_speed'): self.label_movement_speed.setText(tr("Move Speed:", self.current_language))
        if hasattr(self, 'label_edit_name1'): self.label_edit_name1.setText(tr("Name 1:", self.current_language))
        if hasattr(self, 'edit_name1'): self.edit_name1.setPlaceholderText(tr("Edit Current Image 1 Name", self.current_language))
        if hasattr(self, 'label_edit_name2'): self.label_edit_name2.setText(tr("Name 2:", self.current_language))
        if hasattr(self, 'edit_name2'): self.edit_name2.setPlaceholderText(tr("Edit Current Image 2 Name", self.current_language))
        if hasattr(self, 'label_edit_font_size'): self.label_edit_font_size.setText(tr("Font Size (%):", self.current_language))

        if hasattr(self, 'combo_image1'): self.combo_image1.setToolTip(tr('Select image for left/top side', self.current_language))
        if hasattr(self, 'combo_image2'): self.combo_image2.setToolTip(tr('Select image for right/bottom side', self.current_language))

        if hasattr(self, 'slider_speed'): self.slider_speed.setToolTip(f"{self.movement_speed_per_sec} {tr('px/sec', self.current_language)}")
        if hasattr(self, 'slider_size'): self.slider_size.setToolTip(f"{self.magnifier_size} {tr('px', self.current_language)}")
        if hasattr(self, 'slider_capture'): self.slider_capture.setToolTip(f"{self.capture_size} {tr('px', self.current_language)}")
        self._update_color_button_tooltip()

        if hasattr(self, 'drag_overlay1') and self.drag_overlay1.isVisible(): self.drag_overlay1.setText(tr("Drop Image(s) 1 Here", self.current_language))
        if hasattr(self, 'drag_overlay2') and self.drag_overlay2.isVisible(): self.drag_overlay2.setText(tr("Drop Image(s) 2 Here", self.current_language))

        if hasattr(self, 'length_warning_label') and self.length_warning_label.isVisible(): self.check_name_lengths()

        self.update_file_names()


    def _on_language_changed(self, language):
        if self.current_language == language:
             cb = getattr(self, f'lang_{language}', None)
             if cb and not cb.isChecked():
                  self._block_language_checkbox_signals(True)
                  cb.setChecked(True)
                  self._block_language_checkbox_signals(False)
             return

        self._block_language_checkbox_signals(True)
        for lang_code in ['en', 'ru', 'zh']:
             if lang_code != language:
                  cb = getattr(self, f'lang_{lang_code}', None)
                  if cb: cb.setChecked(False)
        self.change_language(language)
        self._block_language_checkbox_signals(False)


    def _block_language_checkbox_signals(self, block):
        if hasattr(self, 'lang_en'): self.lang_en.blockSignals(block)
        if hasattr(self, 'lang_ru'): self.lang_ru.blockSignals(block)
        if hasattr(self, 'lang_zh'): self.lang_zh.blockSignals(block)

    def update_language_checkboxes(self):
        """Ensures only the current language checkbox is checked."""
        self._block_language_checkbox_signals(True)
        if hasattr(self, 'lang_en'): self.lang_en.setChecked(self.current_language == 'en')
        if hasattr(self, 'lang_ru'): self.lang_ru.setChecked(self.current_language == 'ru')
        if hasattr(self, 'lang_zh'): self.lang_zh.setChecked(self.current_language == 'zh')
        self._block_language_checkbox_signals(False)

    def _show_help_dialog(self):
        help_text = tr("Minimal Help Text", self.current_language)
        QMessageBox.information(self, tr("Help", self.current_language), help_text)

    def _update_split_or_capture_position(self, cursor_pos_f: QPointF):
        """Updates split position or capture position based on cursor position relative to the pixmap."""
        if self.pixmap_width <= 0 or self.pixmap_height <= 0:
            return

        cursor_pos = cursor_pos_f.toPoint()
        label_rect = self.image_label.rect()

        x_offset = max(0, (label_rect.width() - self.pixmap_width) // 2)
        y_offset = max(0, (label_rect.height() - self.pixmap_height) // 2)

        raw_x = cursor_pos_f.x() - x_offset
        raw_y = cursor_pos_f.y() - y_offset

        pixmap_x = max(0.0, min(float(self.pixmap_width), raw_x))
        pixmap_y = max(0.0, min(float(self.pixmap_height), raw_y))

        rel_x = pixmap_x / self.pixmap_width
        rel_y = pixmap_y / self.pixmap_height
        rel_x = max(0.0, min(1.0, rel_x))
        rel_y = max(0.0, min(1.0, rel_y))


        needs_update = False
        epsilon = 1e-5

        if not self.use_magnifier:
            new_split = rel_x if not self.is_horizontal else rel_y
            if not math.isclose(self.split_position, new_split, abs_tol=epsilon):
                self.split_position = new_split
                needs_update = True
        else:
            new_rel = QPointF(rel_x, rel_y)
            current_rel = self.capture_position_relative
            if not math.isclose(current_rel.x(), new_rel.x(), abs_tol=epsilon) or \
               not math.isclose(current_rel.y(), new_rel.y(), abs_tol=epsilon):
                self.capture_position_relative = new_rel
                needs_update = True

        if needs_update:
            self.update_comparison()

    def _trigger_live_name_update(self):
        """Triggers a comparison update if file names checkbox is checked."""
        if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
            if self.original_image1 and self.original_image2:
                self.update_comparison_if_needed()

    def update_file_names(self):
        """Updates the file name labels below the image and checks length based on *currently selected* images."""
        name1_raw = ""
        if 0 <= self.current_index1 < len(self.image_list1):
             _, path, display_name = self.image_list1[self.current_index1]
             name1_raw = (self.edit_name1.text() if hasattr(self, 'edit_name1') else display_name) or display_name or os.path.basename(path or "")
        else:
             name1_raw = tr("Image 1", self.current_language) if self.current_index1 == -1 else ""

        name2_raw = ""
        if 0 <= self.current_index2 < len(self.image_list2):
             _, path, display_name = self.image_list2[self.current_index2]
             name2_raw = (self.edit_name2.text() if hasattr(self, 'edit_name2') else display_name) or display_name or os.path.basename(path or "")
        else:
             name2_raw = tr("Image 2", self.current_language) if self.current_index2 == -1 else ""


        max_len_ui = self.max_name_length
        display_name1 = (name1_raw[:max_len_ui-3]+"...") if len(name1_raw) > max_len_ui else name1_raw
        display_name2 = (name2_raw[:max_len_ui-3]+"...") if len(name2_raw) > max_len_ui else name2_raw

        if hasattr(self, 'file_name_label1') and hasattr(self, 'file_name_label2'):
            prefix1 = tr('Left', self.current_language) if not self.is_horizontal else tr('Top', self.current_language)
            prefix2 = tr('Right', self.current_language) if not self.is_horizontal else tr('Bottom', self.current_language)
            self.file_name_label1.setText(f"{prefix1}: {display_name1}")
            self.file_name_label2.setText(f"{prefix2}: {display_name2}")
            self.file_name_label1.setToolTip(name1_raw if len(name1_raw) > max_len_ui else "")
            self.file_name_label2.setToolTip(name2_raw if len(name2_raw) > max_len_ui else "")

        self.check_name_lengths(name1_raw, name2_raw)


    def check_name_lengths(self, name1 = None, name2 = None):
        """Checks name lengths and updates the warning label visibility and tooltip."""
        if not hasattr(self, 'length_warning_label'): return

        if name1 is None or name2 is None:
             if 0 <= self.current_index1 < len(self.image_list1):
                  _, _, dn1 = self.image_list1[self.current_index1]
                  name1 = (self.edit_name1.text() if hasattr(self, 'edit_name1') else dn1) or dn1
             else: name1 = ""
             if 0 <= self.current_index2 < len(self.image_list2):
                  _, _, dn2 = self.image_list2[self.current_index2]
                  name2 = (self.edit_name2.text() if hasattr(self, 'edit_name2') else dn2) or dn2
             else: name2 = ""

        len1, len2 = len(name1), len(name2)
        limit = self.max_name_length

        if len1 > limit or len2 > limit:
            longest = max(len1, len2)
            warning_text = tr("Name length limit ({limit}) exceeded!", self.current_language).format(limit=limit)
            tooltip_text = tr("One or both names exceed the current limit of {limit} characters (longest is {length}).\nClick here to change the limit.", self.current_language).format(length=longest, limit=limit)
            self.length_warning_label.setText(warning_text)
            self.length_warning_label.setToolTip(tooltip_text)
            if not self.length_warning_label.isVisible():
                 self.length_warning_label.setVisible(True)
        else:
            if self.length_warning_label.isVisible():
                 self.length_warning_label.setVisible(False)
                 self.length_warning_label.setToolTip("")


    def _edit_length_dialog(self, event):
        """Opens dialog to change the maximum name length."""
        current_limit = self.max_name_length
        new_limit, ok = QInputDialog.getInt(
            self,
            tr("Edit Length Limit", self.current_language),
            tr("Enter new maximum length (10-100):", self.current_language),
            value=current_limit, min=10, max=100)

        if ok and new_limit != current_limit:
            self.max_name_length = new_limit
            self.save_setting("max_name_length", new_limit)
            self.update_file_names()
            if hasattr(self, 'checkbox_file_names') and self.checkbox_file_names.isChecked():
                self.update_comparison_if_needed()
        else:
            pass


    def _create_flag_icon(self, base64_data):
        """Creates QIcon from base64 encoded image data."""
        try:
            pixmap = QPixmap()
            loaded = pixmap.loadFromData(base64.b64decode(base64_data))
            if not loaded:
                 print("Warning: Failed to load pixmap from base64 flag data.")
                 return QIcon()
            return QIcon(pixmap)
        except Exception as e:
             print(f"Error decoding/loading flag icon: {e}")
             return QIcon()

    def update_minimum_window_size(self):
        """Calculates and sets the minimum window size based on visible widgets."""
        min_w, min_h = 400, 0
        layout = self.layout()
        if not layout: return

        margins = layout.contentsMargins()
        spacing = layout.spacing() if layout.spacing() > -1 else 5

        min_h += margins.top() + margins.bottom()

        for i in range(layout.count()):
            item = layout.itemAt(i)
            item_h = 0
            is_visible = False

            widget = item.widget()
            sub_layout = item.layout()

            if widget:
                if widget.isVisible():
                    is_visible = True
                    hint = widget.minimumSizeHint() if widget == self.image_label else widget.sizeHint()
                    item_h = hint.height()
            elif sub_layout:
                 for j in range(sub_layout.count()):
                     sub_item = sub_layout.itemAt(j)
                     if sub_item and sub_item.widget() and sub_item.widget().isVisible():
                          is_visible = True
                          break
                 if is_visible:
                     item_h = sub_layout.sizeHint().height()

            if is_visible and item_h > 0:
                min_h += item_h
                if i < layout.count() - 1:
                    min_h += spacing

        min_h = max(350, min_h)
        try:
             current_min = self.minimumSize()
             if current_min.width() != min_w or current_min.height() != min_h:
                  self.setMinimumSize(min_w, min_h)
        except Exception as e:
             print(f"Error setting minimum size: {e}")


    def _update_drag_overlays(self):
        """Positions the drag-and-drop overlay labels over the image label halves."""
        if not hasattr(self, 'drag_overlay1') or not hasattr(self, 'image_label') or not self.image_label.isVisible():
            return

        try:
             label_geom = self.image_label.geometry()
             margin = 10
             half_width = label_geom.width() // 2
             overlay_w = half_width - margin - (margin // 2)
             overlay_h = label_geom.height() - 2 * margin
             overlay_w = max(10, overlay_w)
             overlay_h = max(10, overlay_h)

             overlay1_x = label_geom.x() + margin
             overlay1_y = label_geom.y() + margin
             self.drag_overlay1.setGeometry(overlay1_x, overlay1_y, overlay_w, overlay_h)

             overlay2_x = label_geom.x() + half_width + (margin // 2)
             overlay2_y = label_geom.y() + margin
             self.drag_overlay2.setGeometry(overlay2_x, overlay2_y, overlay_w, overlay_h)

        except Exception as e:
             print(f"Error updating drag overlays geometry: {e}")


    def _is_in_left_area(self, pos: QPoint) -> bool:
        """Determines if a point (relative to window) is in the left half of the image label."""
        if not hasattr(self, 'image_label'): return True
        try:
            label_geom = self.image_label.geometry()
            center_x = label_geom.x() + label_geom.width() // 2
            return pos.x() < center_x
        except Exception as e:
             print(f"Error in _is_in_left_area: {e}")
             return True

if __name__ == '__main__':
    app = QApplication(sys.argv)

    window = ImageComparisonApp()
    window.show()
    sys.exit(app.exec())
