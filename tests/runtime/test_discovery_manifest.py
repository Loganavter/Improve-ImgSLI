"""The build-time discovery manifest: freshness, zero-import discovery, fail-open.

`core.plugin_system.discovery_scan` prefers ``discovery_manifest.json`` (written
by ``src/devtools/gen_discovery_manifest.py``) so a frozen bundle discovers tab
and plugin entry points without importing a single module. These tests pin the
three things that make that safe: the committed manifest matches the tree, the
manifest path imports nothing, and anything wrong with the file fails open to
the import scan with one warning instead of crashing startup.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import importlib.util
import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from core.plugin_system import discovery_scan
from devtools import gen_discovery_manifest as generator

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "src"
_COMMITTED = _SRC / "core" / "plugin_system" / "discovery_manifest.json"
_SPEC = _REPO_ROOT / "build" / "Windows-template" / "BlinkTable.spec"
_BUILD_WINDOWS = _REPO_ROOT / "build" / "Windows-template" / "build_windows.py"

_DISCOVERY_PREFIXES = ("tabs.", "plugins.")


@contextmanager
def _count_module_imports(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Record every tab/plugin module import performed inside the block.

    Wraps both entry points used by the scan: ``pkgutil`` discovery ends in
    ``importlib.import_module``, while ``import plugins`` goes through
    ``builtins.__import__``; counting only one would miss half the cost.
    """
    imported: list[str] = []
    real_import = builtins.__import__
    real_import_module = importlib.import_module

    def _track(name: str) -> None:
        if name.startswith(_DISCOVERY_PREFIXES):
            imported.append(name)

    def _import(name, *args, **kwargs):
        _track(name)
        return real_import(name, *args, **kwargs)

    def _import_module(name, package=None):
        _track(name)
        return real_import_module(name, package=package)

    monkeypatch.setattr(builtins, "__import__", _import)
    monkeypatch.setattr(importlib, "import_module", _import_module)
    yield imported


def _fake_source_tree(tmp_path: Path) -> Path:
    """A minimal source tree holding one extra tab and one extra plugin."""
    src = tmp_path / "src"
    tab_dir = src / "tabs" / "extra_tab"
    tab_dir.mkdir(parents=True)
    (tab_dir / "tab.py").write_text(
        "from tabs.contract import TabContract\n\n\n"
        "class ExtraTab(TabContract):\n"
        "    startup_tier = 'deferred'\n",
        encoding="utf-8",
    )
    plugin_dir = src / "plugins" / "extra"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text(
        "from core.plugin_system import Plugin, plugin\n\n\n"
        "@plugin(name='extra', version='1.0', startup_tier='deferred')\n"
        "class ExtraPlugin(Plugin):\n"
        "    pass\n",
        encoding="utf-8",
    )
    return src


# -- freshness ---------------------------------------------------------------


def test_committed_manifest_is_generated_from_the_tree() -> None:
    assert _COMMITTED.read_text(encoding="utf-8") == generator.render_manifest()


def test_generator_check_mode_is_green_on_the_committed_manifest() -> None:
    assert generator.main(["--check"]) == 0


def test_manifest_entries_are_sorted_unique_and_complete() -> None:
    payload = json.loads(_COMMITTED.read_text(encoding="utf-8"))
    assert payload["version"] == discovery_scan.MANIFEST_VERSION
    assert payload["generated_by"] == "src/devtools/gen_discovery_manifest.py"

    keys = [(entry["kind"], entry["id"]) for entry in payload["entries"]]
    assert keys == sorted(keys)
    assert len(set(keys)) == len(keys)

    tabs = {entry["id"] for entry in payload["entries"] if entry["kind"] == "tab"}
    plugins = {entry["id"] for entry in payload["entries"] if entry["kind"] == "plugin"}
    assert tabs == {
        entry.package_name for entry in discovery_scan.iter_tab_entry_points(src_root=_SRC)
    }
    assert plugins == {
        entry.plugin_name for entry in discovery_scan.iter_plugin_entry_points(src_root=_SRC)
    }


