import logging

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.constants import AppConstants
from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
from src.shared_toolkit.ui.widgets.atomic.fluent_combobox import FluentComboBox
from ui.widgets import FluentCheckBox, FluentRadioButton
from utils.resource_loader import resource_path

logger = logging.getLogger("ImproveImgSLI")

try:
    from resources.translations import tr as app_tr
except ImportError:

    def app_tr(text, lang="en", *args, **kwargs):
        try:
            return text.format(*args, **kwargs)
        except (KeyError, IndexError):
            return text

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
        optimize_magnifier_movement: bool = True,
        movement_interpolation_method: str = "BILINEAR",
        auto_calculate_psnr: bool = False,
        auto_calculate_ssim: bool = False,
    ):
        super().__init__(parent)
        self.setWindowIcon(QIcon(resource_path("resources/icons/icon.png")))
        self.setObjectName("SettingsDialog")
        self.tr = tr_func if callable(tr_func) else app_tr
        self.current_language = current_language

        self.theme_manager = ThemeManager.get_instance()

        self.setWindowTitle(self.tr("Settings", self.current_language))

        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
        )
        self.setSizeGripEnabled(True)
        self.resize(400, 560)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        lang_title = QLabel(self.tr("Language:", self.current_language))
        main_layout.addWidget(lang_title)

        lang_grid_layout = QGridLayout()
        lang_grid_layout.setSpacing(10)
        self.radio_en = FluentRadioButton("English")
        self.radio_ru = FluentRadioButton("Русский")
        self.radio_zh = FluentRadioButton("中文")
        self.radio_pt_br = FluentRadioButton("Português")
        self._lang_group = QButtonGroup(self)
        for rb in (self.radio_en, self.radio_ru, self.radio_zh, self.radio_pt_br):
            self._lang_group.addButton(rb)
        lang_grid_layout.addWidget(self.radio_en, 0, 0)
        lang_grid_layout.addWidget(self.radio_ru, 0, 1)
        lang_grid_layout.addWidget(self.radio_zh, 1, 0)
        lang_grid_layout.addWidget(self.radio_pt_br, 1, 1)
        main_layout.addLayout(lang_grid_layout)

        if current_language == "en":
            self.radio_en.setChecked(True)
        elif current_language == "ru":
            self.radio_ru.setChecked(True)
        elif current_language == "zh":
            self.radio_zh.setChecked(True)
        elif current_language == "pt_BR":
            self.radio_pt_br.setChecked(True)
        else:
            self.radio_en.setChecked(True)

        theme_layout = QHBoxLayout()
        theme_label = QLabel(self.tr("Theme:", self.current_language))
        self.combo_theme = FluentComboBox()
        self.combo_theme.addItem(self.tr("Auto", self.current_language), "auto")
        self.combo_theme.addItem(self.tr("Light", self.current_language), "light")
        self.combo_theme.addItem(self.tr("Dark", self.current_language), "dark")

        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.combo_theme)
        main_layout.addLayout(theme_layout)

        theme_index_to_set = self.combo_theme.findData(current_theme)
        if theme_index_to_set != -1:
            self.combo_theme.setCurrentIndex(theme_index_to_set)

        font_section_label = QLabel(self.tr("UI Font:", self.current_language))
        main_layout.addWidget(font_section_label)

        font_mode_layout = QHBoxLayout()
        self.radio_font_builtin = FluentRadioButton(self.tr("Built-in font", self.current_language))
        self.radio_font_system_default = FluentRadioButton(self.tr("System default", self.current_language))
        self.radio_font_system_custom = FluentRadioButton(self.tr("Custom", self.current_language))
        self._font_mode_group = QButtonGroup(self)
        for rb in (self.radio_font_builtin, self.radio_font_system_default, self.radio_font_system_custom):
            self._font_mode_group.addButton(rb)
        font_mode_layout.addWidget(self.radio_font_builtin)
        font_mode_layout.addWidget(self.radio_font_system_default)
        font_mode_layout.addWidget(self.radio_font_system_custom)
        main_layout.addLayout(font_mode_layout)

        self.combo_font_family = FluentComboBox()
        families = QFontDatabase.families()
        self.combo_font_family.addItem(self.tr("Select font...", self.current_language), "")
        for fam in families:
            self.combo_font_family.addItem(fam, fam)
        main_layout.addWidget(self.combo_font_family)

        mode = (current_ui_font_mode or "builtin")
        if mode == "system_default" or mode == "system":
            self.radio_font_system_default.setChecked(True)
        elif mode == "system_custom":
            self.radio_font_system_custom.setChecked(True)
        else:
            self.radio_font_builtin.setChecked(True)
        idx_fam = self.combo_font_family.findData(current_ui_font_family or "")
        if idx_fam != -1:
            self.combo_font_family.setCurrentIndex(idx_fam)

        def _sync_font_family_enabled():
            self.combo_font_family.setEnabled(self.radio_font_system_custom.isChecked())
        _sync_font_family_enabled()
        self.radio_font_system_custom.toggled.connect(_sync_font_family_enabled)
        self.radio_font_builtin.toggled.connect(_sync_font_family_enabled)
        self.radio_font_system_default.toggled.connect(_sync_font_family_enabled)

        def _sync_font_family_visibility():
            is_custom = self.radio_font_system_custom.isChecked()
            self.combo_font_family.setEnabled(is_custom)
            self.combo_font_family.setVisible(is_custom)
        _sync_font_family_visibility()
        self.radio_font_system_custom.toggled.connect(_sync_font_family_visibility)
        self.radio_font_builtin.toggled.connect(_sync_font_family_visibility)
        self.radio_font_system_default.toggled.connect(_sync_font_family_visibility)

        length_layout = QHBoxLayout()
        length_label = QLabel(
            self.tr("Maximum Name Length (UI):", self.current_language)
        )
        self.spin_max_length = QSpinBox()
        self.spin_max_length.setRange(min_limit, max_limit)
        self.spin_max_length.setValue(
            max(min_limit, min(max_limit, current_max_length))
        )
        length_layout.addWidget(length_label)
        length_layout.addWidget(self.spin_max_length)
        main_layout.addLayout(length_layout)

        resolution_layout = QHBoxLayout()
        resolution_label = QLabel(
            self.tr("Display Cache Resolution:", self.current_language)
        )
        self.combo_resolution = FluentComboBox()
        for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
            self.combo_resolution.addItem(
                self.tr(name_key, self.current_language), userData=limit
            )
        index_to_set = self.combo_resolution.findData(current_resolution_limit)
        if index_to_set != -1:
            self.combo_resolution.setCurrentIndex(index_to_set)
        resolution_layout.addWidget(resolution_label)
        resolution_layout.addWidget(self.combo_resolution)
        main_layout.addLayout(resolution_layout)

        self.movement_interp_container = QWidget()
        movement_interp_layout = QHBoxLayout(self.movement_interp_container)
        movement_interp_layout.setContentsMargins(0, 0, 0, 0)
        movement_interp_layout.setSpacing(8)

        self.movement_interp_label = QLabel(self.tr("Movement Interpolation:", self.current_language))
        movement_interp_layout.addWidget(self.movement_interp_label)

        self.combo_movement_interpolation = FluentComboBox()
        try:
            from image_processing.resize import WAND_AVAILABLE
        except Exception:
            WAND_AVAILABLE = False

        self._movement_interp_keys = []
        for key, name in AppConstants.INTERPOLATION_METHODS_MAP.items():
            if key == "EWA_LANCZOS" and not WAND_AVAILABLE:
                continue
            self.combo_movement_interpolation.addItem(self.tr(name, self.current_language), key)
            self._movement_interp_keys.append(key)

        interp_index_to_set = self.combo_movement_interpolation.findData(movement_interpolation_method)
        if interp_index_to_set != -1:
            self.combo_movement_interpolation.setCurrentIndex(interp_index_to_set)

        movement_interp_layout.addWidget(self.combo_movement_interpolation)

        main_layout.addWidget(self.movement_interp_container)

        self.optimize_movement_checkbox = FluentCheckBox(
            self.tr("Optimize magnifier movement", self.current_language)
        )
        self.optimize_movement_checkbox.setChecked(optimize_magnifier_movement)
        main_layout.addWidget(self.optimize_movement_checkbox)

        self.optimize_movement_checkbox.toggled.connect(self.movement_interp_container.setVisible)

        self.movement_interp_container.setVisible(optimize_magnifier_movement)

        self.debug_checkbox = FluentCheckBox(
            self.tr("Enable debug logging", self.current_language)
        )
        self.debug_checkbox.setChecked(debug_mode_enabled)
        main_layout.addWidget(self.debug_checkbox)

        self.auto_psnr_checkbox = FluentCheckBox(
            self.tr("Auto-calculate PSNR", self.current_language)
        )
        self.auto_psnr_checkbox.setChecked(auto_calculate_psnr)
        main_layout.addWidget(self.auto_psnr_checkbox)

        self.auto_ssim_checkbox = FluentCheckBox(
            self.tr("Auto-calculate SSIM", self.current_language)
        )
        self.auto_ssim_checkbox.setChecked(auto_calculate_ssim)
        main_layout.addWidget(self.auto_ssim_checkbox)

        self.system_notifications_checkbox = FluentCheckBox(
            self.tr("System notifications", self.current_language)
        )
        self.system_notifications_checkbox.setChecked(system_notifications_enabled)
        main_layout.addWidget(self.system_notifications_checkbox)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        self.ok_button = QPushButton(self.tr("OK", self.current_language))
        self.ok_button.setObjectName("okButton")
        self.cancel_button = QPushButton(self.tr("Cancel", self.current_language))
        self.ok_button.setMinimumSize(80, 32)
        self.cancel_button.setMinimumSize(80, 32)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.ok_button)
        buttons_layout.addWidget(self.cancel_button)
        main_layout.addStretch()
        main_layout.addLayout(buttons_layout)

        self._apply_styles()
        self.theme_manager.theme_changed.connect(self._apply_styles)

    def _apply_styles(self):

        self.theme_manager.apply_theme_to_dialog(self)

    def get_settings(self):
        selected_language = "en"
        if self.radio_en.isChecked():
            selected_language = "en"
        elif self.radio_ru.isChecked():
            selected_language = "ru"
        elif self.radio_zh.isChecked():
            selected_language = "zh"
        elif self.radio_pt_br.isChecked():
            selected_language = "pt_BR"

        selected_theme = self.combo_theme.currentData()

        max_length = self.spin_max_length.value()
        debug_enabled = self.debug_checkbox.isChecked()
        auto_psnr = self.auto_psnr_checkbox.isChecked()
        auto_ssim = self.auto_ssim_checkbox.isChecked()
        sys_notif_enabled = self.system_notifications_checkbox.isChecked()
        resolution_limit = self.combo_resolution.currentData()

        optimize_movement = self.optimize_movement_checkbox.isChecked()
        movement_interp = self.combo_movement_interpolation.currentData()

        if self.radio_font_system_default.isChecked():
            ui_font_mode = "system_default"
        elif self.radio_font_system_custom.isChecked():
            ui_font_mode = "system_custom"
        else:
            ui_font_mode = "builtin"
        ui_font_family = self.combo_font_family.currentData() or ""

        return (
            selected_language,
            selected_theme,
            max_length,
            debug_enabled,
            sys_notif_enabled,
            resolution_limit,
            ui_font_mode,
            ui_font_family,
            optimize_movement,
            movement_interp,
            auto_psnr,
            auto_ssim,
        )

    def update_language(self, lang_code: str):
        self.current_language = lang_code
        self.setWindowTitle(self.tr("Settings", self.current_language))

        for label in self.findChildren(QLabel):
            if "Language:" in label.text() or "Язык:" in label.text():
                label.setText(self.tr("Language:", self.current_language))
            elif "Theme:" in label.text() or "Тема:" in label.text():
                label.setText(self.tr("Theme:", self.current_language))
            elif "UI Font:" in label.text() or "Шрифт интерфейса:" in label.text():
                label.setText(self.tr("UI Font:", self.current_language))
            elif "Maximum Name Length (UI):" in label.text() or "Макс. длина имени (в UI):" in label.text():
                label.setText(self.tr("Maximum Name Length (UI):", self.current_language))
            elif "Display Cache Resolution:" in label.text() or "Разрешение кэша:" in label.text():
                label.setText(self.tr("Display Cache Resolution:", self.current_language))

            elif "Movement Interpolation:" in label.text() or "Интерполяция при движении:" in label.text():
                label.setText(self.tr("Movement Interpolation:", self.current_language))

        self.radio_font_builtin.setText(self.tr("Built-in font", self.current_language))
        self.radio_font_system_default.setText(self.tr("System default", self.current_language))
        self.radio_font_system_custom.setText(self.tr("Custom", self.current_language))
        self.combo_font_family.setItemText(0, self.tr("Select font...", self.current_language))

        self.debug_checkbox.setText(self.tr("Enable debug logging", self.current_language))
        self.auto_psnr_checkbox.setText(self.tr("Auto-calculate PSNR", self.current_language))
        self.auto_ssim_checkbox.setText(self.tr("Auto-calculate SSIM", self.current_language))

        self.optimize_movement_checkbox.setText(self.tr("Optimize magnifier movement", self.current_language))
        for i, key in enumerate(self._movement_interp_keys):
            self.combo_movement_interpolation.setItemText(i, self.tr(AppConstants.INTERPOLATION_METHODS_MAP[key], self.current_language))

        self.system_notifications_checkbox.setText(self.tr("System notifications", self.current_language))

        self.ok_button.setText(self.tr("OK", self.current_language))
        self.cancel_button.setText(self.tr("Cancel", self.current_language))

        self.combo_theme.setItemText(0, self.tr("Auto", self.current_language))
        self.combo_theme.setItemText(1, self.tr("Light", self.current_language))
        self.combo_theme.setItemText(2, self.tr("Dark", self.current_language))

        for i, (name_key, _) in enumerate(AppConstants.DISPLAY_RESOLUTION_OPTIONS.items()):
            self.combo_resolution.setItemText(i, self.tr(name_key, self.current_language))
