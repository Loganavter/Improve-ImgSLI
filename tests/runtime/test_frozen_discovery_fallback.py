"""Frozen / datas-only layouts must still discover tabs and plugins."""

from __future__ import annotations

import importlib
import importlib.machinery
import logging
import pkgutil
import sys
from pathlib import Path

import pytest

from core.plugin_system import discovery_scan
from core.plugin_system.discovery_scan import (
    iter_plugin_entry_points,
    iter_tab_entry_points,
)

#: Packages under ``src/tabs`` that carry no ``tab.py`` (``use_cases`` is the
#: live one): the import fallback has to skip them, not report them as broken.
_NOT_A_TAB_PACKAGE = "use_cases"


def _datas_only_src(tmp_path: Path) -> Path:
    """Mimic a PyInstaller onedir datas tree: resources present, no *.py."""
    src = tmp_path / "src"
    for package in ("image_compare", "session_picker", "multi_compare"):
        (src / "tabs" / package / "resources" / "i18n").mkdir(parents=True)
    for plugin in ("settings", "export"):
        (src / "plugins" / plugin / "resources" / "i18n").mkdir(parents=True)
    return src


def _tab_failures(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        rec
        for rec in caplog.records
        if rec.name == discovery_scan.logger.name
        and rec.levelno >= logging.ERROR
        and "Import-based tab discovery failed" in rec.getMessage()
    ]


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


def test_import_fallback_skips_packages_without_a_tab_module(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A package with no ``tab.py`` is not a broken tab.

    A frozen tree has no sources, so every ``tabs/<name>`` package is a
    candidate; ``use_cases`` never ships a ``tab.py``. It must be skipped
    before the import (one ERROR + traceback per start otherwise) while the
    discovered tab set stays exactly the same.
    """
    with caplog.at_level(logging.DEBUG, logger=discovery_scan.logger.name):
        entries = iter_tab_entry_points(src_root=_datas_only_src(tmp_path))

    assert {e.package_name: e.startup_tier for e in entries} == {
        "image_compare": "bootstrap",
        "image_gallery": "deferred",
        "multi_compare": "deferred",
        "session_picker": "bootstrap",
    }
    skipped = [
        rec
        for rec in caplog.records
        if rec.name == discovery_scan.logger.name
        and f"tabs.{_NOT_A_TAB_PACKAGE}.tab" in rec.getMessage()
    ]
    assert [rec.levelno for rec in skipped] == [logging.DEBUG]
    assert _tab_failures(caplog) == []


def test_import_fallback_keeps_loud_error_for_a_module_that_fails_to_import(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``find_spec`` may only skip what does not exist, never a real failure."""
    broken = "tabs.broken_tab.tab"
    spec = importlib.machinery.ModuleSpec(broken, loader=None)
    monkeypatch.setitem(sys.modules, broken, importlib.util.module_from_spec(spec))

    real_iter_modules = pkgutil.iter_modules
    monkeypatch.setattr(
        discovery_scan.pkgutil,
        "iter_modules",
        lambda path: [*real_iter_modules(path), (None, "broken_tab", True)],
    )
    real_import_module = importlib.import_module

    def _import_or_raise(name: str, package: str | None = None):
        if name == broken:
            raise RuntimeError("tab module exploded on import")
        return real_import_module(name, package=package)

    monkeypatch.setattr(discovery_scan.importlib, "import_module", _import_or_raise)

    with caplog.at_level(logging.ERROR, logger=discovery_scan.logger.name):
        entries = iter_tab_entry_points(src_root=_datas_only_src(tmp_path))

    failures = _tab_failures(caplog)
    assert len(failures) == 1
    assert broken in failures[0].getMessage()
    assert failures[0].exc_info is not None
    assert broken not in {e.module_name for e in entries}


def test_import_fallback_survives_find_spec_errors(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``find_spec`` raises for a broken parent or a relative name; keep going.

    ``ImportError`` / ``ValueError`` mean "not resolvable" (skipped); anything
    else is left to the import below, which reports it — the scan itself never
    aborts and never hides a resolvable tab.
    """
    real_find_spec = importlib.util.find_spec

    def _find_spec_or_raise(name: str, package: str | None = None):
        if name == "tabs.image_compare.tab":
            raise ImportError(f"broken parent package for {name}")
        if name == "tabs.session_picker.tab":
            raise ValueError("relative module name")
        if name == "tabs.multi_compare.tab":
            raise RuntimeError("metadata lookup blew up")
        return real_find_spec(name, package)

    monkeypatch.setattr(discovery_scan.importlib.util, "find_spec", _find_spec_or_raise)

    with caplog.at_level(logging.ERROR, logger=discovery_scan.logger.name):
        entries = iter_tab_entry_points(src_root=_datas_only_src(tmp_path))

    # image_gallery resolves normally; multi_compare fell through to its import.
    assert {e.package_name for e in entries} == {"image_gallery", "multi_compare"}
    assert _tab_failures(caplog) == []
