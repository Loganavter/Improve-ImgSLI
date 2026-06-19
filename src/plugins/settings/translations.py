from __future__ import annotations

from core.constants import AppConstants
from sli_ui_toolkit.i18n import TranslationsBinder


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


def build_translations_binder(dialog) -> TranslationsBinder:
    """Build a TranslationsBinder for SettingsDialog.

    Takes a fully initialized dialog and registers all string updates.
    Combo boxes whose items need re-translation are rebuilt via callbacks.
    """
    binder = TranslationsBinder(tr_func=dialog.tr)

    binder.bind_callback(
        lambda lang: dialog.setWindowTitle(dialog.tr("misc.settings", lang))
    )

    _bind_buttons(binder, dialog)
    _bind_simple_texts(binder, dialog)
    _bind_group_titles(binder, dialog)
    _bind_label_with_colon(binder, dialog)
    _bind_combo_rebuilds(binder, dialog)

    return binder


def _bind_buttons(binder: TranslationsBinder, dialog) -> None:
    binder.bind_text(dialog.ok_button, "common.ok")
    binder.bind_text(dialog.cancel_button, "common.cancel")


def _bind_simple_texts(binder: TranslationsBinder, dialog) -> None:
    items = [
        (dialog.system_notifications_checkbox, "settings.system_notifications"),
        (dialog.debug_checkbox, "settings.enable_debug_logging"),
        (dialog.show_workspace_tabs_checkbox, "settings.show_workspace_tabs"),
        (dialog.radio_ui_mode_beginner, "settings.ui_mode_beginner"),
        (dialog.radio_ui_mode_advanced, "settings.ui_mode_advanced"),
        (dialog.radio_ui_mode_expert, "settings.ui_mode_expert"),
        (dialog.radio_font_builtin, "settings.builtin_font"),
        (dialog.radio_font_system_default, "settings.system_default"),
        (dialog.radio_font_system_custom, "settings.custom"),
        (dialog.optimize_movement_checkbox, "settings.optimize_magnifier_movement"),
        (dialog.laser_smoothing_checkbox, "settings.optimize_laser_smoothing"),
        (dialog.magnifier_intersection_highlight_checkbox,
         "settings.magnifier_intersection_highlight"),
        (dialog.magnifier_auto_color_checkbox,
         "settings.magnifier_auto_color_new_instances"),
        (dialog.crop_checkbox, "settings.autocrop_black_borders_on_load"),
        (dialog.auto_psnr_checkbox, "settings.autocalculate_psnr"),
        (dialog.auto_ssim_checkbox, "settings.autocalculate_ssim"),
        (dialog.lbl_zoom_interp, "settings.zoom_interpolation"),
    ]
    for widget, key in items:
        binder.bind_text(widget, key)


def _bind_group_titles(binder: TranslationsBinder, dialog) -> None:
    groups = [
        ("lang_group", "label.language"),
        ("sys_group", "settings.appearance"),
        ("ui_mode_group", "settings.ui_mode"),
        ("font_group", "settings.ui_font"),
        ("other_ui_group", "settings.maximum_name_length_ui"),
        ("res_group", "settings.display_cache_resolution"),
        ("interactive_opt_group", "settings.interactive_optimization"),
        ("auto_group", "settings.auto"),
        ("metrics_group", "label.details"),
    ]

    def _make(attr_name: str, key: str):
        def _apply(lang: str) -> None:
            group = getattr(dialog, attr_name, None)
            if group is not None:
                group.set_title(dialog.tr(key, lang))
        return _apply

    for attr_name, key in groups:
        binder.bind_callback(_make(attr_name, key))


def _bind_label_with_colon(binder: TranslationsBinder, dialog) -> None:
    binder.bind_text(dialog.theme_label, "label.theme", suffix=":")


def _bind_combo_rebuilds(binder: TranslationsBinder, dialog) -> None:
    binder.bind_callback(lambda lang: _rebuild_theme_combo(dialog, lang))
    binder.bind_callback(lambda lang: _rebuild_font_family_combo(dialog, lang))
    binder.bind_callback(lambda lang: _rebuild_resolution_combo(dialog, lang))
    binder.bind_callback(lambda lang: _rebuild_interpolation_combos(dialog, lang))


def _rebuild_theme_combo(dialog, lang: str) -> None:
    current = dialog.combo_theme.currentData()
    dialog.combo_theme.clear()
    for key in _THEME_KEYS:
        dialog.combo_theme.addItem(dialog.tr(f"settings.{key}", lang), key)
    idx = dialog.combo_theme.findData(current)
    if idx != -1:
        dialog.combo_theme.setCurrentIndex(idx)


def _rebuild_font_family_combo(dialog, lang: str) -> None:
    from PySide6.QtGui import QFontDatabase

    current = dialog.combo_font_family.currentData()
    dialog.combo_font_family.clear()
    for fam in QFontDatabase.families():
        dialog.combo_font_family.addItem(fam, fam)
    idx = dialog.combo_font_family.findData(current or "")
    if idx != -1:
        dialog.combo_font_family.setCurrentIndex(idx)


def _rebuild_resolution_combo(dialog, lang: str) -> None:
    current = dialog.combo_resolution.currentData()
    dialog.combo_resolution.clear()
    for name_key, limit in AppConstants.DISPLAY_RESOLUTION_OPTIONS.items():
        translated = dialog.tr(_RESOLUTION_KEY_MAP.get(name_key, name_key), lang)
        dialog.combo_resolution.addItem(translated, userData=limit)
    idx = dialog.combo_resolution.findData(current)
    if idx != -1:
        dialog.combo_resolution.setCurrentIndex(idx)


def _rebuild_interpolation_combos(dialog, lang: str) -> None:
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