def test_manifest_discovery_agrees_with_the_filesystem_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale-but-valid manifest must not silently change tiers or order.

    The freshness test above catches drift; this one proves the two discovery
    paths describe the same entry points, so a green ``--check`` is meaningful.
    """
    from_manifest_tabs = discovery_scan.iter_tab_entry_points()
    from_manifest_plugins = discovery_scan.iter_plugin_entry_points()

    monkeypatch.setattr(discovery_scan, "_MANIFEST_PATH", _SRC / "no-such-manifest.json")
    from_tree_tabs = discovery_scan.iter_tab_entry_points()
    from_tree_plugins = discovery_scan.iter_plugin_entry_points()

    def _tab_key(entry: discovery_scan.TabEntryPoint) -> tuple[str, str, str]:
        return (entry.package_name, entry.module_name, entry.startup_tier)

    def _plugin_key(entry: discovery_scan.PluginEntryPoint) -> tuple[str, str, str, int]:
        return (
            entry.plugin_name,
            entry.module_name,
            entry.startup_tier,
            entry.startup_order,
        )

    assert {_tab_key(e) for e in from_manifest_tabs} == {_tab_key(e) for e in from_tree_tabs}
    assert {_plugin_key(e) for e in from_manifest_plugins} == {
        _plugin_key(e) for e in from_tree_plugins
    }


def test_check_goes_red_after_a_registry_addition(tmp_path: Path) -> None:
    """A new tab/plugin without regeneration is exactly what ``--check`` catches."""
    drifted = generator.render_manifest(src_root=_fake_source_tree(tmp_path))
    assert drifted != _COMMITTED.read_text(encoding="utf-8")

    stale_copy = tmp_path / "discovery_manifest.json"
    stale_copy.write_text(drifted, encoding="utf-8")
    assert generator.main(["--check", "--output", str(stale_copy)]) == 1


# -- zero-import discovery ---------------------------------------------------


def test_discovery_with_manifest_imports_no_tab_or_plugin_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _count_module_imports(monkeypatch) as imported:
        tabs = discovery_scan.iter_tab_entry_points()
        plugins = discovery_scan.iter_plugin_entry_points()
        bootstrap_tabs = discovery_scan.tab_packages_for_tier("bootstrap")
        deferred_plugins = discovery_scan.plugin_modules_for_tier("deferred")

    assert imported == []
    assert tabs and plugins and bootstrap_tabs and deferred_plugins


def test_discovery_without_a_manifest_imports_modules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An explicit ``src_root`` is a frozen-like tree: no sources, no manifest.

    The committed manifest is deliberately consulted only for the real tree, so
    this pins the fallback that a datas-only bundle actually executes.
    """
    empty_src = tmp_path / "src"
    (empty_src / "tabs").mkdir(parents=True)
    (empty_src / "plugins").mkdir(parents=True)

    with _count_module_imports(monkeypatch) as imported:
        tabs = discovery_scan.iter_tab_entry_points(src_root=empty_src)
        plugins = discovery_scan.iter_plugin_entry_points(src_root=empty_src)

    assert len(imported) > 0
    # ``src_root`` only bounds the filesystem scan; the import fallback then
    # enumerates the real ``tabs`` / ``plugins`` packages, which is exactly the
    # work the manifest removes.
    assert tabs and plugins


# -- fail-open ---------------------------------------------------------------


def test_missing_manifest_is_not_an_error(tmp_path: Path) -> None:
    assert discovery_scan.load_discovery_manifest(tmp_path / "absent.json") is None


