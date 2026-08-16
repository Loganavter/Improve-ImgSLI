"""Per-tab settings sections are ambient — visible from any session context.

Contract: ``SettingsRegistry.sections_for`` returns every registered section
(built-in + tab-owned) regardless of the active workspace session, and the
Settings dialog sidebar shows tab sections titled by the tab's localized name
from any context (the session picker included — the app's start screen where
tab settings used to be invisible).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

pytestmark = pytest.mark.usefixtures("qtbot")


@pytest.fixture(scope="module")
def app():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture()
def registry(app):
    from plugins.settings.registry import ensure_tab_settings_contributions, get_settings_registry
    from tabs.registry import TabRegistry

    tab_registry = TabRegistry()
    tab_registry.discover()
    tab_registry.contribute_all_settings()
    ensure_tab_settings_contributions()
    return get_settings_registry()


def _section_ids(registry, active_tab):
    return [s.section_id for s in registry.sections_for(active_tab)]


def test_sections_for_is_identical_across_session_contexts(registry):
    ids_none = _section_ids(registry, None)
    assert "builtin.general" in ids_none
    assert "builtin.performance" in ids_none
    assert "image_compare.analysis" in ids_none
    assert "image_gallery.ai" in ids_none
    assert ids_none == _section_ids(registry, "session_picker")
    assert ids_none == _section_ids(registry, "image_compare")
    assert ids_none == _section_ids(registry, "multi_compare")


def test_tab_sections_titled_after_the_tab(registry):
    by_id = {s.section_id: s for s in registry.all_sections()}
    assert by_id["image_compare.analysis"].title_key == "image_compare.session_type"
    assert by_id["image_gallery.ai"].title_key == "image_gallery.tab_name"
    # owner_tab stays as metadata on the section.
    assert by_id["image_compare.analysis"].owner_tab == "image_compare"
    assert by_id["image_gallery.ai"].owner_tab == "image_gallery"


def test_perf_extras_live_on_the_tab_section_not_platform_page(registry):
    ic = next(
        s for s in registry.all_sections() if s.section_id == "image_compare.analysis"
    )
    perf = next(
        s for s in registry.all_sections() if s.section_id == "builtin.performance"
    )
    merged_ic = registry.search_for(ic, active_tab="session_picker")
    assert "settings.optimize_magnifier_movement" in merged_ic.keys
    merged_perf = registry.search_for(perf, active_tab="image_compare")
    assert "settings.optimize_magnifier_movement" not in merged_perf.keys
    assert "settings.render_backend_vulkan" in merged_perf.keys


def test_dialog_sidebar_shows_tab_sections_from_session_picker(app, registry):
    from plugins.settings.dialog import SettingsDialog

    dialog = SettingsDialog(
        current_language="en",
        current_theme="dark",
        current_max_length=30,
        min_limit=1,
        max_limit=200,
        debug_mode_enabled=False,
        system_notifications_enabled=True,
        current_resolution_limit=0,
        active_tab="session_picker",
    )
    try:
        titles = [title for title, _icon in dialog._sidebar_items_data]
        assert "Image Compare" in titles
        assert "Image Gallery" in titles
        # The tab page hosts the perf groups; the platform page does not.
        dialog.select_section("image_compare.analysis")
        assert hasattr(dialog, "combo_resolution")
        assert hasattr(dialog, "interactive_opt_group")

        def _under(widget, page):
            parent = widget.parentWidget()
            while parent is not None:
                if parent is page:
                    return True
                parent = parent.parentWidget()
            return False

        assert _under(dialog.res_group, dialog.page_analysis)
        assert not _under(dialog.res_group, dialog.page_perf)
        assert not _under(dialog.combo_rhi_backend, dialog.page_analysis)
        assert _under(dialog.combo_rhi_backend, dialog.page_perf)
    finally:
        dialog.deleteLater()