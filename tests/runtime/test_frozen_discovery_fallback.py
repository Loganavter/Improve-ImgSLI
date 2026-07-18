"""Frozen / datas-only layouts must still discover tabs and plugins."""

from __future__ import annotations

from pathlib import Path

from core.plugin_system.discovery_scan import (
    iter_plugin_entry_points,
    iter_tab_entry_points,
)


def _datas_only_src(tmp_path: Path) -> Path:
    """Mimic a PyInstaller onedir datas tree: resources present, no *.py."""
    src = tmp_path / "src"
    for package in ("image_compare", "session_picker", "multi_compare"):
        (src / "tabs" / package / "resources" / "i18n").mkdir(parents=True)
    for plugin in ("settings", "export"):
        (src / "plugins" / plugin / "resources" / "i18n").mkdir(parents=True)
    return src


def test_tab_discovery_falls_back_when_tab_py_missing(tmp_path: Path) -> None:
    entries = iter_tab_entry_points(src_root=_datas_only_src(tmp_path))
    tiers = {e.package_name: e.startup_tier for e in entries}
    assert tiers["image_compare"] == "bootstrap"
    assert tiers["session_picker"] == "bootstrap"
    assert tiers["multi_compare"] == "deferred"


def test_plugin_discovery_falls_back_when_plugin_py_missing(tmp_path: Path) -> None:
    entries = iter_plugin_entry_points(src_root=_datas_only_src(tmp_path))
    by_name = {e.plugin_name: e.startup_tier for e in entries}
    assert by_name["settings"] == "bootstrap"
    assert by_name["export"] == "deferred"
    assert "video_editor" in by_name
