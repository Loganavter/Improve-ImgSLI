from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.constants import AppConstants
from shared_toolkit.ui.widgets.atomic import (
    CustomGroupWidget,
    FluentCheckBox,
    FluentRadioButton,
)
from shared_toolkit.ui.widgets.atomic.fluent_combobox import FluentComboBox
from shared_toolkit.ui.widgets.atomic.fluent_spinbox import FluentSpinBox

def init_general_page(dialog, p):
    dialog.page_general, layout = dialog._create_scrollable_page()

    dialog.lang_group = CustomGroupWidget(dialog.tr("label.language", dialog.current_language))
    lang_layout = QHBoxLayout()
    lang_layout.setContentsMargins(5, 5, 5, 5)
    dialog.radio_en = FluentRadioButton("English")
    dialog.radio_ru = FluentRadioButton("Русский")
    dialog.radio_zh = FluentRadioButton("中文")
    dialog.radio_pt_br = FluentRadioButton("Português")
    dialog._lang_group = QButtonGroup(dialog)
    for rb in (dialog.radio_en, dialog.radio_ru, dialog.radio_zh, dialog.radio_pt_br):
        dialog._lang_group.addButton(rb)
        lang_layout.addWidget(rb)
    dialog.lang_group.add_layout(lang_layout)
    layout.addWidget(dialog.lang_group)
    {"ru": dialog.radio_ru, "zh": dialog.radio_zh, "pt_BR": dialog.radio_pt_br}.get(
        p.current_language, dialog.radio_en
    ).setChecked(True)

    dialog.sys_group = CustomGroupWidget(dialog.tr("settings.appearance", dialog.current_language))
    theme_row = QHBoxLayout()
    theme_row.setContentsMargins(5, 5, 5, 5)
    dialog.theme_label = QLabel(dialog.tr("label.theme", dialog.current_language) + ":")
    dialog.combo_theme = FluentComboBox()
    dialog.combo_theme.setFixedWidth(140)
    for key in ("auto", "light", "dark"):
        dialog.combo_theme.addItem(dialog.tr(f"settings.{key}", dialog.current_language), key)
    idx = dialog.combo_theme.findData(p.current_theme)
    if idx != -1:
        dialog.combo_theme.setCurrentIndex(idx)
    theme_row.addWidget(dialog.theme_label)
    theme_row.addWidget(dialog.combo_theme)
    theme_row.addStretch()
    dialog.sys_group.add_layout(theme_row)

    dialog.system_notifications_checkbox = FluentCheckBox(dialog.tr("settings.system_notifications", dialog.current_language))
    dialog.system_notifications_checkbox.setChecked(p.system_notifications_enabled)
    dialog.sys_group.add_widget(dialog.system_notifications_checkbox)
    dialog.debug_checkbox = FluentCheckBox(dialog.tr("settings.enable_debug_logging", dialog.current_language))
    dialog.debug_checkbox.setChecked(p.debug_mode_enabled)
    dialog.sys_group.add_widget(dialog.debug_checkbox)
    layout.addWidget(dialog.sys_group)
    dialog.pages_stack.addWidget(dialog.page_general)

