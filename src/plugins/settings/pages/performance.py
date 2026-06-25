"""Optimization page — group-level filtering by active tab.

Render backend is global. Resolution / interactive optimization / video
recording belong to ``image_compare`` and are skipped on other tabs.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy

from core.constants import AppConstants
from sli_ui_toolkit.widgets import CheckBox, ComboBox, CustomGroupWidget, SpinBox
from ui.icon_manager import AppIcon

from plugins.settings.registry import SettingsSection


def build(dialog, p):
    dialog.page_perf, layout = dialog._create_scrollable_page()
    is_image_compare = getattr(dialog, "active_tab", None) in (None, "image_compare")
    if is_image_compare:
        _build_resolution_group(dialog, layout, p)
        _build_interactive_optimization_group(dialog, layout, p)
        _build_video_group(dialog, layout, p)
    _build_render_backend_group(dialog, layout, p)
    dialog.pages_stack.addWidget(dialog.page_perf)


def _build_resolution_group(dialog, layout, p):
    dialog.res_group = CustomGroupWidget(
        dialog.tr("settings.display_cache_resolution", dialog.current_language)
    )
    res_layout = QHBoxLayout()
    res_layout.setContentsMargins(5, 5, 5, 5)
    dialog.combo_resolution = ComboBox()
    dialog.combo_resolution.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    mapping = {
        "Original": "settings.original",
        "8K (4320p)": "settings.resolution_8k",
        "4K (2160p)": "settings.resolution_4k",
        "2K (1440p)": "settings.resolution_2k",
        "Full HD (1080p)": "settings.resolution_full_hd",
    }
    for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
        dialog.combo_resolution.addItem(
            dialog.tr(mapping.get(name_key, name_key), dialog.current_language),
            userData=limit,
        )
    idx_res = dialog.combo_resolution.findData(p.current_resolution_limit)
    if idx_res != -1:
        dialog.combo_resolution.setCurrentIndex(idx_res)
    res_layout.addWidget(dialog.combo_resolution)
    dialog.res_group.add_layout(res_layout)
    layout.addWidget(dialog.res_group)


def _build_interactive_optimization_group(dialog, layout, p):
    dialog.interactive_opt_group = CustomGroupWidget(
        dialog.tr("settings.interactive_optimization", dialog.current_language)
    )

    row_zoom = QHBoxLayout()
    row_zoom.setContentsMargins(0, 5, 0, 5)
    dialog.lbl_zoom_interp = QLabel(dialog.tr("settings.zoom_interpolation", dialog.current_language))
    dialog.combo_zoom_interp = ComboBox()
    dialog.combo_zoom_interp.setMinimumWidth(140)
    dialog.combo_zoom_interp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row_zoom.addWidget(dialog.lbl_zoom_interp)
    row_zoom.addWidget(dialog.combo_zoom_interp, 1)
    dialog.interactive_opt_group.add_layout(row_zoom)

    row_mag = QHBoxLayout()
    row_mag.setContentsMargins(0, 5, 0, 5)
    dialog.optimize_movement_checkbox = CheckBox(
        dialog.tr("settings.optimize_magnifier_movement", dialog.current_language)
    )
    dialog.optimize_movement_checkbox.setChecked(p.optimize_magnifier_movement)
    dialog.combo_mag_interp = ComboBox()
    dialog.combo_mag_interp.setMinimumWidth(140)
    dialog.combo_mag_interp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    dialog.combo_mag_interp.setEnabled(p.optimize_magnifier_movement)
    row_mag.addWidget(dialog.optimize_movement_checkbox)
    row_mag.addWidget(dialog.combo_mag_interp, 1)
    dialog.interactive_opt_group.add_layout(row_mag)

    row_laser = QHBoxLayout()
    row_laser.setContentsMargins(0, 5, 0, 5)
    dialog.laser_smoothing_checkbox = CheckBox(
        dialog.tr("settings.optimize_laser_smoothing", dialog.current_language)
    )
    dialog.laser_smoothing_checkbox.setChecked(p.optimize_laser_smoothing)
    dialog.combo_laser_interp = ComboBox()
    dialog.combo_laser_interp.setMinimumWidth(140)
    dialog.combo_laser_interp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    dialog.combo_laser_interp.setEnabled(p.optimize_laser_smoothing)
    row_laser.addWidget(dialog.laser_smoothing_checkbox)
    row_laser.addWidget(dialog.combo_laser_interp, 1)
    dialog.interactive_opt_group.add_layout(row_laser)

    dialog.magnifier_intersection_highlight_checkbox = CheckBox(
        dialog.tr("settings.magnifier_intersection_highlight", dialog.current_language)
    )
    dialog.magnifier_intersection_highlight_checkbox.setChecked(
        p.magnifier_intersection_highlight_enabled
    )
    dialog.interactive_opt_group.add_widget(
        dialog.magnifier_intersection_highlight_checkbox
    )

    dialog.magnifier_auto_color_checkbox = CheckBox(
        dialog.tr("settings.magnifier_auto_color_new_instances", dialog.current_language)
    )
    dialog.magnifier_auto_color_checkbox.setChecked(
        p.magnifier_auto_color_new_instances
    )
    dialog.interactive_opt_group.add_widget(dialog.magnifier_auto_color_checkbox)

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


def _build_render_backend_group(dialog, layout, p):
    dialog.render_backend_group = CustomGroupWidget(
        dialog.tr("settings.render_backend", dialog.current_language)
    )
    row = QHBoxLayout()
    row.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_rhi_backend = QLabel(
        dialog.tr("settings.render_backend_label", dialog.current_language) + ":"
    )
    dialog.combo_rhi_backend = ComboBox()
    dialog.combo_rhi_backend.setMinimumWidth(180)
    dialog.combo_rhi_backend.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    all_options = [
        ("default", "settings.render_backend_default"),
        ("opengl", "settings.render_backend_opengl"),
        ("vulkan", "settings.render_backend_vulkan"),
        ("d3d11", "settings.render_backend_d3d11"),
        ("d3d12", "settings.render_backend_d3d12"),
        ("metal", "settings.render_backend_metal"),
    ]
    if sys.platform == "darwin":
        keep = {"default", "opengl", "metal", "vulkan"}
    elif sys.platform.startswith("win"):
        keep = {"default", "opengl", "d3d11", "d3d12", "vulkan"}
    else:
        keep = {"default", "opengl", "vulkan"}

    for value, key in all_options:
        if value not in keep:
            continue
        dialog.combo_rhi_backend.addItem(
            dialog.tr(key, dialog.current_language), userData=value,
        )
    idx = dialog.combo_rhi_backend.findData(p.rhi_backend or "default")
    if idx != -1:
        dialog.combo_rhi_backend.setCurrentIndex(idx)
    row.addWidget(dialog.lbl_rhi_backend)
    row.addWidget(dialog.combo_rhi_backend, 1)
    dialog.render_backend_group.add_layout(row)

    dialog.lbl_rhi_backend_hint = QLabel(
        dialog.tr("settings.render_backend_restart_hint", dialog.current_language)
    )
    dialog.lbl_rhi_backend_hint.setWordWrap(True)
    dialog.lbl_rhi_backend_hint.setStyleSheet("color: palette(mid);")
    dialog.render_backend_group.add_widget(dialog.lbl_rhi_backend_hint)

    layout.addWidget(dialog.render_backend_group)


def _build_video_group(dialog, layout, p):
    dialog.video_group = CustomGroupWidget(
        dialog.tr("settings.video_recording", dialog.current_language)
    )
    video_layout = QHBoxLayout()
    video_layout.setContentsMargins(5, 5, 5, 5)
    dialog.lbl_fps = QLabel(dialog.tr("settings.recording_fps", dialog.current_language) + ":")
    dialog.spin_fps = SpinBox(default_value=60)
    dialog.spin_fps.setRange(10, 144)
    dialog.spin_fps.setValue(p.current_video_fps)
    dialog.spin_fps.setFixedWidth(100)
    dialog.spin_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
    video_layout.addWidget(dialog.lbl_fps)
    video_layout.addWidget(dialog.spin_fps)
    video_layout.addStretch()
    dialog.video_group.add_layout(video_layout)
    layout.addWidget(dialog.video_group)


SECTION = SettingsSection(
    section_id="builtin.performance",
    title_key="settings.optimization",
    icon=AppIcon.PLAY,
    build=build,
    owner_tab=None,
    order=30,
)
