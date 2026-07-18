"""Staged plugin discovery — bootstrap vs deferred tiers."""

from __future__ import annotations

import core.plugin_system.registry as registry_mod
from core.plugin_system.registry import PluginRegistry


def test_bootstrap_tier_omits_deferred_plugins():
    registry = PluginRegistry(app_context=object())
    created = list(registry.discover_plugins(tier="bootstrap"))
    names = {p._plugin_meta["name"] for p in created if hasattr(p, "_plugin_meta")}

    assert "comparison" in names
    assert "settings" in names
    assert "session_picker" in names
    assert "export" not in names
    assert "video_editor" not in names
    assert "multi_compare" not in names


def test_deferred_tier_adds_export_and_video_editor():
    registry = PluginRegistry(app_context=object())
    registry.discover_plugins(tier="bootstrap")

    created = list(registry.discover_plugins(tier="deferred"))
    names = {p._plugin_meta["name"] for p in created if hasattr(p, "_plugin_meta")}

    assert "export" in names
    assert "video_editor" in names
    assert "multi_compare" in names
    assert registry.get_plugin("video_editor") is not None
    assert registry.get_plugin("export") is not None


def test_deferred_export_sees_video_editor_via_coordinator():
    from core.bootstrap import ApplicationContext

    ctx = ApplicationContext()
    ctx._build_core_services()
    ctx._load_persistent_state()
    ctx._configure_theme_manager()
    ctx._build_runtime_services()
    ctx._initialize_plugins()

    ctx.load_deferred_plugins()

    export = ctx.plugin_coordinator.get_plugin("export")
    video = ctx.plugin_coordinator.get_plugin("video_editor")
    assert export is not None
    assert video is not None
    assert export.video_editor_plugin is video


def test_load_deferred_plugins_reapplies_app_stylesheet(qapp, monkeypatch):
    """Deferred QSS (video editor tabs) must be pushed to QApplication, not only templated."""
    from core.bootstrap import ApplicationContext
    from core.theme import LIGHT_THEME_PALETTE, DARK_THEME_PALETTE
    from sli_ui_toolkit.theme import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(LIGHT_THEME_PALETTE, DARK_THEME_PALETTE)

    ctx = ApplicationContext()
    ctx._build_core_services()
    ctx._load_persistent_state()
    ctx._configure_theme_manager()
    ctx._build_runtime_services()
    ctx._initialize_plugins()
    tm.apply_theme_to_app(qapp)

    calls: list[object] = []
    original = ThemeManager.apply_theme_to_app

    def _spy(self, app):
        calls.append(app)
        return original(self, app)

    monkeypatch.setattr(ThemeManager, "apply_theme_to_app", _spy)
    started = ctx.load_deferred_plugins()

    assert "video_editor" in started
    assert qapp in calls
    assert "VideoEditorTabs" in qapp.styleSheet()
    assert "VideoEditorTabs #TopTabBar" in qapp.styleSheet()


def test_bootstrap_tier_is_idempotent():
    registry = PluginRegistry(app_context=object())
    first = list(registry.discover_plugins(tier="bootstrap"))
    second = list(registry.discover_plugins(tier="bootstrap"))
    assert len(first) >= 3
    assert second == []
