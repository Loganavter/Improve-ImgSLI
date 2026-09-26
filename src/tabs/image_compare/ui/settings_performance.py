"""Image-compare specific groups appended to the platform ``builtin.performance`` settings page.

Resolution, interactive-optimization and video-recording controls only make
sense for the image-compare tab; render-backend is platform-owned and lives in
:mod:`plugins.settings.pages.performance`.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy
from sli_ui_toolkit.managers import as_nav_row, scaled_px
from sli_ui_toolkit.widgets import CheckBox, ComboBox, SpinBox

from plugins.settings.typography import (
    apply_settings_body,
    settings_body_label,
    settings_group,
)

from core.constants import AppConstants
from plugins.settings.search import SearchIndex, group

INTERACTIVE = group(
    "settings.interactive_optimization",
    "settings.zoom_interpolation",
    "settings.optimize_magnifier_movement",
    "settings.optimize_laser_smoothing",
    "settings.magnifier_intersection_highlight",
    "settings.magnifier_auto_color_new_instances",
)
VIDEO = group("image_compare.settings.video_recording", "image_compare.settings.recording_fps")
SEARCH = SearchIndex.of(INTERACTIVE, VIDEO)


def build_image_perf_extras(dialog, p) -> list:
    """Build this tab's performance extras and return their nav rows.

    The caller (``plugins/settings/pages/analysis.py`` /
    ``performance.py``) feeds the returned rows into its page's
    ``NavRowBuilder`` so they participate in keyboard navigation — these
    used to be added straight to the layout via ``add_layout()``, which
    made them permanently unreachable by Up/Down (see
    docs/legacy/plan_navigation_descriptor_unification.md §2.2).
    """
    layout = getattr(dialog, "_perf_layout", None)
    if layout is None:
        return []
    rows = []
    rows += _build_interactive_optimization_group(dialog, layout, p)
    rows += _build_video_group(dialog, layout, p)
    return rows


def _build_interactive_optimization_group(dialog, layout, p):
    dialog.interactive_opt_group = settings_group(dialog, INTERACTIVE)
    rows = []

    row_zoom = QHBoxLayout()
    row_zoom.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    dialog.lbl_zoom_interp = settings_body_label(
        INTERACTIVE.text(dialog, "settings.zoom_interpolation"),
    )
    INTERACTIVE.tag_member(dialog.lbl_zoom_interp, "settings.zoom_interpolation")
    dialog.combo_zoom_interp = ComboBox()
    apply_settings_body(dialog.combo_zoom_interp)
    INTERACTIVE.tag_combo(dialog.combo_zoom_interp, "settings.zoom_interpolation")
    dialog.combo_zoom_interp.setMinimumWidth(scaled_px(140))
    dialog.combo_zoom_interp.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    row_zoom.addWidget(dialog.lbl_zoom_interp)
    row_zoom.addWidget(dialog.combo_zoom_interp, 1)
    row_zoom_widget = as_nav_row(row_zoom)
    dialog.interactive_opt_group.add_widget(row_zoom_widget)
    rows.append(row_zoom_widget)

    row_mag = QHBoxLayout()
    row_mag.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    dialog.optimize_movement_checkbox = CheckBox(
        INTERACTIVE.text(dialog, "settings.optimize_magnifier_movement")
    )
    apply_settings_body(dialog.optimize_movement_checkbox)
    dialog.optimize_movement_checkbox.setChecked(p.optimize_magnifier_movement)
    INTERACTIVE.tag_member(
        dialog.optimize_movement_checkbox, "settings.optimize_magnifier_movement"
    )
    dialog.combo_mag_interp = ComboBox()
    apply_settings_body(dialog.combo_mag_interp)
    dialog.combo_mag_interp.setMinimumWidth(scaled_px(140))
    dialog.combo_mag_interp.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    dialog.combo_mag_interp.setEnabled(p.optimize_magnifier_movement)
    row_mag.addWidget(dialog.optimize_movement_checkbox)
    row_mag.addWidget(dialog.combo_mag_interp, 1)
    row_mag_widget = as_nav_row(row_mag)
    dialog.interactive_opt_group.add_widget(row_mag_widget)
    rows.append(row_mag_widget)

    row_laser = QHBoxLayout()
    row_laser.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    dialog.laser_smoothing_checkbox = CheckBox(
        INTERACTIVE.text(dialog, "settings.optimize_laser_smoothing")
    )
    apply_settings_body(dialog.laser_smoothing_checkbox)
    dialog.laser_smoothing_checkbox.setChecked(p.optimize_laser_smoothing)
    INTERACTIVE.tag_member(
        dialog.laser_smoothing_checkbox, "settings.optimize_laser_smoothing"
    )
    dialog.combo_laser_interp = ComboBox()
    apply_settings_body(dialog.combo_laser_interp)
    dialog.combo_laser_interp.setMinimumWidth(scaled_px(140))
    dialog.combo_laser_interp.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    dialog.combo_laser_interp.setEnabled(p.optimize_laser_smoothing)
    row_laser.addWidget(dialog.laser_smoothing_checkbox)
    row_laser.addWidget(dialog.combo_laser_interp, 1)
    row_laser_widget = as_nav_row(row_laser)
    dialog.interactive_opt_group.add_widget(row_laser_widget)
    rows.append(row_laser_widget)

    dialog.magnifier_intersection_highlight_checkbox = CheckBox(
        INTERACTIVE.text(dialog, "settings.magnifier_intersection_highlight")
    )
    apply_settings_body(dialog.magnifier_intersection_highlight_checkbox)
    dialog.magnifier_intersection_highlight_checkbox.setChecked(
        p.magnifier_intersection_highlight_enabled
    )
    INTERACTIVE.tag_member(
        dialog.magnifier_intersection_highlight_checkbox,
        "settings.magnifier_intersection_highlight",
    )
    intersection_row = as_nav_row(dialog.magnifier_intersection_highlight_checkbox)
    dialog.interactive_opt_group.add_widget(intersection_row)
    rows.append(intersection_row)

    dialog.magnifier_auto_color_checkbox = CheckBox(
        INTERACTIVE.text(dialog, "settings.magnifier_auto_color_new_instances")
    )
    apply_settings_body(dialog.magnifier_auto_color_checkbox)
    dialog.magnifier_auto_color_checkbox.setChecked(
        p.magnifier_auto_color_new_instances
    )
    INTERACTIVE.tag_member(
        dialog.magnifier_auto_color_checkbox,
        "settings.magnifier_auto_color_new_instances",
    )
    auto_color_row = as_nav_row(dialog.magnifier_auto_color_checkbox)
    dialog.interactive_opt_group.add_widget(auto_color_row)
    rows.append(auto_color_row)

    _populate_interpolation_combos(dialog, p)
    dialog.optimize_movement_checkbox.toggled.connect(
        dialog.combo_mag_interp.setEnabled
    )
    dialog.laser_smoothing_checkbox.toggled.connect(
        dialog.combo_laser_interp.setEnabled
    )
    layout.addWidget(dialog.interactive_opt_group)
    return rows


def _populate_interpolation_combos(dialog, p):
    interp_map = {
        "NEAREST": "magnifier.nearest_neighbor",
        "BILINEAR": "magnifier.bilinear",
        "BICUBIC": "magnifier.bicubic",
        "LANCZOS": "magnifier.lanczos",
        "EWA_LANCZOS": "magnifier.ewa_lanczos",
    }
    for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
        text = dialog._tr(interp_map.get(key, key), dialog.current_language)
        dialog.combo_mag_interp.addItem(text, key)
        dialog.combo_laser_interp.addItem(text, key)
    dialog.combo_zoom_interp.addItem(
        dialog._tr(interp_map["NEAREST"], dialog.current_language), "NEAREST"
    )
    dialog.combo_zoom_interp.addItem(
        dialog._tr(interp_map["BILINEAR"], dialog.current_language), "BILINEAR"
    )

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
    dialog.video_group = settings_group(dialog, VIDEO)
    video_layout = QHBoxLayout()
    video_layout.setContentsMargins(0, scaled_px(5), 0, scaled_px(5))
    # Bare "FPS" — universal abbreviation, no translation needed (and the
    # spin keeps the Find Action member key for discoverability).
    dialog.lbl_fps = settings_body_label("FPS:")
    dialog.spin_fps = SpinBox(default_value=60)
    apply_settings_body(dialog.spin_fps)
    VIDEO.tag_member(dialog.spin_fps, "image_compare.settings.recording_fps")
    dialog.spin_fps.setRange(10, 144)
    dialog.spin_fps.setValue(p.current_video_fps)
    dialog.spin_fps.setFixedWidth(scaled_px(100))
    dialog.spin_fps.setAlignment(Qt.AlignmentFlag.AlignCenter)
    video_layout.addWidget(dialog.lbl_fps)
    video_layout.addWidget(dialog.spin_fps)
    video_layout.addStretch()
    video_row = as_nav_row(video_layout)
    dialog.video_group.add_widget(video_row)
    layout.addWidget(dialog.video_group)
    return [video_row]