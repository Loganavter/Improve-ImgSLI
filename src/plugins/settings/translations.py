from __future__ import annotations

from core.constants import AppConstants

_INTERPOLATION_KEY_MAP = {
    "NEAREST": "magnifier.nearest_neighbor",
    "BILINEAR": "magnifier.bilinear",
    "BICUBIC": "magnifier.bicubic",
    "LANCZOS": "magnifier.lanczos",
    "EWA_LANCZOS": "magnifier.ewa_lanczos",
}

_THEME_KEYS = ("auto", "light", "dark")

_RESOLUTION_KEY_MAP = {
    "Original": "settings.original",
    "8K (4320p)": "settings.resolution_8k",
    "4K (2160p)": "settings.resolution_4k",
    "2K (1440p)": "settings.resolution_2k",
    "Full HD (1080p)": "settings.resolution_full_hd",
}


def apply_translations(dialog, lang: str) -> None:
    dialog.setWindowTitle(dialog.tr("misc.settings", lang))
    _apply_buttons(dialog, lang)
    _apply_simple_texts(dialog, lang)
    _apply_group_titles(dialog, lang)
    _apply_label_with_colon(dialog, lang)
    _rebuild_theme_combo(dialog, lang)
    _rebuild_font_family_combo(dialog, lang)
    _rebuild_resolution_combo(dialog, lang)
    _rebuild_interpolation_combos(dialog, lang)
    _rebuild_rhi_backend_combo(dialog, lang)


def _apply_buttons(dialog, lang: str) -> None:
    dialog.ok_button.setText(dialog.tr("common.ok", lang))
    dialog.cancel_button.setText(dialog.tr("common.cancel", lang))


def _apply_simple_texts(dialog, lang: str) -> None:
    candidates = [
        ("system_notifications_checkbox", "settings.system_notifications"),
        ("debug_checkbox", "settings.enable_debug_logging"),
        ("show_workspace_tabs_checkbox", "settings.show_workspace_tabs"),
        ("radio_ui_mode_beginner", "settings.ui_mode_beginner"),
        ("radio_ui_mode_advanced", "settings.ui_mode_advanced"),
        ("radio_ui_mode_expert", "settings.ui_mode_expert"),
        ("radio_font_builtin", "settings.builtin_font"),
        ("radio_font_system_default", "settings.system_default"),
        ("radio_font_system_custom", "settings.custom"),
        ("optimize_movement_checkbox", "settings.optimize_magnifier_movement"),
        ("laser_smoothing_checkbox", "settings.optimize_laser_smoothing"),
        (
            "magnifier_intersection_highlight_checkbox",
            "settings.magnifier_intersection_highlight",
        ),
        (
            "magnifier_auto_color_checkbox",
            "settings.magnifier_auto_color_new_instances",
        ),
        ("crop_checkbox", "settings.autocrop_black_borders_on_load"),
        ("auto_psnr_checkbox", "settings.autocalculate_psnr"),
        ("auto_ssim_checkbox", "settings.autocalculate_ssim"),
        ("lbl_zoom_interp", "settings.zoom_interpolation"),
        ("lbl_rhi_backend_hint", "settings.render_backend_restart_hint"),
    ]
    for attr, key in candidates:
        widget = getattr(dialog, attr, None)
        if widget is not None:
            widget.setText(dialog.tr(key, lang))


def _apply_group_titles(dialog, lang: str) -> None:
    groups = [
        ("lang_group", "label.language"),
        ("general_group", "settings.general"),
        ("appearance_group", "settings.appearance"),
        ("ui_mode_group", "settings.ui_mode"),
        ("font_group", "settings.ui_font"),
        ("other_ui_group", "settings.maximum_name_length_ui"),
        ("res_group", "settings.display_cache_resolution"),
        ("interactive_opt_group", "settings.interactive_optimization"),
        ("render_backend_group", "settings.render_backend"),
        ("auto_group", "settings.auto"),
        ("metrics_group", "label.details"),
    ]

    for attr_name, key in groups:
        group = getattr(dialog, attr_name, None)
        if group is not None:
            group.set_title(dialog.tr(key, lang))