def init_interface_page(dialog, p):
    dialog.page_interface, layout = dialog._create_scrollable_page()
    dialog.ui_mode_group = CustomGroupWidget(dialog.tr("settings.ui_mode", dialog.current_language))
    row = QHBoxLayout()
    row.setContentsMargins(5, 5, 5, 5)
    dialog.radio_ui_mode_beginner = FluentRadioButton(dialog.tr("settings.ui_mode_beginner", dialog.current_language))
    dialog.radio_ui_mode_advanced = FluentRadioButton(dialog.tr("settings.ui_mode_advanced", dialog.current_language))
    dialog.radio_ui_mode_expert = FluentRadioButton(dialog.tr("settings.ui_mode_expert", dialog.current_language))
    dialog._ui_mode_group = QButtonGroup(dialog)
    for rb in (dialog.radio_ui_mode_beginner, dialog.radio_ui_mode_advanced, dialog.radio_ui_mode_expert):
        dialog._ui_mode_group.addButton(rb)
        row.addWidget(rb)
    dialog.ui_mode_group.add_layout(row)
    layout.addWidget(dialog.ui_mode_group)
    {"expert": dialog.radio_ui_mode_expert, "advanced": dialog.radio_ui_mode_advanced}.get(
        p.current_ui_mode, dialog.radio_ui_mode_beginner
    ).setChecked(True)

    dialog.font_group = CustomGroupWidget(dialog.tr("settings.ui_font", dialog.current_language))
    font_radio_layout = QVBoxLayout()
    font_radio_layout.setContentsMargins(5, 5, 5, 5)
    dialog.radio_font_builtin = FluentRadioButton(dialog.tr("settings.builtin_font", dialog.current_language))
    dialog.radio_font_system_default = FluentRadioButton(dialog.tr("settings.system_default", dialog.current_language))
    dialog.radio_font_system_custom = FluentRadioButton(dialog.tr("settings.custom", dialog.current_language))
    for rb in (dialog.radio_font_builtin, dialog.radio_font_system_default, dialog.radio_font_system_custom):
        font_radio_layout.addWidget(rb)
    dialog.font_group.add_layout(font_radio_layout)

    dialog.combo_font_family = FluentComboBox()
    dialog.combo_font_family.setFixedWidth(320)
    dialog.combo_font_family.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    from PyQt6.QtGui import QFontDatabase

    for fam in QFontDatabase.families():
        dialog.combo_font_family.addItem(fam, fam)
    font_combo_container = QWidget()
    fc_layout = QHBoxLayout(font_combo_container)
    fc_layout.setContentsMargins(5, 0, 5, 5)
    fc_layout.addWidget(dialog.combo_font_family)
    fc_layout.addStretch()
    dialog.font_group.add_widget(font_combo_container)
    layout.addWidget(dialog.font_group)

    mode = p.current_ui_font_mode or "builtin"
    {
        "system_default": dialog.radio_font_system_default,
        "system": dialog.radio_font_system_default,
        "system_custom": dialog.radio_font_system_custom,
    }.get(mode, dialog.radio_font_builtin).setChecked(True)
    idx_fam = dialog.combo_font_family.findData(p.current_ui_font_family or "")
    if idx_fam != -1:
        dialog.combo_font_family.setCurrentIndex(idx_fam)

    def sync_font_ui():
        is_custom = dialog.radio_font_system_custom.isChecked()
        scroll_area = dialog._page_scroll_area(dialog.page_interface)
        if scroll_area is not None:
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        font_combo_container.setVisible(is_custom)
        font_combo_container.adjustSize()
        dialog.font_group.adjustSize()
        dialog._calculate_and_apply_geometry()
        if scroll_area is not None:
            QTimer.singleShot(
                0,
                lambda: scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded),
            )

    for rb in (dialog.radio_font_system_custom, dialog.radio_font_builtin, dialog.radio_font_system_default):
        rb.toggled.connect(sync_font_ui)
    sync_font_ui()

    dialog.other_ui_group = CustomGroupWidget(dialog.tr("settings.maximum_name_length_ui", dialog.current_language))
    len_layout = QHBoxLayout()
    len_layout.setContentsMargins(12, 5, 12, 5)
    value = max(p.min_limit, min(p.max_limit, p.current_max_length))
    dialog.spin_max_length = FluentSpinBox(default_value=value)
    dialog.spin_max_length.setRange(p.min_limit, p.max_limit)
    dialog.spin_max_length.setValue(value)
    dialog.spin_max_length.setFixedWidth(100)
    dialog.spin_max_length.setAlignment(Qt.AlignmentFlag.AlignCenter)
    len_layout.addWidget(dialog.spin_max_length)
    len_layout.addStretch()
    dialog.other_ui_group.add_layout(len_layout)
    layout.addWidget(dialog.other_ui_group)
    dialog.pages_stack.addWidget(dialog.page_interface)

