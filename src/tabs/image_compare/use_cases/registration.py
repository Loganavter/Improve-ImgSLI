"""Settings-section / Find-Action registration for ``ImageCompareTab`` --
split out to keep that class down to the ``TabContract`` surface itself.
"""

from __future__ import annotations


def _make_analysis_section(tab) -> "SettingsSection":  # type: ignore[no-untyped-def]
    from plugins.settings.registry import SettingsSection
    from tabs.image_compare.icons import Icon, get_icon
    from plugins.settings.pages.analysis import SEARCH as ANALYSIS_SEARCH

    def _build_analysis_with_perf_extras(dialog, p):
        from plugins.settings.pages.analysis import build as build_analysis

        build_analysis(dialog, p, extras_section_id="image_compare.analysis")

    return SettingsSection(
        section_id="image_compare.analysis",
        title_key="image_compare.session_type",
        icon=get_icon(Icon.HIGHLIGHT_DIFFERENCES),
        build=_build_analysis_with_perf_extras,
        owner_tab=tab.session_type,
        order=40,
        action_description_key="image_compare.action.settings.analysis_desc",
        search=ANALYSIS_SEARCH,
    )


def _make_analysis_extra() -> "SettingsSectionExtra":  # type: ignore[no-untyped-def]
    from plugins.settings.registry import SettingsSectionExtra
    from tabs.image_compare.ui.settings_performance import build_image_perf_extras
    from tabs.image_compare.ui.settings_performance import SEARCH as PERF_EXTRA_SEARCH

    return SettingsSectionExtra(
        section_id="image_compare.analysis",
        build=build_image_perf_extras,
        order=10,
        search=PERF_EXTRA_SEARCH,
    )


def build_settings_contribution(tab):  # type: ignore[no-untyped-def]
    """Return typed ``SettingsContribution`` for ``image_compare``."""
    from plugins.settings.registry import SettingsContribution

    return SettingsContribution(
        owner_tab=tab.session_type,
        sections=(_make_analysis_section(tab),),
        extras=(_make_analysis_extra(),),
    )


def register_settings(tab, registry) -> None:
    contrib = build_settings_contribution(tab)
    for section in contrib.sections:
        registry.add(section)
    for extra in contrib.extras:
        registry.add_section_extra(
            extra.section_id,
            extra.build,
            owner_tab=contrib.owner_tab,
            order=extra.order,
            search=extra.search,
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
    from ui.actions.binder import resync_action_shortcuts as _resync
    from ui.helpers.window_resolver import find_main_window

    window = find_main_window()
    if window is not None:
        _resync(window, active_tab=tab.session_type)
        return
