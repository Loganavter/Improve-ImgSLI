"""Contract: every plugin entry point declares startup_tier via @plugin."""

from __future__ import annotations

from core.plugin_system.discovery_scan import (
    iter_plugin_entry_points,
    iter_tab_entry_points,
)


def test_every_plugin_entry_point_declares_startup_tier():
    entries = iter_plugin_entry_points()
    assert len(entries) >= 9
    tiers = {e.plugin_name: e.startup_tier for e in entries}
    assert tiers["comparison"] == "bootstrap"
    assert tiers["settings"] == "bootstrap"
    assert tiers["export"] == "deferred"
    assert tiers["video_editor"] == "deferred"


def test_plugin_scan_finds_nested_video_editor():
    modules = {e.module_name for e in iter_plugin_entry_points()}
    assert "tabs.image_compare.plugins.video_editor.plugin" in modules


def test_bootstrap_and_deferred_plugin_sets_are_disjoint():
    entries = iter_plugin_entry_points()
    bootstrap = {e.plugin_name for e in entries if e.startup_tier == "bootstrap"}
    deferred = {e.plugin_name for e in entries if e.startup_tier == "deferred"}
    assert bootstrap == {
        "comparison",
        "layout",
        "onboarding",
        "session_picker",
        "settings",
    }
    assert "export" in deferred
    assert "video_editor" in deferred
    assert bootstrap.isdisjoint(deferred)


def test_video_editor_loads_before_export():
    entries = [e for e in iter_plugin_entry_points() if e.startup_tier == "deferred"]
    by_name = {e.plugin_name: e.startup_order for e in entries}
    assert by_name["video_editor"] < by_name["export"]


def test_every_tab_declares_startup_tier():
    entries = iter_tab_entry_points()
    assert len(entries) >= 3
    tiers = {e.package_name: e.startup_tier for e in entries}
    assert tiers["image_compare"] == "bootstrap"
    assert tiers["session_picker"] == "bootstrap"
    assert tiers["multi_compare"] == "deferred"