@pytest.mark.parametrize(
    "payload",
    [
        "{ not json",
        "[]",
        json.dumps({"version": 2, "entries": []}),
        json.dumps({"version": 1, "entries": []}),
        json.dumps({"version": 1, "entries": [{"kind": "tab", "id": "x", "module": "tabs.x.tab"}]}),
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "kind": "tab",
                        "id": "x",
                        "module": "tabs.x.tab",
                        "attr": "X",
                        "startup_tier": "sometimes",
                    }
                ],
            }
        ),
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "kind": "plugin",
                        "id": "x",
                        "module": "elsewhere.x",
                        "attr": "X",
                        "startup_tier": "bootstrap",
                    }
                ],
            }
        ),
    ],
)
def test_corrupt_manifest_warns_once_and_is_ignored(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, payload: str
) -> None:
    corrupt = tmp_path / "discovery_manifest.json"
    corrupt.write_text(payload, encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger=discovery_scan.logger.name):
        assert discovery_scan.load_discovery_manifest(corrupt) is None

    warnings = [rec for rec in caplog.records if rec.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "discovery_manifest.json" in warnings[0].getMessage()


def test_corrupt_manifest_still_discovers_everything(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The real worst case: bad manifest AND a bundle with no sources on disk."""
    corrupt = tmp_path / "discovery_manifest.json"
    corrupt.write_text('{"version": 1, "entries": [', encoding="utf-8")
    monkeypatch.setattr(discovery_scan, "_MANIFEST_PATH", corrupt)
    monkeypatch.setattr(
        discovery_scan, "_iter_tab_entry_points_from_filesystem", lambda _root: ()
    )
    monkeypatch.setattr(
        discovery_scan, "_iter_plugin_entry_points_from_filesystem", lambda _root: ()
    )
    # The caches are process-global: any earlier test that ran discovery warms
    # them, and a warm cache would return entries without ever reaching the
    # import fallback, making ``imported`` empty for a reason that has nothing
    # to do with the corrupt manifest.
    discovery_scan.reset_tab_entry_scan_cache()
    discovery_scan.reset_plugin_entry_scan_cache()

    with caplog.at_level(logging.WARNING, logger=discovery_scan.logger.name):
        with _count_module_imports(monkeypatch) as imported:
            tabs = discovery_scan.iter_tab_entry_points()
            plugins = discovery_scan.iter_plugin_entry_points()

    assert imported
    assert tabs and plugins
    # The import fallback logs one ERROR per non-tab package under ``tabs/``
    # (e.g. ``tabs.use_cases.tab`` is not a module) — pre-existing noise in the
    # frozen path, not a manifest defect; the point here is that nothing raised
    # and every entry point was found.


# -- a frozen start consumes it and says so ----------------------------------


def test_a_frozen_like_start_consumes_the_manifest_and_names_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Ship-then-consume: no module imported to discover, and one evidence line.

    A datas-only bundle has no ``.py`` sources and a manifest next to
    ``discovery_scan``. The file is copied out here so the path is fresh (the
    evidence line is once per manifest path per process). Two things must hold
    together: discovery imports nothing, and the start names the data it used —
    a silent success cannot be told apart from a start that paid for the scan.
    """
    shipped = tmp_path / "discovery_manifest.json"
    shipped.write_text(_COMMITTED.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(discovery_scan, "_MANIFEST_PATH", shipped)
    # Process-global caches: a warm one would return entries before the
    # manifest is ever read, hiding both assertions below.
    discovery_scan.reset_plugin_entry_scan_cache()
    discovery_scan.reset_tab_entry_scan_cache()

    with caplog.at_level(logging.INFO, logger=discovery_scan.logger.name):
        with _count_module_imports(monkeypatch) as imported:
            bootstrap_plugins = discovery_scan.plugin_modules_for_tier("bootstrap")
            bootstrap_tabs = discovery_scan.tab_packages_for_tier("bootstrap")
            discovery_scan.plugin_modules_for_tier("deferred")
            discovery_scan.tab_packages_for_tier("deferred")

    assert imported == []
    assert bootstrap_plugins and bootstrap_tabs
    used = [
        record
        for record in caplog.records
        if record.levelno == logging.INFO and "Discovery manifest:" in record.getMessage()
    ]
    assert len(used) == 1, "one evidence line per manifest, not one per discovery call"
    assert str(shipped) in used[0].getMessage()
    assert "entry points" in used[0].getMessage()


# -- Windows packaging (no PyInstaller run) ----------------------------------


def _load_build_windows():
    """Import ``build_windows.py`` (its only import-time work is path config)."""
    spec = importlib.util.spec_from_file_location("build_windows_under_test", _BUILD_WINDOWS)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app_datas_from_spec() -> list[tuple[str, str]]:
    """The literal ``APP_DATAS`` entries of the spec, without running PyInstaller."""
    tree = ast.parse(_SPEC.read_text(encoding="utf-8"), filename=str(_SPEC))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.List):
            continue
        names = [target.id for target in node.targets if isinstance(target, ast.Name)]
        if "APP_DATAS" not in names:
            continue
        entries: list[tuple[str, str]] = []
        for element in node.value.elts:
            if not isinstance(element, ast.Tuple) or len(element.elts) != 2:
                continue
            source, destination = element.elts
            if isinstance(destination, ast.Constant) and isinstance(destination.value, str):
                entries.append((ast.unparse(source), destination.value))
        return entries
    raise AssertionError(f"{_SPEC}: no APP_DATAS list literal")


def test_windows_spec_ships_the_discovery_manifest_next_to_the_module() -> None:
    """A bundle without this file pays the import scan the manifest exists for."""
    destinations = [
        destination
        for source, destination in _app_datas_from_spec()
        if "discovery_manifest.json" in source
    ]
    assert destinations == ["core/plugin_system"], (
        "discovery_scan resolves the manifest with Path(__file__).with_name(...), "
        "so the bundle destination must be the module's own package directory"
    )


def test_windows_build_generates_the_manifest_before_pyinstaller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The data entry is only correct if the file is written first.

    Falsifiable: drop the ``generate_discovery_manifest()`` step from ``main``
    and ``"manifest"`` disappears from the recorded order.
    """
    build = _load_build_windows()
    order: list[str] = []

    def _step(name: str):
        def _record(*_args, **_kwargs):
            order.append(name)
            return 0

        return _record

    monkeypatch.setattr(build.os, "chdir", lambda _path: None)
    monkeypatch.setattr(build, "ensure_supported_python", _step("python"))
    monkeypatch.setattr(build, "ensure_python_dependencies", _step("deps"))
    monkeypatch.setattr(build, "generate_discovery_manifest", _step("manifest"))
    monkeypatch.setattr(build, "build_pyinstaller", _step("pyinstaller"))
    monkeypatch.setattr(build, "run_command", _step("script"))
    monkeypatch.setattr(build, "fetch_ffmpeg", _step("ffmpeg"))
    monkeypatch.setattr(build, "build_inno_setup", _step("inno"))

    assert build.main() == 0
    assert order.index("manifest") < order.index("pyinstaller")


def test_windows_build_runs_the_manifest_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _load_build_windows()
    calls: list[list[str]] = []
    monkeypatch.setattr(
        build, "run_command", lambda args, **_kwargs: calls.append(list(args)) or 0
    )

    assert build.generate_discovery_manifest() == 0
    assert build.DISCOVERY_MANIFEST_SCRIPT.is_file()
    assert calls == [[sys.executable, str(build.DISCOVERY_MANIFEST_SCRIPT)]]


def test_windows_build_fails_when_the_manifest_cannot_be_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = _load_build_windows()
    monkeypatch.setattr(build, "run_command", lambda *_args, **_kwargs: 1)
    assert build.generate_discovery_manifest() == 1