def init_performance_page(dialog, p):
    dialog.page_perf, layout = dialog._create_scrollable_page()
    _build_resolution_group(dialog, layout, p)
    _build_interactive_optimization_group(dialog, layout, p)
    _build_video_group(dialog, layout, p)
    dialog.pages_stack.addWidget(dialog.page_perf)

def init_analysis_page(dialog, p):
    dialog.page_analysis, layout = dialog._create_scrollable_page()
    dialog.auto_group = CustomGroupWidget(dialog.tr("settings.auto", dialog.current_language))
    dialog.crop_checkbox = FluentCheckBox(dialog.tr("settings.autocrop_black_borders_on_load", dialog.current_language))
    dialog.crop_checkbox.setChecked(p.auto_crop_black_borders)
    dialog.crop_checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    dialog.auto_group.add_widget(dialog.crop_checkbox)
    layout.addWidget(dialog.auto_group)

    dialog.metrics_group = CustomGroupWidget(dialog.tr("label.details", dialog.current_language))
    dialog.auto_psnr_checkbox = FluentCheckBox(dialog.tr("settings.autocalculate_psnr", dialog.current_language))
    dialog.auto_psnr_checkbox.setChecked(p.auto_calculate_psnr)
    dialog.metrics_group.add_widget(dialog.auto_psnr_checkbox)
    dialog.auto_ssim_checkbox = FluentCheckBox(dialog.tr("settings.autocalculate_ssim", dialog.current_language))
    dialog.auto_ssim_checkbox.setChecked(p.auto_calculate_ssim)
    dialog.metrics_group.add_widget(dialog.auto_ssim_checkbox)
    layout.addWidget(dialog.metrics_group)
    dialog.pages_stack.addWidget(dialog.page_analysis)

def _build_resolution_group(dialog, layout, p):
    dialog.res_group = CustomGroupWidget(dialog.tr("settings.display_cache_resolution", dialog.current_language))
    res_layout = QHBoxLayout()
    res_layout.setContentsMargins(5, 5, 5, 5)
    dialog.combo_resolution = FluentComboBox()
    dialog.combo_resolution.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    mapping = {
        "Original": "settings.original",
        "8K (4320p)": "settings.resolution_8k",
        "4K (2160p)": "settings.resolution_4k",
        "2K (1440p)": "settings.resolution_2k",
        "Full HD (1080p)": "settings.resolution_full_hd",
    }
    for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
        dialog.combo_resolution.addItem(dialog.tr(mapping.get(name_key, name_key), dialog.current_language), userData=limit)
    idx_res = dialog.combo_resolution.findData(p.current_resolution_limit)
    if idx_res != -1:
        dialog.combo_resolution.setCurrentIndex(idx_res)
    res_layout.addWidget(dialog.combo_resolution)
    dialog.res_group.add_layout(res_layout)
    layout.addWidget(dialog.res_group)

