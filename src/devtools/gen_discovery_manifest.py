#!/usr/bin/env python3
"""Write or verify the build-time discovery manifest.

A frozen PyInstaller bundle ships no ``.py`` files on disk, so
``core.plugin_system.discovery_scan`` cannot find tab/plugin entry points by
scanning the filesystem and falls back to importing every tab and plugin module
just to discover it. This generator records those entry points as data
(``src/core/plugin_system/discovery_manifest.json``), which the loader consumes
instead — no module is imported to discover anything.

Usage (from the repo root; the frozen build must run the write form before
PyInstaller collects data):

    PYTHONPATH=src python3 src/devtools/gen_discovery_manifest.py
    PYTHONPATH=src python3 src/devtools/gen_discovery_manifest.py --check

``--check`` regenerates in memory and compares with the committed file, exiting
1 on drift: adding, removing or renaming a tab / ``@plugin`` entry point makes
the committed manifest stale until this script is re-run. Exit codes: 0 = ok,
1 = stale, 2 = the tree does not look like a source checkout.

The manifest is authoritative only where it exists; when it is missing,
unreadable or malformed the loader fails open to the import scan (see
docs/dev/PLUGINS.md).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.plugin_system.discovery_scan import (  # noqa: E402  (after the sys.path fix)
    MANIFEST_GENERATED_BY,
    MANIFEST_VERSION,
    iter_plugin_entry_points,
    iter_tab_entry_points,
)

MANIFEST_PATH = _SRC / "core" / "plugin_system" / "discovery_manifest.json"


def build_entries(src_root: Path | None = None) -> list[dict[str, Any]]:
    """Manifest entries for the tree, sorted by ``(kind, id)`` and stable."""
    root = src_root or _SRC
    entries: list[dict[str, Any]] = []
    for tab in iter_tab_entry_points(src_root=root):
        entries.append(
            {
                "kind": "tab",
                "id": tab.package_name,
                "module": tab.module_name,
                "attr": _tab_class_name(tab.tab_py),
                "startup_tier": tab.startup_tier,
                "startup_order": 0,
            }
        )
    for plugin in iter_plugin_entry_points(src_root=root):
        entries.append(
            {
                "kind": "plugin",
                "id": plugin.plugin_name,
                "module": plugin.module_name,
                "attr": _plugin_class_name(plugin.plugin_py),
                "startup_tier": plugin.startup_tier,
                "startup_order": plugin.startup_order,
            }
        )
    if not entries:
        raise ValueError(f"{root}: no tab/plugin entry points found (not a source tree?)")
    entries.sort(key=lambda entry: (entry["kind"], entry["id"]))
    return entries


def render_manifest(src_root: Path | None = None) -> str:
    """The exact bytes ``--check`` compares against and the write form emits."""
    payload = {
        "version": MANIFEST_VERSION,
        "generated_by": MANIFEST_GENERATED_BY,
        "entries": build_entries(src_root),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _tab_class_name(tab_py: Path) -> str:
    for node in _parse(tab_py).body:
        if isinstance(node, ast.ClassDef) and any(
            _name_of(base) == "TabContract" for base in node.bases
        ):
            return node.name
    raise ValueError(f"{tab_py}: no TabContract subclass found")


def _plugin_class_name(plugin_py: Path) -> str:
    for node in _parse(plugin_py).body:
        if not isinstance(node, ast.ClassDef):
            continue
        for deco in node.decorator_list:
            if isinstance(deco, ast.Call) and _name_of(deco.func) == "plugin":
                return node.name
    raise ValueError(f"{plugin_py}: no @plugin(...) class found")


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ValueError(f"{path}: cannot be parsed ({exc})") from exc


def _name_of(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or verify discovery_manifest.json.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="regenerate in memory and compare with the committed manifest (exit 1 on drift)",
    )
    parser.add_argument("--output", type=Path, default=MANIFEST_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        rendered = render_manifest()
    except ValueError as exc:
        print(f"gen_discovery_manifest: {exc}", file=sys.stderr)
        return 2

    if not args.check:
        args.output.write_text(rendered, encoding="utf-8")
        print(f"gen_discovery_manifest: wrote {args.output}")
        return 0

    try:
        committed = args.output.read_text(encoding="utf-8")
    except OSError:
        committed = ""
    if committed != rendered:
        print(
            f"gen_discovery_manifest: {args.output} is stale; re-run "
            "`PYTHONPATH=src python3 src/devtools/gen_discovery_manifest.py`",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
