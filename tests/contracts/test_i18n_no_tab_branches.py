"""Translation resource ownership: shared vs tab branches.

Dogma: ``src/resources/i18n/`` is the *host-level* translation tree
(core / plugins / ui / shared) and the home of **cross-cutting** keys —
errors and common buttons used by more than one owner (see
``docs/dev/RESOURCES_I18N.md``, "Picking where a key lives"). A translation
referenced by **exactly one** tab (``src/tabs/<name>/``) is a tab branch
growing in the wrong place — it must live in that tab's own i18n root
(``src/tabs/<name>/resources/i18n/<lang>/``, registered via
``add_i18n_root``), namespaced by the tab, where it is guaranteed to be
loaded with the tab.

This test scans, universally (no tab name hardcoded):

  * every dotted key present in the shared tree;
  * every *production* reference to a key: string literals (``tr("key")``,
    ``label_key="key"``, settings ``group("key")``, ...) and key-shaped
    templates (``f"settings.{name}"``, ``"workspace.session_types.{x}"``
    used with ``.format``) — template shape = only ``[a-z0-9_.]`` literal
    parts plus at least one placeholder, so logging/format strings are not
    mistaken for translation keys;
  * which zone each reference comes from: ``shared`` (anything outside
    ``src/tabs/``) or ``tab:<name>``.

Violations:

  * **tab branches** — a shared key referenced by exactly one tab, never by
    shared code nor by any other tab: move it to that tab's i18n root,
    namespaced as ``<tab>.<key>`` (keys used by two or more tabs are
    cross-cutting and legitimately stay in the shared tree);
  * **orphans** — a shared key referenced by nothing at all: dead
    translation, remove it from the shared tree.

Test files are intentionally excluded: the contract is about what
production code consumes at runtime.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from ._framework import ROOT, SRC, iter_py, read, rel

I18N_ROOT = SRC / "resources" / "i18n"
TABS_ROOT = SRC / "tabs"

# Placeholder sentinel used while compiling key templates.
_PLACEHOLDER = "{PLACEHOLDER}"


def _production_py(root: Path) -> list[Path]:
    return [
        p
        for p in iter_py(root)
        if not p.name.startswith("test_") and "tests" not in p.parts
    ]


def _load_json_keys(json_files: list[Path]) -> dict[str, set[Path]]:
    """Full dotted keys of every JSON translation file -> source files."""
    keys: dict[str, set[Path]] = {}

    def walk(node: dict, prefix: str, path: Path) -> None:
        for name, value in node.items():
            key = f"{prefix}.{name}" if prefix else name
            if isinstance(value, dict):
                walk(value, key, path)
            else:
                keys.setdefault(key, set()).add(path)

    for jf in json_files:
        try:
            data = json.loads(read(jf))
        except Exception:
            continue
        if isinstance(data, dict):
            walk(data, "", jf)
    return keys


def _template_strings(node: ast.AST):
    """Key-shaped templates from a node (f-string or ``"...{x}..."`` plain
    ``.format`` string): regexes anchored ``^...$``, or nothing.

    Only templates whose literal parts consist solely of ``[a-z0-9_.]``
    (with at least one wordy literal part and at least one placeholder) are
    treated as key builders — logging/format messages with spaces and
    punctuation are ignored.
    """
    candidates: list[list[str]] = []
    if isinstance(node, ast.JoinedStr):
        candidates.append([])
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                candidates[-1].append(_PLACEHOLDER)
            elif isinstance(value, ast.Constant) and isinstance(value.value, str):
                candidates[-1].append(value.value)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
        if "{" not in text:
            return
        parts: list[str] = []
        i = 0
        while i < len(text):
            open_at = text.find("{", i)
            if open_at < 0:
                parts.append(text[i:])
                break
            if open_at > i:
                parts.append(text[i:open_at])
            close_at = text.find("}", open_at)
            if close_at < 0:
                return
            parts.append(_PLACEHOLDER)
            i = close_at + 1
        candidates.append(parts)
    for parts in candidates:
        literals = "".join(p for p in parts if p != _PLACEHOLDER)
        if not literals or "{" in literals or "}" in literals:
            continue
        if not re.fullmatch(r"[a-z0-9_.]+", literals):
            continue  # logging / format message, not a key template
        if _PLACEHOLDER not in parts:
            continue  # static string — covered by the literal scan
        if not re.search(r"[a-z0-9_]{2,}", literals):
            continue  # pure placeholder composition, e.g. f"{a}.{b}"
        yield "^" + "".join(
            re.escape(p) if p != _PLACEHOLDER else r"[a-z0-9_.]+" for p in parts
        ) + "$"


def _scan_consumers() -> tuple[dict[str, set[Path]], dict[str, set[Path]]]:
    """(literal key -> files, template regex -> files) over production code."""
    literals: dict[str, set[Path]] = {}
    templates: dict[str, set[Path]] = {}
    for py in _production_py(SRC):
        tree = ast.parse(read(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.setdefault(node.value, set()).add(py)
            for template in _template_strings(node):
                templates.setdefault(template, set()).add(py)
    return literals, templates


def _zone_of(path: Path) -> str:
    try:
        parts = path.relative_to(TABS_ROOT).parts
    except ValueError:
        return "shared"
    return f"tab:{parts[0]}"


def _analyze():
    """Shared keys -> (violating tabs, consumer files, dead flag)."""
    json_files = [
        jf
        for lang_dir in I18N_ROOT.iterdir()
        if lang_dir.is_dir()
        for jf in lang_dir.rglob("*.json")
    ]
    shared_keys = _load_json_keys(json_files)
    literals, templates = _scan_consumers()

    def used_by_shared(key: str) -> bool:
        if any(_zone_of(p) == "shared" for p in literals.get(key, ())):
            return True
        for template, files in templates.items():
            if any(_zone_of(p) == "shared" for p in files) and re.match(
                template, key
            ):
                return True
        return False

    tab_branches: dict[str, tuple[list[str], list[Path]]] = {}
    orphans: list[str] = []
    for key in sorted(shared_keys):
        if used_by_shared(key):
            continue
        consumers = literals.get(key, set())
        tabs = sorted({_zone_of(p) for p in consumers if _zone_of(p) != "shared"})
        if len(tabs) == 1:
            tab_branches[key] = (tabs, sorted(consumers))
        elif not consumers:
            orphans.append(key)
    return shared_keys, tab_branches, orphans


def test_shared_i18n_has_no_tab_branches():
    _, tab_branches, _ = _analyze()
    lines = []
    for key, (tabs, files) in tab_branches.items():
        lines.append(f"  {key}  <- used only by {', '.join(tabs)}")
        for f in files[:4]:
            lines.append(f"      {rel(f)}")
        lines.append(
            f"      -> move to src/tabs/<tab>/resources/i18n/<lang>/ as "
            f"'<tab>.{key}' (registered via add_i18n_root), not the shared "
            f"tree; keys used by >=2 tabs are cross-cutting and stay shared"
        )
    assert not tab_branches, (
        "Shared translation tree contains tab branches (translations "
        "referenced exclusively by one tab must live in that tab's own "
        f"i18n root):\n{chr(10).join(lines)}"
    )


def test_shared_i18n_has_no_orphan_keys():
    _, _, orphans = _analyze()
    lines = [f"  {key}" for key in orphans]
    assert not orphans, (
        "Shared translation tree contains orphan keys (referenced by no "
        "production code — dead translations should be removed):\n"
        f"{chr(10).join(lines)}"
    )