def _build_interactive_optimization_group(dialog, layout, p):
    dialog.interactive_opt_group = CustomGroupWidget(dialog.tr("settings.interactive_optimization", dialog.current_language))

    row_zoom = QHBoxLayout()
    row_zoom.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_zoom_interp = QLabel(dialog.tr("settings.zoom_interpolation", dialog.current_language))
    dialog.combo_zoom_interp = FluentComboBox()
    dialog.combo_zoom_interp.setMinimumWidth(140)
    dialog.combo_zoom_interp.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
    row_zoom.addWidget(dialog.lbl_zoom_interp)
    row_zoom.addStretch()
    row_zoom.addWidget(dialog.combo_zoom_interp)
    dialog.interactive_opt_group.add_layout(row_zoom)

    row_mag = QHBoxLayout()
    row_mag.setContentsMargins(5, 5, 5, 5)
    dialog.optimize_movement_checkbox = FluentCheckBox(dialog.tr("settings.optimize_magnifier_movement", dialog.current_language))
    dialog.optimize_movement_checkbox.setChecked(p.optimize_magnifier_movement)
    dialog.combo_mag_interp = FluentComboBox()
    dialog.combo_mag_interp.setMinimumWidth(140)
    dialog.combo_mag_interp.setEnabled(p.optimize_magnifier_movement)
    row_mag.addWidget(dialog.optimize_movement_checkbox)
    row_mag.addStretch()
    row_mag.addWidget(dialog.combo_mag_interp)
    dialog.interactive_opt_group.add_layout(row_mag)

    row_laser = QHBoxLayout()
    row_laser.setContentsMargins(5, 5, 5, 5)
    dialog.laser_smoothing_checkbox = FluentCheckBox(dialog.tr("settings.optimize_laser_smoothing", dialog.current_language))
    dialog.laser_smoothing_checkbox.setChecked(p.optimize_laser_smoothing)
    dialog.combo_laser_interp = FluentComboBox()
    dialog.combo_laser_interp.setMinimumWidth(140)
    dialog.combo_laser_interp.setEnabled(p.optimize_laser_smoothing)
    row_laser.addWidget(dialog.laser_smoothing_checkbox)
    row_laser.addStretch()
    row_laser.addWidget(dialog.combo_laser_interp)
    dialog.interactive_opt_group.add_layout(row_laser)

    _populate_interpolation_combos(dialog, p)
    dialog.optimize_movement_checkbox.toggled.connect(dialog.combo_mag_interp.setEnabled)
    dialog.laser_smoothing_checkbox.toggled.connect(dialog.combo_laser_interp.setEnabled)
    layout.addWidget(dialog.interactive_opt_group)

def _populate_interpolation_combos(dialog, p):
    interp_map = {
        "NEAREST": "magnifier.nearest_neighbor",
        "BILINEAR": "magnifier.bilinear",
        "BICUBIC": "magnifier.bicubic",
        "LANCZOS": "magnifier.lanczos",
        "EWA_LANCZOS": "magnifier.ewa_lanczos",
    }
    for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
        text = dialog.tr(interp_map.get(key, key), dialog.current_language)
        dialog.combo_mag_interp.addItem(text, key)
        dialog.combo_laser_interp.addItem(text, key)
    dialog.combo_zoom_interp.addItem(dialog.tr(interp_map["NEAREST"], dialog.current_language), "NEAREST")
    dialog.combo_zoom_interp.addItem(dialog.tr(interp_map["BILINEAR"], dialog.current_language), "BILINEAR")

    store_obj = p.store
    if store_obj and hasattr(store_obj, "viewport"):
        mag_method = getattr(
            store_obj.viewport.render_config,
            "magnifier_movement_interpolation_method",
            None,
        )
        laser_method = getattr(
            store_obj.viewport.render_config,
            "laser_smoothing_interpolation_method",
            None,
        )
    else:
        mag_method = p.movement_interpolation_method
        laser_method = "BILINEAR"
    for combo, value in (
        (dialog.combo_mag_interp, mag_method),
        (dialog.combo_laser_interp, laser_method),
        (dialog.combo_zoom_interp, p.zoom_interpolation_method),
    ):
        idx = combo.findData(value)
        if idx != -1:
            combo.setCurrentIndex(idx)

def _build_video_group(dialog, layout, p):
    dialog.video_group = CustomGroupWidget(dialog.tr("settings.video_recording", dialog.current_language))
    video_layout = QHBoxLayout()
    video_layout.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_fps = QLabel(dialog.tr("settings.recording_fps", dialog.current_language) + ":")
    dialog.spin_fps = FluentSpinBox(default_value=60)
    dialog.spin_fps.setRange(10, 144)
    dialog.spin_fps.setValue(p.current_video_fps)
    dialog.spin_fps.setFixedWidth(100)
    dialog.spin_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
    video_layout.addWidget(dialog.lbl_fps)
    video_layout.addWidget(dialog.spin_fps)
    video_layout.addStretch()
    dialog.video_group.add_layout(video_layout)
    layout.addWidget(dialog.video_group)
