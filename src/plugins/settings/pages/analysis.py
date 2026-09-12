"""Analysis page — image-compare specific metrics and auto-crop.

Registration is owned by ``ImageCompareTab`` via
``create_service("contribute_settings", registry)``; this module only
exposes the page-building function and its Find Action ``SEARCH`` index.
The page can host tab-owned performance extras (``extras_section_id``) the
same way ``builtin.performance`` hosts its extras — the section id is passed
in by the registering tab, so this platform module stays tab-agnostic.
"""

from __future__ import annotations

from PySide6.QtWidgets import QSizePolicy
from sli_ui_toolkit.widgets import CheckBox

from plugins.settings.nav_rows import page_nav_builder, register_page_navigation
from plugins.settings.search import SearchIndex, group

AUTO = group("settings.auto", "settings.autocrop_black_borders_on_load")
METRICS = group(
    "label.details",
    "settings.autocalculate_psnr",
    "settings.autocalculate_ssim",
)
SEARCH = SearchIndex.of(AUTO, METRICS)


def build(dialog, p, *, extras_section_id: str | None = None):
    dialog.page_analysis, layout = dialog._create_scrollable_page()
    builder = page_nav_builder(dialog, tag="settings-analysis")
    if extras_section_id:
        # Host tab-owned perf extras on this page: they read
        # ``dialog._perf_layout`` (same contract the shared performance page
        # used to provide). Extras are ambient — no active-tab filtering.
        from plugins.settings.registry import get_settings_registry

        dialog._perf_layout = layout
        for extra in get_settings_registry().extras_for(
            extras_section_id,
            getattr(dialog, "active_tab", None),
        ):
            # An extra can return the nav rows it built so they
            # participate in this page's keyboard navigation instead of
            # being silently invisible to it (the bug this migration fixes
            # — see docs/legacy/plan_navigation_descriptor_unification.md
            # §2.2).
            builder.extend(extra(dialog, p) or [])
    _build_auto_crop_group(dialog, layout, p, builder)
    _build_metrics_group(dialog, layout, p, builder)
    register_page_navigation(dialog, dialog.page_analysis, builder)
    dialog.pages_stack.addWidget(dialog.page_analysis)


def _build_auto_crop_group(dialog, layout, p, builder):
    dialog.auto_group = AUTO.widget(dialog)
    dialog.crop_checkbox = CheckBox(
        AUTO.text(dialog, "settings.autocrop_black_borders_on_load")
    )
    dialog.crop_checkbox.setChecked(p.auto_crop_black_borders)
    AUTO.tag_member(dialog.crop_checkbox, "settings.autocrop_black_borders_on_load")
    dialog.crop_checkbox.setSizePolicy(
        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
    )
    crop_row = builder.row(dialog.crop_checkbox)
    dialog.auto_group.add_widget(crop_row)
    layout.addWidget(dialog.auto_group)


def _build_metrics_group(dialog, layout, p, builder):
    dialog.metrics_group = METRICS.widget(dialog)
    dialog.auto_psnr_checkbox = CheckBox(
        METRICS.text(dialog, "settings.autocalculate_psnr")
    )
    dialog.auto_psnr_checkbox.setChecked(p.auto_calculate_psnr)
    METRICS.tag_member(dialog.auto_psnr_checkbox, "settings.autocalculate_psnr")
    psnr_row = builder.row(dialog.auto_psnr_checkbox)
    dialog.metrics_group.add_widget(psnr_row)
    dialog.auto_ssim_checkbox = CheckBox(
        METRICS.text(dialog, "settings.autocalculate_ssim")
    )
    dialog.auto_ssim_checkbox.setChecked(p.auto_calculate_ssim)
    METRICS.tag_member(dialog.auto_ssim_checkbox, "settings.autocalculate_ssim")
    ssim_row = builder.row(dialog.auto_ssim_checkbox)
    dialog.metrics_group.add_widget(ssim_row)
    layout.addWidget(dialog.metrics_group)
