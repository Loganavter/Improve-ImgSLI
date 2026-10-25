"""Startup micro-costs — one measured win per item (cold-launch recon, P3).

Guards four independent pipeline costs that used to be paid repeatedly or
eagerly during startup:

1. ``ui.main_window.window`` imported ``PIL.Image`` at module scope for one
   constant (``MAX_IMAGE_PIXELS``) — ~35 ms dragged into every importer,
   including tools/tests that never decode an image.
2. The plugin-entry and tab-entry filesystem/AST scans ran once per
   discovery tier (and once more for the session-picker tab grid).
3. ``SettingsManager.load_all_settings`` read every key twice
   (``contains`` + ``value``): 102 QSettings reads for ~51 startup keys.
4. ``contribute_all_help`` re-ran the whole help-tree filesystem scan after
   every page build even when the fragment set was unchanged.

Each test is falsifiable on its own: the counters go red if the exact
duplicate/eager work comes back. Nothing here asserts a *duration*.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


# --------------------------------------------------------------------------
# 1. PIL is not an import-time cost of the window module
# --------------------------------------------------------------------------


def test_window_module_import_does_not_import_pil():
    """Importing the window module must not pull PIL; the constant is lazy.

    Run in a subprocess: the test process itself has already imported PIL
    through other suites, so an in-process ``sys.modules`` check would be
    vacuous.
    """
    script = "\n".join(
        [
            "import sys",
            "import ui.main_window.window as window",
            "assert 'PIL' not in sys.modules, sorted(m for m in sys.modules if m.startswith('PIL'))",
            "assert not any(m.startswith('PIL.') for m in sys.modules)",
            "assert window._pil_pixel_limit_installed is False",
            # The lazy path still applies the real setting, exactly once.
            "window._install_pil_pixel_limit()",
            "import PIL.Image",
            "assert PIL.Image.MAX_IMAGE_PIXELS is None",
            "window._install_pil_pixel_limit()",
            "assert PIL.Image.MAX_IMAGE_PIXELS is None",
            "print('ok')",
        ]
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SRC_ROOT)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("ok")


# --------------------------------------------------------------------------
# 2. Discovery scans run once per process (invalidation hook re-arms them)
# --------------------------------------------------------------------------


def _spy(monkeypatch, module, name: str) -> list[int]:
    calls: list[int] = []
    original = getattr(module, name)

    def wrapper(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return calls


def test_plugin_entry_scan_runs_once_for_all_tiers(monkeypatch):
    from core.plugin_system import discovery_scan

    discovery_scan.reset_plugin_entry_scan_cache()
    calls = _spy(
        monkeypatch, discovery_scan, "_iter_plugin_entry_points_from_filesystem"
    )
    try:
        # The two startup passes: bootstrap tier, then deferred tier.
        bootstrap = discovery_scan.plugin_modules_for_tier("bootstrap")
        deferred = discovery_scan.plugin_modules_for_tier("deferred")
        assert bootstrap and deferred, "real source tree must yield both tiers"
        assert len(calls) == 1, "plugin entry scan must run once per process"

        discovery_scan.reset_plugin_entry_scan_cache()
        discovery_scan.plugin_modules_for_tier("bootstrap")
        assert len(calls) == 2, "reset_plugin_entry_scan_cache must re-arm the scan"
    finally:
        discovery_scan.reset_plugin_entry_scan_cache()


def test_tab_entry_scan_runs_once_for_all_call_sites(monkeypatch):
    from core.plugin_system import discovery_scan

    discovery_scan.reset_tab_entry_scan_cache()
    calls = _spy(monkeypatch, discovery_scan, "_iter_tab_entry_points_from_filesystem")
    try:
        # bootstrap + deferred tiers, then the session-picker tab grid.
        assert discovery_scan.tab_packages_for_tier("bootstrap")
        assert discovery_scan.tab_packages_for_tier("deferred")
        assert discovery_scan.iter_tab_entry_points()
        assert len(calls) == 1, "tab entry scan must run once per process"

        discovery_scan.reset_tab_entry_scan_cache()
        discovery_scan.iter_tab_entry_points()
        assert len(calls) == 2, "reset_tab_entry_scan_cache must re-arm the scan"
    finally:
        discovery_scan.reset_tab_entry_scan_cache()


def test_scan_cache_is_per_source_root(monkeypatch, tmp_path):
    """A synthetic src tree gets its own cached entries (never the real tree's)."""
    from core.plugin_system import discovery_scan

    discovery_scan.reset_plugin_entry_scan_cache()
    discovery_scan.reset_tab_entry_scan_cache()
    real_plugins = discovery_scan.iter_plugin_entry_points()

    synthetic = tmp_path / "src"
    plugin_dir = synthetic / "plugins" / "alpha"
    plugin_dir.mkdir(parents=True)
    plugin_py = plugin_dir / "plugin.py"
    plugin_py.write_text(
        "@plugin(name='alpha', startup_tier='bootstrap')\nclass Alpha:\n    pass\n",
        encoding="utf-8",
    )
    assert [
        e.plugin_name
        for e in discovery_scan.iter_plugin_entry_points(src_root=synthetic)
    ] == ["alpha"]
    # The synthetic scan must not have replaced the real tree's entries.
    assert discovery_scan.iter_plugin_entry_points() == real_plugins

    # Without invalidation the rewritten tree keeps serving the cached scan.
    plugin_py.write_text(
        "@plugin(name='beta', startup_tier='deferred')\nclass Beta:\n    pass\n",
        encoding="utf-8",
    )
    assert [
        e.plugin_name
        for e in discovery_scan.iter_plugin_entry_points(src_root=synthetic)
    ] == ["alpha"]
    discovery_scan.reset_plugin_entry_scan_cache()
    assert [
        e.plugin_name
        for e in discovery_scan.iter_plugin_entry_points(src_root=synthetic)
    ] == ["beta"]
    discovery_scan.reset_plugin_entry_scan_cache()
    discovery_scan.reset_tab_entry_scan_cache()


# --------------------------------------------------------------------------
# 3. Settings load is one read pass, with identical resulting values
# --------------------------------------------------------------------------


class _CountingSettings:
    """QSettings proxy counting the calls a load pass makes."""

    def __init__(self, inner: QSettings):
        self.inner = inner
        self.counts: Counter[str] = Counter()

    def allKeys(self):  # noqa: N802 - QSettings API
        self.counts["allKeys"] += 1
        return self.inner.allKeys()

    def contains(self, key):
        self.counts["contains"] += 1
        return self.inner.contains(key)

    def value(self, key, default=None):
        self.counts["value"] += 1
        if default is None:
            return self.inner.value(key)
        return self.inner.value(key, default)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def _redirect_qsettings(tmp_path: Path):
    """Point org/app QSettings at an isolated ini (never the real config)."""
    previous_format = QSettings.defaultFormat()
    previous_path = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.ConfigLocation
    )
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path)
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    return previous_format, previous_path


