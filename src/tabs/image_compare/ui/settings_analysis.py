"""Analysis page — image-compare specific metrics and auto-crop.

Registration is owned by ``ImageCompareTab`` via
``create_service("contribute_settings", registry)``; this module only
exposes the page-building function. Field values live in
``p.tab_extras["image_compare_performance"]``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy
from sli_ui_toolkit.widgets import CheckBox, CustomGroupWidget

from tabs.image_compare.ui.settings_payload import (
    SECTION_ID as _PERF_SECTION_ID,
    defaults as _perf_defaults,
)


def _perf(p) -> dict:
    section = p.get_section(_PERF_SECTION_ID)
    if not section:
        return _perf_defaults()
    merged = _perf_defaults()
    merged.update(section)
    return merged


def build(dialog, p):
    perf = _perf(p)
    dialog.page_analysis, layout = dialog._create_scrollable_page()
    dialog.auto_group = CustomGroupWidget(
        dialog.tr("settings.auto", dialog.current_language)
    )
    dialog.crop_checkbox = CheckBox(
        dialog.tr("settings.autocrop_black_borders_on_load", dialog.current_language)
    )
    dialog.crop_checkbox.setChecked(bool(perf["auto_crop_black_borders"]))
    dialog.crop_checkbox.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    dialog.auto_group.add_widget(dialog.crop_checkbox)
    layout.addWidget(dialog.auto_group)

    dialog.metrics_group = CustomGroupWidget(
        dialog.tr("label.details", dialog.current_language)
    )
    dialog.auto_psnr_checkbox = CheckBox(
        dialog.tr("settings.autocalculate_psnr", dialog.current_language)
    )
    dialog.auto_psnr_checkbox.setChecked(bool(perf["auto_calculate_psnr"]))
    dialog.metrics_group.add_widget(dialog.auto_psnr_checkbox)
    dialog.auto_ssim_checkbox = CheckBox(
        dialog.tr("settings.autocalculate_ssim", dialog.current_language)
    )
    dialog.auto_ssim_checkbox.setChecked(bool(perf["auto_calculate_ssim"]))
    dialog.metrics_group.add_widget(dialog.auto_ssim_checkbox)
    layout.addWidget(dialog.metrics_group)
    dialog.pages_stack.addWidget(dialog.page_analysis)
