"""Analysis page — image-compare specific metrics and auto-crop."""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.widgets import CheckBox, CustomGroupWidget
from ui.icon_manager import AppIcon

from plugins.settings.registry import SettingsSection


def build(dialog, p):
    dialog.page_analysis, layout = dialog._create_scrollable_page()
    dialog.auto_group = CustomGroupWidget(dialog.tr("settings.auto", dialog.current_language))
    dialog.crop_checkbox = CheckBox(
        dialog.tr("settings.autocrop_black_borders_on_load", dialog.current_language)
    )
    dialog.crop_checkbox.setChecked(p.auto_crop_black_borders)
    dialog.crop_checkbox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    dialog.auto_group.add_widget(dialog.crop_checkbox)
    layout.addWidget(dialog.auto_group)

    dialog.metrics_group = CustomGroupWidget(dialog.tr("label.details", dialog.current_language))
    dialog.auto_psnr_checkbox = CheckBox(
        dialog.tr("settings.autocalculate_psnr", dialog.current_language)
    )
    dialog.auto_psnr_checkbox.setChecked(p.auto_calculate_psnr)
    dialog.metrics_group.add_widget(dialog.auto_psnr_checkbox)
    dialog.auto_ssim_checkbox = CheckBox(
        dialog.tr("settings.autocalculate_ssim", dialog.current_language)
    )
    dialog.auto_ssim_checkbox.setChecked(p.auto_calculate_ssim)
    dialog.metrics_group.add_widget(dialog.auto_ssim_checkbox)
    layout.addWidget(dialog.metrics_group)
    dialog.pages_stack.addWidget(dialog.page_analysis)


SECTION = SettingsSection(
    section_id="builtin.analysis",
    title_key="label.details",
    icon=AppIcon.HIGHLIGHT_DIFFERENCES,
    build=build,
    owner_tab="image_compare",
    order=40,
)