def _restore_qsettings(previous_format, previous_path) -> None:
    QSettings.setDefaultFormat(previous_format)
    QSettings.setPath(
        QSettings.Format.NativeFormat, QSettings.Scope.UserScope, previous_path
    )
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, previous_path
    )


def _store_snapshot(store) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    parts = {
        "settings": store.settings,
        "render": store.viewport.render_config,
        "view": store.viewport.view_state,
    }
    for scope, obj in parts.items():
        for field in dataclasses.fields(obj):
            snapshot[f"{scope}.{field.name}"] = repr(getattr(obj, field.name))
    return snapshot


def _typed_probe_value(type_name: str, key: str) -> str:
    if type_name == "bool":
        return "true"
    if type_name == "int":
        return "7"
    if type_name == "float":
        return "2.5"
    if key.endswith("_color") or key == "export_background_color":
        return "#FF112233"
    return f"probe-{key}"


def test_settings_load_is_one_read_pass(qapp, tmp_path):
    from core.store import Store
    from plugins.settings.manager import SettingsManager
    from tests.contracts._framework import MANAGER_PATH, read, settings_load_pairs

    pairs = settings_load_pairs(ast.parse(read(MANAGER_PATH)))
    assert pairs, "settings surface must not be empty"
    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        manager = SettingsManager("improve-imgsli", "improve-imgsli")
        settings = manager.settings
        for pair in pairs:
            settings.setValue(
                pair["key"], _typed_probe_value(pair["type"], pair["key"])
            )
        settings.sync()

        counted = _CountingSettings(settings)
        manager.settings = counted
        proxied_store = Store()
        manager.load_all_settings(proxied_store)

        keys_in_file = len(pairs)
        reads = counted.counts
        assert reads["allKeys"] == 1, f"expected one allKeys() pass, got {reads}"
        assert reads["contains"] == 0, (
            "membership must come from the allKeys() snapshot, not a second "
            f"per-key read: {reads}"
        )
        assert reads["value"] <= keys_in_file, (
            f"at most one value() per present key expected, got {reads}"
        )
        assert reads["value"] + reads["allKeys"] <= keys_in_file + 1, reads

        # Identical observable result: a plain manager over the same store.
        manager.settings = settings
        plain_store = Store()
        manager.load_all_settings(plain_store)
        assert _store_snapshot(proxied_store) == _store_snapshot(plain_store)
    finally:
        _restore_qsettings(previous_format, previous_path)


def test_settings_load_missing_keys_fall_back_to_defaults(qapp, tmp_path):
    """An empty store still yields defaults — the snapshot is not a value cache
    that invents entries for absent keys."""
    from core.store import Store
    from plugins.settings.manager import SettingsManager

    previous_format, previous_path = _redirect_qsettings(tmp_path)
    try:
        manager = SettingsManager("improve-imgsli", "improve-imgsli")
        counted = _CountingSettings(manager.settings)
        manager.settings = counted
        empty_store = Store()
        manager.load_all_settings(empty_store)

        default_store = Store()
        assert _store_snapshot(empty_store) == _store_snapshot(default_store)
        assert counted.counts["value"] == 0, counted.counts
        assert counted.counts["contains"] == 0, counted.counts
        assert counted.counts["allKeys"] == 1, counted.counts
    finally:
        _restore_qsettings(previous_format, previous_path)


# --------------------------------------------------------------------------
# 4. Help-tree scan is not re-run for an unchanged fragment set
# --------------------------------------------------------------------------


def test_help_tree_scan_is_skipped_for_unchanged_contributions(monkeypatch):
    """The help-tree filesystem scan is not re-run per page build.

    Driven through the host facade (``TabRegistry.contribute_all_help``) —
    the same call ``install_pages`` and every page build make.
    """
    from plugins.help import scan as help_scan
    from plugins.help.tree import clear_help_contributions
    from tabs.registry import TabRegistry

    calls = _spy(monkeypatch, help_scan, "scan_help_tree")
    registry = TabRegistry()
    registry.discover()
    try:
        # A cold tree (what a fresh process has) installs once...
        clear_help_contributions()
        registry.contribute_all_help()
        assert len(calls) == 1

        # ...and the repeated page-build calls with unchanged fragments do not
        # re-run the scan.
        registry.contribute_all_help()
        registry.contribute_all_help()
        assert len(calls) == 1, "unchanged fragments must not re-run the help scan"

        # Dropping the tree cache (help dialog rebuild) re-arms the install.
        clear_help_contributions()
        registry.contribute_all_help()
        assert len(calls) == 2
    finally:
        clear_help_contributions()
