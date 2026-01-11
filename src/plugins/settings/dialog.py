import logging

from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QLabel,
    QButtonGroup,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QApplication,
)

from core.constants import AppConstants
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.atomic.custom_button import CustomButton
from toolkit.widgets.atomic.fluent_combobox import FluentComboBox
from toolkit.widgets.atomic.fluent_spinbox import FluentSpinBox
from toolkit.widgets.atomic import FluentCheckBox, FluentRadioButton, CustomGroupWidget
from ui.icon_manager import AppIcon, get_app_icon
from utils.resource_loader import resource_path
from resources.translations import tr as app_tr

logger = logging.getLogger("ImproveImgSLI")

class SettingsDialog(QDialog):
    def __init__(
        self,
        current_language,
        current_theme,
        current_max_length,
        min_limit,
        max_limit,
        debug_mode_enabled,
        system_notifications_enabled,
        current_resolution_limit,
        parent=None,
        tr_func=None,
        current_ui_font_mode: str = "builtin",
        current_ui_font_family: str = "",
        current_ui_mode: str = "beginner",
        optimize_magnifier_movement: bool = True,
        movement_interpolation_method: str = "BILINEAR",
        optimize_laser_smoothing: bool = False,
        interpolation_method: str = "LANCZOS",
        auto_calculate_psnr: bool = False,
        auto_calculate_ssim: bool = False,
        auto_crop_black_borders: bool = True,
        current_video_fps: int = 60,
        store=None,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("SettingsDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language
        self.theme_manager = ThemeManager.get_instance()

        self._init_params = locals()

        self.setWindowTitle(self.tr("misc.settings", self.current_language))

        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sidebar.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar.setIconSize(QSize(24, 24))
        self.sidebar.currentRowChanged.connect(self._on_category_changed)

        self.content_area = QWidget()
        self.content_layout = QVBoxLayout(self.content_area)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(10)

        self.pages_stack = QStackedWidget()
        self.content_layout.addWidget(self.pages_stack)

        self.buttons_layout = QHBoxLayout()
        self.buttons_layout.addStretch()

        self.ok_button = CustomButton(None, self.tr("common.ok", self.current_language))
        self.ok_button.setProperty("class", "primary")
        self.ok_button.setFixedSize(100, 32)

        self.cancel_button = CustomButton(None, self.tr("common.cancel", self.current_language))
        self.cancel_button.setFixedSize(100, 32)

        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)

        self.buttons_layout.addWidget(self.ok_button)
        self.buttons_layout.addWidget(self.cancel_button)

        self.content_layout.addLayout(self.buttons_layout)

        self.main_layout.addWidget(self.sidebar)
        self.main_layout.addWidget(self.content_area, 1)

        self._init_general_page()
        self._init_interface_page()
        self._init_performance_page()
        self._init_analysis_page()

        self._setup_sidebar_items()

        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

        self.sidebar.setCurrentRow(0)

        QTimer.singleShot(0, self._calculate_and_apply_geometry)

    def _calculate_and_apply_geometry(self):
        self.ensurePolished()

        sidebar_width = self.sidebar.width()
        content_margins = self.content_layout.contentsMargins()

        total_width_margins = content_margins.left() + content_margins.right() + 40

        max_group_width = 0
        max_content_height = 0

        for i in range(self.pages_stack.count()):
            page_wrapper = self.pages_stack.widget(i)
            scroll_area = page_wrapper.findChild(QScrollArea)

            if scroll_area:
                content_widget = scroll_area.widget()

                content_widget.ensurePolished()
                content_widget.adjustSize()

                groups = content_widget.findChildren(CustomGroupWidget)
                if groups:
                    for group in groups:
                        max_group_width = max(max_group_width, group.sizeHint().width())
                else:
                    max_group_width = max(max_group_width, content_widget.sizeHint().width())

                max_content_height = max(max_content_height, content_widget.sizeHint().height())

        required_width = sidebar_width + max_group_width + total_width_margins
        final_width = max(800, min(required_width, 1200))

        bottom_controls_height = 80

        sidebar_req_height = self.sidebar.count() * 45 + 40

        required_height = max(sidebar_req_height, max_content_height + bottom_controls_height)

        screen_h = QApplication.primaryScreen().availableGeometry().height()
        final_height = min(required_height, screen_h - 100) + 5

        self.resize(final_width, final_height)
        self.setMinimumSize(final_width, final_height)

        if self.parent():
            geo = self.geometry()
            geo.moveCenter(self.parent().geometry().center())
            self.move(geo.topLeft())

    def _setup_sidebar_items(self):
        self.sidebar.clear()
        self._sidebar_items_data = [
            (self.tr("settings.appearance", self.current_language), AppIcon.SETTINGS),
            (self.tr("label.view", self.current_language), AppIcon.TEXT_MANIPULATOR),
            (self.tr("settings.optimization", self.current_language), AppIcon.PLAY),
            (self.tr("label.details", self.current_language), AppIcon.HIGHLIGHT_DIFFERENCES)
        ]
        for text, icon_enum in self._sidebar_items_data:
            item = QListWidgetItem(get_app_icon(icon_enum), text)
            item.setSizeHint(QSize(0, 44))
            self.sidebar.addItem(item)

    def _update_sidebar_icons(self):
        if not hasattr(self, '_sidebar_items_data'):
            return

        for i, (text, icon_enum) in enumerate(self._sidebar_items_data):
            if i < self.sidebar.count():
                item = self.sidebar.item(i)
                item.setIcon(get_app_icon(icon_enum))

    def _create_scrollable_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 12, 0)
        content_layout.setSpacing(15)

        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        return page, content_layout

    def _init_general_page(self):
        self.page_general, layout = self._create_scrollable_page()
        p = self._init_params

        self.lang_group = CustomGroupWidget(self.tr("label.language", self.current_language))
        lang_layout = QHBoxLayout()

        lang_layout.setContentsMargins(5, 5, 5, 5)
        self.radio_en = FluentRadioButton("English")
        self.radio_ru = FluentRadioButton("Русский")
        self.radio_zh = FluentRadioButton("中文")
        self.radio_pt_br = FluentRadioButton("Português")
        self._lang_group = QButtonGroup(self)
        for rb in (self.radio_en, self.radio_ru, self.radio_zh, self.radio_pt_br):
            self._lang_group.addButton(rb)
            lang_layout.addWidget(rb)
        self.lang_group.add_layout(lang_layout)
        layout.addWidget(self.lang_group)

        language_radio_map = {
            "ru": self.radio_ru,
            "zh": self.radio_zh,
            "pt_BR": self.radio_pt_br,
        }
        selected_radio = language_radio_map.get(p['current_language'], self.radio_en)
        selected_radio.setChecked(True)

        self.sys_group = CustomGroupWidget(self.tr("settings.appearance", self.current_language))

        theme_row = QHBoxLayout()
        theme_row.setContentsMargins(5, 5, 5, 5)
        self.theme_label = QLabel(self.tr("label.theme", self.current_language) + ":")
        self.combo_theme = FluentComboBox()
        self.combo_theme.setFixedWidth(140)
        self.combo_theme.addItem(self.tr("settings.auto", self.current_language), "auto")
        self.combo_theme.addItem(self.tr("settings.light", self.current_language), "light")
        self.combo_theme.addItem(self.tr("settings.dark", self.current_language), "dark")
        idx = self.combo_theme.findData(p['current_theme'])
        if idx != -1: self.combo_theme.setCurrentIndex(idx)

        theme_row.addWidget(self.theme_label)
        theme_row.addWidget(self.combo_theme)
        theme_row.addStretch()
        self.sys_group.add_layout(theme_row)

        self.system_notifications_checkbox = FluentCheckBox(self.tr("settings.system_notifications", self.current_language))
        self.system_notifications_checkbox.setChecked(p['system_notifications_enabled'])
        self.sys_group.add_widget(self.system_notifications_checkbox)

        self.debug_checkbox = FluentCheckBox(self.tr("settings.enable_debug_logging", self.current_language))
        self.debug_checkbox.setChecked(p['debug_mode_enabled'])
        self.sys_group.add_widget(self.debug_checkbox)

        layout.addWidget(self.sys_group)

        self.pages_stack.addWidget(self.page_general)

    def _init_interface_page(self):
        self.page_interface, layout = self._create_scrollable_page()
        p = self._init_params

        self.ui_mode_group = CustomGroupWidget(self.tr("settings.ui_mode", self.current_language))
        ui_mode_layout = QHBoxLayout()
        ui_mode_layout.setContentsMargins(5, 5, 5, 5)
        self.radio_ui_mode_beginner = FluentRadioButton(self.tr("settings.ui_mode_beginner", self.current_language))
        self.radio_ui_mode_advanced = FluentRadioButton(self.tr("settings.ui_mode_advanced", self.current_language))
        self.radio_ui_mode_expert = FluentRadioButton(self.tr("settings.ui_mode_expert", self.current_language))
        self._ui_mode_group = QButtonGroup(self)
        for rb in (self.radio_ui_mode_beginner, self.radio_ui_mode_advanced, self.radio_ui_mode_expert):
            self._ui_mode_group.addButton(rb)
            ui_mode_layout.addWidget(rb)
        self.ui_mode_group.add_layout(ui_mode_layout)
        layout.addWidget(self.ui_mode_group)

        ui_mode_radio_map = {
            "expert": self.radio_ui_mode_expert,
            "advanced": self.radio_ui_mode_advanced,
        }
        selected_ui_mode_radio = ui_mode_radio_map.get(p['current_ui_mode'], self.radio_ui_mode_beginner)
        selected_ui_mode_radio.setChecked(True)

        self.font_group = CustomGroupWidget(self.tr("settings.ui_font", self.current_language))
        font_radio_layout = QVBoxLayout()
        font_radio_layout.setContentsMargins(5, 5, 5, 5)

        self.radio_font_builtin = FluentRadioButton(self.tr("settings.builtin_font", self.current_language))
        self.radio_font_system_default = FluentRadioButton(self.tr("settings.system_default", self.current_language))
        self.radio_font_system_custom = FluentRadioButton(self.tr("settings.custom", self.current_language))

        font_radio_layout.addWidget(self.radio_font_builtin)
        font_radio_layout.addWidget(self.radio_font_system_default)
        font_radio_layout.addWidget(self.radio_font_system_custom)

        self.font_group.add_layout(font_radio_layout)

        self.combo_font_family = FluentComboBox()
        from PyQt6.QtGui import QFontDatabase
        families = QFontDatabase.families()
        self.combo_font_family.addItem(self.tr("settings.select_font", self.current_language), "")
        for fam in families:
            self.combo_font_family.addItem(fam, fam)

        font_combo_container = QWidget()
        fc_layout = QHBoxLayout(font_combo_container)
        fc_layout.setContentsMargins(5, 0, 5, 5)
        fc_layout.addWidget(self.combo_font_family)
        self.font_group.add_widget(font_combo_container)

        layout.addWidget(self.font_group)

        mode = p['current_ui_font_mode'] or "builtin"
        font_mode_radio_map = {
            "system_default": self.radio_font_system_default,
            "system": self.radio_font_system_default,
            "system_custom": self.radio_font_system_custom,
        }
        selected_font_radio = font_mode_radio_map.get(mode, self.radio_font_builtin)
        selected_font_radio.setChecked(True)

        idx_fam = self.combo_font_family.findData(p['current_ui_font_family'] or "")
        if idx_fam != -1: self.combo_font_family.setCurrentIndex(idx_fam)

        def _sync_font_ui():
            is_custom = self.radio_font_system_custom.isChecked()
            font_combo_container.setVisible(is_custom)
            QTimer.singleShot(50, self._calculate_and_apply_geometry)

        self.radio_font_system_custom.toggled.connect(_sync_font_ui)
        self.radio_font_builtin.toggled.connect(_sync_font_ui)
        self.radio_font_system_default.toggled.connect(_sync_font_ui)
        _sync_font_ui()

        self.other_ui_group = CustomGroupWidget(self.tr("settings.maximum_name_length_ui", self.current_language))
        len_layout = QHBoxLayout()

        len_layout.setContentsMargins(12, 5, 12, 5)

        val_to_set = max(p['min_limit'], min(p['max_limit'], p['current_max_length']))

        self.spin_max_length = FluentSpinBox(default_value=val_to_set)
        self.spin_max_length.setRange(p['min_limit'], p['max_limit'])
        self.spin_max_length.setValue(val_to_set)

        self.spin_max_length.setFixedWidth(100)
        self.spin_max_length.setAlignment(Qt.AlignmentFlag.AlignCenter)

        len_layout.addWidget(self.spin_max_length)
        len_layout.addStretch()

        self.other_ui_group.add_layout(len_layout)

        layout.addWidget(self.other_ui_group)

        self.pages_stack.addWidget(self.page_interface)

    def _init_performance_page(self):
        self.page_perf, layout = self._create_scrollable_page()
        p = self._init_params

        self.res_group = CustomGroupWidget(self.tr("settings.display_cache_resolution", self.current_language))
        res_layout = QHBoxLayout()
        res_layout.setContentsMargins(5, 5, 5, 5)

        self.combo_resolution = FluentComboBox()
        self.combo_resolution.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        resolution_translation_map = {
            "Original": "settings.original",
            "8K (4320p)": "settings.resolution_8k",
            "4K (2160p)": "settings.resolution_4k",
            "2K (1440p)": "settings.resolution_2k",
            "Full HD (1080p)": "settings.resolution_full_hd",
        }
        for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
            translation_key = resolution_translation_map.get(name_key, name_key)
            display_text = self.tr(translation_key, self.current_language)
            self.combo_resolution.addItem(display_text, userData=limit)

        idx_res = self.combo_resolution.findData(p['current_resolution_limit'])
        if idx_res != -1: self.combo_resolution.setCurrentIndex(idx_res)

        res_layout.addWidget(self.combo_resolution)

        self.res_group.add_layout(res_layout)
        layout.addWidget(self.res_group)

        self.interactive_opt_group = CustomGroupWidget(self.tr("settings.interactive_optimization", self.current_language))

        row_mag_layout = QHBoxLayout()
        row_mag_layout.setContentsMargins(5, 5, 5, 5)
        self.optimize_movement_checkbox = FluentCheckBox(self.tr("settings.optimize_magnifier_movement", self.current_language))
        self.optimize_movement_checkbox.setChecked(p['optimize_magnifier_movement'])

        self.combo_mag_interp = FluentComboBox()
        self.combo_mag_interp.setMinimumWidth(140)
        self.combo_mag_interp.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.combo_mag_interp.setEnabled(p['optimize_magnifier_movement'])

        row_mag_layout.addWidget(self.optimize_movement_checkbox)
        row_mag_layout.addStretch()
        row_mag_layout.addWidget(self.combo_mag_interp)

        self.interactive_opt_group.add_layout(row_mag_layout)

        row_laser_layout = QHBoxLayout()
        row_laser_layout.setContentsMargins(5, 5, 5, 5)
        self.laser_smoothing_checkbox = FluentCheckBox(self.tr("settings.optimize_laser_smoothing", self.current_language))
        self.laser_smoothing_checkbox.setChecked(p['optimize_laser_smoothing'])

        self.combo_laser_interp = FluentComboBox()
        self.combo_laser_interp.setMinimumWidth(140)
        self.combo_laser_interp.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.combo_laser_interp.setEnabled(p['optimize_laser_smoothing'])

        row_laser_layout.addWidget(self.laser_smoothing_checkbox)
        row_laser_layout.addStretch()
        row_laser_layout.addWidget(self.combo_laser_interp)

        self.interactive_opt_group.add_layout(row_laser_layout)

        try:
            from shared.image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False

        interp_map = {
            "NEAREST": "magnifier.nearest_neighbor",
            "BILINEAR": "magnifier.bilinear",
            "BICUBIC": "magnifier.bicubic",
            "LANCZOS": "magnifier.lanczos",
            "EWA_LANCZOS": "magnifier.ewa_lanczos",
        }

        valid_keys = [k for k in AppConstants.INTERPOLATION_METHODS_MAP.keys() if k != "EWA_LANCZOS" or WAND_AVAILABLE]

        from PyQt6.QtGui import QFontMetrics
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            font_metrics = QFontMetrics(self.combo_mag_interp.font())
            max_text_width = 0
            items_texts = []

            for key in valid_keys:
                text = self.tr(interp_map.get(key, key), self.current_language)
                items_texts.append(text)
                text_width = font_metrics.horizontalAdvance(text)
                max_text_width = max(max_text_width, text_width)

            combo_width = max(140, max_text_width + 50)

            for i, key in enumerate(valid_keys):
                self.combo_mag_interp.addItem(items_texts[i], key)
                self.combo_laser_interp.addItem(items_texts[i], key)

            self.combo_mag_interp.setMinimumWidth(combo_width)
            self.combo_laser_interp.setMinimumWidth(combo_width)
        else:

            for key in valid_keys:
                text = self.tr(interp_map.get(key, key), self.current_language)
                self.combo_mag_interp.addItem(text, key)
                self.combo_laser_interp.addItem(text, key)

        store_obj = p.get('store', None)
        if store_obj and hasattr(store_obj, 'viewport'):
            mag_method = getattr(store_obj.viewport.render_config, 'magnifier_movement_interpolation_method', None)
            laser_method = getattr(store_obj.viewport.render_config, 'laser_smoothing_interpolation_method', None)
        else:
            mag_method = p.get('movement_interpolation_method', 'BILINEAR')
            laser_method = 'BILINEAR'

        mag_idx = self.combo_mag_interp.findData(mag_method)
        if mag_idx != -1:
            self.combo_mag_interp.setCurrentIndex(mag_idx)

        laser_idx = self.combo_laser_interp.findData(laser_method)
        if laser_idx != -1:
            self.combo_laser_interp.setCurrentIndex(laser_idx)

        self.optimize_movement_checkbox.toggled.connect(self.combo_mag_interp.setEnabled)
        self.laser_smoothing_checkbox.toggled.connect(self.combo_laser_interp.setEnabled)

        layout.addWidget(self.interactive_opt_group)

        self.video_group = CustomGroupWidget(self.tr("settings.video_recording", self.current_language))
        video_layout = QHBoxLayout()
        video_layout.setContentsMargins(5, 5, 5, 5)

        self.lbl_fps = QLabel(self.tr("settings.recording_fps", self.current_language) + ":")
        self.spin_fps = FluentSpinBox(default_value=60)
        self.spin_fps.setRange(10, 144)
        self.spin_fps.setValue(p.get('current_video_fps', 60))
        self.spin_fps.setFixedWidth(100)
        self.spin_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)

        video_layout.addWidget(self.lbl_fps)
        video_layout.addWidget(self.spin_fps)
        video_layout.addStretch()

        self.video_group.add_layout(video_layout)
        layout.addWidget(self.video_group)

        self.pages_stack.addWidget(self.page_perf)

    def _init_analysis_page(self):
        self.page_analysis, layout = self._create_scrollable_page()
        p = self._init_params

        self.auto_group = CustomGroupWidget(self.tr("settings.auto", self.current_language))

        self.crop_checkbox = FluentCheckBox(self.tr("settings.autocrop_black_borders_on_load", self.current_language))
        self.crop_checkbox.setChecked(p['auto_crop_black_borders'])

        self.crop_checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.auto_group.add_widget(self.crop_checkbox)
        layout.addWidget(self.auto_group)

        self.metrics_group = CustomGroupWidget(self.tr("label.details", self.current_language))
        self.auto_psnr_checkbox = FluentCheckBox(self.tr("settings.autocalculate_psnr", self.current_language))
        self.auto_psnr_checkbox.setChecked(p['auto_calculate_psnr'])
        self.metrics_group.add_widget(self.auto_psnr_checkbox)

        self.auto_ssim_checkbox = FluentCheckBox(self.tr("settings.autocalculate_ssim", self.current_language))
        self.auto_ssim_checkbox.setChecked(p['auto_calculate_ssim'])
        self.metrics_group.add_widget(self.auto_ssim_checkbox)

        layout.addWidget(self.metrics_group)
        self.pages_stack.addWidget(self.page_analysis)

    def _on_category_changed(self, row):
        self.pages_stack.setCurrentIndex(row)

    def _apply_styles(self):
        self.theme_manager.apply_theme_to_dialog(self)

        is_dark = self.theme_manager.is_dark()
        bg_color = self.theme_manager.get_color("dialog.background").name()
        sidebar_bg = self.theme_manager.get_color("dialog.input.background").name() if is_dark else "#f3f3f3"
        item_hover = self.theme_manager.get_color("list_item.background.hover").name()
        item_selected = self.theme_manager.get_color("accent").name()
        text_color = self.theme_manager.get_color("dialog.text").name()

        self.sidebar.setStyleSheet(f"""
            QListWidget {{
                background-color: {sidebar_bg};
                border-right: 1px solid {self.theme_manager.get_color("dialog.border").name()};
                outline: none;
            }}
            QListWidget::item {{
                padding: 10px 12px;
                margin: 4px 8px;
                border-radius: 6px;
                color: {text_color};
            }}
            QListWidget::item:hover {{
                background-color: {item_hover};
            }}
            QListWidget::item:selected {{
                background-color: {item_selected};
                color: white;
            }}
        """)

        self.content_area.setStyleSheet(f"background-color: {bg_color};")

        self._update_sidebar_icons()

    def get_settings(self):
        language_radio_map = {
            self.radio_en: "en",
            self.radio_ru: "ru",
            self.radio_zh: "zh",
            self.radio_pt_br: "pt_BR",
        }
        selected_language = next(
            (lang for radio, lang in language_radio_map.items() if radio.isChecked()),
            "en"
        )

        selected_theme = self.combo_theme.currentData()
        max_length = self.spin_max_length.value()
        debug_enabled = self.debug_checkbox.isChecked()
        sys_notif = self.system_notifications_checkbox.isChecked()
        res_limit = self.combo_resolution.currentData()

        font_mode_radio_map = {
            self.radio_font_system_default: "system_default",
            self.radio_font_system_custom: "system_custom",
        }
        ui_font_mode = next(
            (mode for radio, mode in font_mode_radio_map.items() if radio.isChecked()),
            "builtin"
        )

        ui_font_family = self.combo_font_family.currentData() or ""

        opt_mov = self.optimize_movement_checkbox.isChecked()
        mag_interp = self.combo_mag_interp.currentData() or "BILINEAR"
        opt_laser = self.laser_smoothing_checkbox.isChecked()
        laser_interp = self.combo_laser_interp.currentData() or "BILINEAR"
        auto_psnr = self.auto_psnr_checkbox.isChecked()
        auto_ssim = self.auto_ssim_checkbox.isChecked()
        auto_crop = self.crop_checkbox.isChecked()
        video_fps = self.spin_fps.value()

        ui_mode_radio_map = {
            self.radio_ui_mode_expert: "expert",
            self.radio_ui_mode_advanced: "advanced",
        }
        ui_mode = next(
            (mode for radio, mode in ui_mode_radio_map.items() if radio.isChecked()),
            "beginner"
        )

        return (
            selected_language,
            selected_theme,
            max_length,
            debug_enabled,
            sys_notif,
            res_limit,
            ui_font_mode,
            ui_font_family,
            opt_mov,
            mag_interp,
            opt_laser,
            laser_interp,
            auto_psnr,
            auto_ssim,
            auto_crop,
            ui_mode,
            video_fps,
        )

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.setWindowTitle(self.tr("misc.settings", self.current_language))

        self._setup_sidebar_items()

        self.ok_button.setText(self.tr("common.ok", lang_code))
        self.cancel_button.setText(self.tr("common.cancel", lang_code))

        if hasattr(self, 'lang_group'):
            self.lang_group.set_title(self.tr("label.language", lang_code))

        if hasattr(self, 'sys_group'):
            self.sys_group.set_title(self.tr("settings.appearance", lang_code))

        if hasattr(self, 'theme_label'):
            self.theme_label.setText(self.tr("label.theme", lang_code) + ":")

        if hasattr(self, 'combo_theme'):
            current_theme = self.combo_theme.currentData()
            self.combo_theme.clear()
            self.combo_theme.addItem(self.tr("settings.auto", lang_code), "auto")
            self.combo_theme.addItem(self.tr("settings.light", lang_code), "light")
            self.combo_theme.addItem(self.tr("settings.dark", lang_code), "dark")
            idx = self.combo_theme.findData(current_theme)
            if idx != -1:
                self.combo_theme.setCurrentIndex(idx)

        if hasattr(self, 'system_notifications_checkbox'):
            self.system_notifications_checkbox.setText(self.tr("settings.system_notifications", lang_code))
        if hasattr(self, 'debug_checkbox'):
            self.debug_checkbox.setText(self.tr("settings.enable_debug_logging", lang_code))

        if hasattr(self, 'ui_mode_group'):
            self.ui_mode_group.set_title(self.tr("settings.ui_mode", lang_code))

        if hasattr(self, 'radio_ui_mode_beginner'):
            self.radio_ui_mode_beginner.setText(self.tr("settings.ui_mode_beginner", lang_code))
        if hasattr(self, 'radio_ui_mode_advanced'):
            self.radio_ui_mode_advanced.setText(self.tr("settings.ui_mode_advanced", lang_code))
        if hasattr(self, 'radio_ui_mode_expert'):
            self.radio_ui_mode_expert.setText(self.tr("settings.ui_mode_expert", lang_code))

        if hasattr(self, 'font_group'):
            self.font_group.set_title(self.tr("settings.ui_font", lang_code))

        if hasattr(self, 'radio_font_builtin'):
            self.radio_font_builtin.setText(self.tr("settings.builtin_font", lang_code))
        if hasattr(self, 'radio_font_system_default'):
            self.radio_font_system_default.setText(self.tr("settings.system_default", lang_code))
        if hasattr(self, 'radio_font_system_custom'):
            self.radio_font_system_custom.setText(self.tr("settings.custom", lang_code))

        if hasattr(self, 'combo_font_family'):
            current_font = self.combo_font_family.currentData()
            from PyQt6.QtGui import QFontDatabase
            families = QFontDatabase.families()
            self.combo_font_family.clear()
            self.combo_font_family.addItem(self.tr("settings.select_font", lang_code), "")
            for fam in families:
                self.combo_font_family.addItem(fam, fam)
            idx_fam = self.combo_font_family.findData(current_font or "")
            if idx_fam != -1:
                self.combo_font_family.setCurrentIndex(idx_fam)

        if hasattr(self, 'other_ui_group'):
            self.other_ui_group.set_title(self.tr("settings.maximum_name_length_ui", lang_code))

        if hasattr(self, 'res_group'):
            self.res_group.set_title(self.tr("settings.display_cache_resolution", lang_code))

        if hasattr(self, 'combo_resolution'):
            current_res = self.combo_resolution.currentData()
            resolution_translation_map = {
                "Original": "settings.original",
                "8K (4320p)": "settings.resolution_8k",
                "4K (2160p)": "settings.resolution_4k",
                "2K (1440p)": "settings.resolution_2k",
                "Full HD (1080p)": "settings.resolution_full_hd",
            }
            self.combo_resolution.clear()
            for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
                translation_key = resolution_translation_map.get(name_key, name_key)
                display_text = self.tr(translation_key, lang_code)
                self.combo_resolution.addItem(display_text, userData=limit)
            idx_res = self.combo_resolution.findData(current_res)
            if idx_res != -1:
                self.combo_resolution.setCurrentIndex(idx_res)

        if hasattr(self, 'interactive_opt_group'):
            self.interactive_opt_group.set_title(self.tr("settings.interactive_optimization", lang_code))

        if hasattr(self, 'optimize_movement_checkbox'):
            self.optimize_movement_checkbox.setText(self.tr("settings.optimize_magnifier_movement", lang_code))
        if hasattr(self, 'laser_smoothing_checkbox'):
            self.laser_smoothing_checkbox.setText(self.tr("settings.optimize_laser_smoothing", lang_code))

        if hasattr(self, 'combo_mag_interp'):
            current_mag_interp = self.combo_mag_interp.currentData()
            current_laser_interp = self.combo_laser_interp.currentData() if hasattr(self, 'combo_laser_interp') else None
            try:
                from shared.image_processing.resize import WAND_AVAILABLE
            except Exception:
                WAND_AVAILABLE = False

            interp_map = {
                "NEAREST": "magnifier.nearest_neighbor",
                "BILINEAR": "magnifier.bilinear",
                "BICUBIC": "magnifier.bicubic",
                "LANCZOS": "magnifier.lanczos",
                "EWA_LANCZOS": "magnifier.ewa_lanczos",
            }

            self.combo_mag_interp.clear()
            for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
                if key == "EWA_LANCZOS" and not WAND_AVAILABLE:
                    continue
                trans_key = interp_map.get(key, key)
                self.combo_mag_interp.addItem(self.tr(trans_key, lang_code), key)
            idx_mag = self.combo_mag_interp.findData(current_mag_interp)
            if idx_mag != -1:
                self.combo_mag_interp.setCurrentIndex(idx_mag)

            if hasattr(self, 'combo_laser_interp'):
                self.combo_laser_interp.clear()
                for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
                    if key == "EWA_LANCZOS" and not WAND_AVAILABLE:
                        continue
                    trans_key = interp_map.get(key, key)
                    self.combo_laser_interp.addItem(self.tr(trans_key, lang_code), key)
                idx_laser = self.combo_laser_interp.findData(current_laser_interp)
                if idx_laser != -1:
                    self.combo_laser_interp.setCurrentIndex(idx_laser)

        if hasattr(self, 'auto_group'):
            self.auto_group.set_title(self.tr("settings.auto", lang_code))

        if hasattr(self, 'crop_checkbox'):
            self.crop_checkbox.setText(self.tr("settings.autocrop_black_borders_on_load", lang_code))

        if hasattr(self, 'metrics_group'):
            self.metrics_group.set_title(self.tr("label.details", lang_code))

        if hasattr(self, 'auto_psnr_checkbox'):
            self.auto_psnr_checkbox.setText(self.tr("settings.autocalculate_psnr", lang_code))
        if hasattr(self, 'auto_ssim_checkbox'):
            self.auto_ssim_checkbox.setText(self.tr("settings.autocalculate_ssim", lang_code))

        curr = self.sidebar.currentRow()
        self.sidebar.setCurrentRow(-1)
        self.sidebar.setCurrentRow(curr)

    def accept(self):

        self._reset_button_states()
        super().accept()

    def reject(self):

        self._reset_button_states()
        super().reject()

    def _reset_button_states(self):
        if hasattr(self, 'ok_button'):
            self.ok_button.setProperty("state", "normal")
            self.ok_button.update()
        if hasattr(self, 'cancel_button'):
            self.cancel_button.setProperty("state", "normal")
            self.cancel_button.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clear_input_focus()
        super().mousePressEvent(event)

    def clear_input_focus(self):
        focused_widget = self.focusWidget()
        if focused_widget and hasattr(focused_widget, 'clearFocus'):
            focused_widget.clearFocus()
