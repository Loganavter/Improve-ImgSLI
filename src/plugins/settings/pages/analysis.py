"""Analysis page — image-compare specific metrics and auto-crop.

Registration is owned by ``ImageCompareTab`` via
``create_service("contribute_settings", registry)``; this module only
exposes the page-building function and its Find Action ``SEARCH`` index.
"""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy
from sli_ui_toolkit.widgets import CheckBox

from plugins.settings.search import SearchIndex, group

AUTO = group("settings.auto", "settings.autocrop_black_borders_on_load")
METRICS = group(
    "label.details",
    "settings.autocalculate_psnr",
    "settings.autocalculate_ssim",
)
SEARCH = SearchIndex.of(AUTO, METRICS)


def build(dialog, p):
    dialog.page_analysis, layout = dialog._create_scrollable_page()
    dialog.auto_group = AUTO.widget(dialog)
    dialog.crop_checkbox = CheckBox(
        AUTO.text(dialog, "settings.autocrop_black_borders_on_load")
    )
    dialog.crop_checkbox.setChecked(p.auto_crop_black_borders)
    AUTO.tag_member(dialog.crop_checkbox, "settings.autocrop_black_borders_on_load")
    dialog.crop_checkbox.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    dialog.auto_group.add_widget(dialog.crop_checkbox)
    layout.addWidget(dialog.auto_group)

    dialog.metrics_group = METRICS.widget(dialog)
    dialog.auto_psnr_checkbox = CheckBox(
        METRICS.text(dialog, "settings.autocalculate_psnr")
    )
    dialog.auto_psnr_checkbox.setChecked(p.auto_calculate_psnr)
    METRICS.tag_member(dialog.auto_psnr_checkbox, "settings.autocalculate_psnr")
    dialog.metrics_group.add_widget(dialog.auto_psnr_checkbox)
    dialog.auto_ssim_checkbox = CheckBox(
        METRICS.text(dialog, "settings.autocalculate_ssim")
    )
    dialog.auto_ssim_checkbox.setChecked(p.auto_calculate_ssim)
    METRICS.tag_member(dialog.auto_ssim_checkbox, "settings.autocalculate_ssim")
    dialog.metrics_group.add_widget(dialog.auto_ssim_checkbox)
    layout.addWidget(dialog.metrics_group)
    dialog.pages_stack.addWidget(dialog.page_analysis)