def _apply_label_with_colon(dialog, lang: str) -> None:
    theme_label = getattr(dialog, "theme_label", None)
    if theme_label is not None:
        theme_label.setText(dialog.tr("label.theme", lang) + ":")
    rhi_label = getattr(dialog, "lbl_rhi_backend", None)
    if rhi_label is not None:
        rhi_label.setText(dialog.tr("settings.render_backend_label", lang) + ":")


_RHI_BACKEND_KEY_MAP = {
    "default": "settings.render_backend_default",
    "opengl": "settings.render_backend_opengl",
    "vulkan": "settings.render_backend_vulkan",
    "d3d11": "settings.render_backend_d3d11",
    "d3d12": "settings.render_backend_d3d12",
    "metal": "settings.render_backend_metal",
}


def _rebuild_rhi_backend_combo(dialog, lang: str) -> None:
    combo = getattr(dialog, "combo_rhi_backend", None)
    if combo is None:
        return
    current = combo.currentData()
    items = [
        (combo.itemData(i), _RHI_BACKEND_KEY_MAP.get(combo.itemData(i), ""))
        for i in range(combo.count())
    ]
    combo.clear()
    for value, key in items:
        text = dialog.tr(key, lang) if key else str(value)
        combo.addItem(text, userData=value)
    idx = combo.findData(current)
    if idx != -1:
        combo.setCurrentIndex(idx)


def _rebuild_theme_combo(dialog, lang: str) -> None:
    combo = getattr(dialog, "combo_theme", None)
    if combo is None:
        return
    current = combo.currentData()
    combo.clear()
    for key in _THEME_KEYS:
        combo.addItem(dialog.tr(f"settings.{key}", lang), key)
    idx = combo.findData(current)
    if idx != -1:
        combo.setCurrentIndex(idx)


def _rebuild_font_family_combo(dialog, lang: str) -> None:
    from PySide6.QtGui import QFontDatabase

    combo = getattr(dialog, "combo_font_family", None)
    if combo is None:
        return
    current = combo.currentData()
    combo.clear()
    for fam in QFontDatabase.families():
        combo.addItem(fam, fam)
    idx = combo.findData(current or "")
    if idx != -1:
        combo.setCurrentIndex(idx)


def _rebuild_resolution_combo(dialog, lang: str) -> None:
    combo = getattr(dialog, "combo_resolution", None)
    if combo is None:
        return
    current = combo.currentData()
    combo.clear()
    for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
        translated = dialog.tr(_RESOLUTION_KEY_MAP.get(name_key, name_key), lang)
        combo.addItem(translated, userData=limit)
    idx = combo.findData(current)
    if idx != -1:
        combo.setCurrentIndex(idx)


def _rebuild_interpolation_combos(dialog, lang: str) -> None:
    if not all(
        hasattr(dialog, name)
        for name in ("combo_mag_interp", "combo_laser_interp", "combo_zoom_interp")
    ):
        return
    current_mag = dialog.combo_mag_interp.currentData()
    current_laser = dialog.combo_laser_interp.currentData()
    current_zoom = dialog.combo_zoom_interp.currentData()

    dialog.combo_mag_interp.clear()
    dialog.combo_laser_interp.clear()
    for key in AppConstants.INTERPOLATION_METHODS_MAP.keys():
        text = dialog.tr(_INTERPOLATION_KEY_MAP.get(key, key), lang)
        dialog.combo_mag_interp.addItem(text, key)
        dialog.combo_laser_interp.addItem(text, key)

    dialog.combo_zoom_interp.clear()
    for key in ("NEAREST", "BILINEAR"):
        dialog.combo_zoom_interp.addItem(
            dialog.tr(_INTERPOLATION_KEY_MAP[key], lang), key
        )

    for combo, value in (
        (dialog.combo_mag_interp, current_mag),
        (dialog.combo_laser_interp, current_laser),
        (dialog.combo_zoom_interp, current_zoom),
    ):
        idx = combo.findData(value)
        if idx != -1:
            combo.setCurrentIndex(idx)
