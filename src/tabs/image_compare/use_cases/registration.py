"""Settings-section / Find-Action registration for ``ImageCompareTab`` --
split out to keep that class down to the ``TabContract`` surface itself.
"""

from __future__ import annotations


def register_settings(tab, registry) -> None:
    from plugins.settings.pages.analysis import build as build_analysis
    from plugins.settings.registry import SettingsSection
    from tabs.image_compare.ui.settings_performance import build_image_perf_extras
    from tabs.image_compare.icons import Icon, get_icon

    from plugins.settings.pages.analysis import SEARCH as ANALYSIS_SEARCH
    from tabs.image_compare.ui.settings_performance import SEARCH as PERF_EXTRA_SEARCH

    registry.add(
        SettingsSection(
            section_id="image_compare.analysis",
            title_key="label.details",
            icon=get_icon(Icon.HIGHLIGHT_DIFFERENCES),
            build=build_analysis,
            owner_tab=tab.session_type,
            order=40,
            action_description_key="action.settings.analysis_desc",
            search=ANALYSIS_SEARCH,
        )
    )
    registry.add_section_extra(
        "builtin.performance",
        build_image_perf_extras,
        owner_tab=tab.session_type,
        order=10,
        search=PERF_EXTRA_SEARCH,
    )


def register_actions(tab, registry) -> None:
    if tab._widget is None:
        return
    from tabs.image_compare.actions import register_image_compare_actions

    register_image_compare_actions(
        widget=tab._widget,
        presenter=None,
        registry=registry,
    )
    resync_action_shortcuts(tab)


def resync_action_shortcuts(tab) -> None:
    from PySide6.QtWidgets import QApplication

    from ui.actions.binder import resync_action_shortcuts as _resync

    for widget in QApplication.topLevelWidgets():
        if getattr(widget, "presenter", None) is not None:
            _resync(widget, active_tab=tab.session_type)
            return
