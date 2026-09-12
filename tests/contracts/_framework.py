"""Shared primitives for architecture contract tests.

These tests verify *structural* dogmas from docs/dev/{CANVAS_FEATURES,
CONTRACTS,ARCHITECTURE}.md — they scan source files rather than execute
runtime code. For behavioral contract tests, see ``tests/test_*_contracts.py``.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "src"
CANVAS_FEATURES = SRC / "tabs" / "image_compare" / "canvas" / "features"
MULTI_COMPARE_CANVAS_FEATURES = SRC / "tabs" / "multi_compare" / "canvas" / "features"
CANVAS_INFRA = SRC / "ui" / "canvas_infra"
CANVAS_PRESENTATION = SRC / "ui" / "canvas_presentation"
SHADER_SOURCES = SRC / "ui" / "widgets" / "canvas" / "shader_sources"
PLUGINS = SRC / "plugins"

def iter_py(root: Path) -> list[Path]:
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and "tests" not in p.parts
    ]

def rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return Path(str(p)).as_posix()

def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""

def module_imports(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return []
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
    return out

def _list_features_under(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name != "__pycache__"
    )

def list_canvas_features() -> list[Path]:
    return _list_features_under(CANVAS_FEATURES)

def list_multi_compare_canvas_features() -> list[Path]:
    return _list_features_under(MULTI_COMPARE_CANVAS_FEATURES)

def list_all_canvas_features() -> list[Path]:
    """Every tab's canvas feature package — not just ``image_compare``'s.

    ``multi_compare`` participates in the same feature-package discovery
    contract (manifest/passes auto-registration) as ``image_compare`` — see
    docs/dev/QRHI_CANVAS_FEATURES.md's Current Feature Status table — so
    structural dogma checks (stack_role, no hardcoded layer/priority, etc.)
    should apply to both, not just the tab that happened to be decomposed
    first.
    """
    return list_canvas_features() + list_multi_compare_canvas_features()

def list_plugins() -> list[Path]:
    if not PLUGINS.is_dir():
        return []
    return sorted(
        d
        for d in PLUGINS.iterdir()
        if d.is_dir()
        and not d.name.startswith("_")
        and d.name != "__pycache__"
    )

def feature_name(feature_dir: Path) -> str | None:
    for fname in ("widget.py", "feature.py", "manifest.py"):
        f = feature_dir / fname
        if not f.exists():
            continue
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', read(f))
        if m:
            return m.group(1)
    return None

# ---------------------------------------------------------------------------
# Settings persistence contract — shared scanners (see CONTRACTS.md
# "Settings persistence contract"). Contract tests AND the runtime full-pass
# sweep must read the settings surface through these helpers so they cannot
# drift apart.
# ---------------------------------------------------------------------------

SETTINGS_TYPE_NAMES = {"str", "int", "float", "bool"}

MANAGER_PATH = SRC / "plugins" / "settings" / "manager.py"
SERVICE_PATH = SRC / "plugins" / "settings" / "application_service.py"
MUTATIONS_PATH = SRC / "plugins" / "settings" / "mutations.py"
STORE_SETTINGS_PATH = SRC / "core" / "store_settings.py"

#: SettingsState fields that legitimately never reach SettingsManager:
#: runtime-transient values only. Adding a field here requires a comment.
TRANSIENT_STORE_SETTINGS = {
    "export_resolution_scale",  # per-export scale, recomputed each export
}

#: SettingsState fields persisted out-of-band (JSON blobs, not scalar keys).
JSON_PERSISTED_STORE_SETTINGS = {
    "keyboard_overrides",  # saved via _save_keyboard_overrides (JSON)
}


SETTINGS_TYPE_NAMES = {"str", "int", "float", "bool"}

MANAGER_PATH = SRC / "plugins" / "settings" / "manager.py"
SERVICE_PATH = SRC / "plugins" / "settings" / "application_service.py"
MUTATIONS_PATH = SRC / "plugins" / "settings" / "mutations.py"
STORE_SETTINGS_PATH = SRC / "core" / "store_settings.py"

#: SettingsState fields that legitimately never reach SettingsManager —
#: runtime-transient values only. Mirrors the manifest documented in
#: docs/dev/CONTRACTS.md §Settings persistence contract. Adding a field here
#: requires a reason; the contract fails for any OTHER uncovered field.
TRANSIENT_STORE_SETTINGS: dict[str, str] = {
    "export_resolution_scale": (
        "per-export resolution scale, recomputed from the export dialog for "
        "each export — a session value, not a user preference"
    ),
}

#: SettingsState fields persisted OUT of the scalar key/value pass — stored
#: as structured blobs by dedicated SettingsManager helpers
#: (``_load_<name>`` / ``_save_<name>``), not via ``_get_setting``/
#: ``_save_setting``. Mirrors docs/dev/CONTRACTS.md §Settings persistence
#: contract.
JSON_PERSISTED_STORE_SETTINGS: dict[str, str] = {
    "keyboard_overrides": (
        "action_id -> shortcut-chord map, saved as JSON via "
        "_load_keyboard_overrides / _save_keyboard_overrides"
    ),
}


def _method_node(tree: ast.Module, class_name: str, method_name: str):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ClassDef)
            and node.name == class_name
            and any(
                isinstance(n, ast.FunctionDef) and n.name == method_name
                for n in node.body
            )
        ):
            return next(
                n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == method_name
            )
    return None


def settings_load_pairs(tree: ast.Module) -> list[dict]:
    """(field, scope, key, type_name) for every typed load in load_all_settings.

    Resolves both direct assignments (``s.x = self._get_setting(...)``),
    wrapped loads (``s.x = hex_to_color(self._get_setting(...))``) and
    name-indirection (``name = self._get_setting(...); render.x = name``).
    """
    fn = _method_node(tree, "SettingsManager", "load_all_settings")
    if fn is None:
        return []
    # name -> (key, type_name) for simple alias assignments.
    aliases: dict[str, tuple[str | None, str | None]] = {}
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and _is_get_setting_call(node.value)
        ):
            key = _literal_str(node.value.args[0])
            third = node.value.args[2]
            type_name = third.id if isinstance(third, ast.Name) else None
            aliases[node.targets[0].id] = (key, type_name)

    pairs: list[dict] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Attribute):
            continue
        scope = target.value.id if isinstance(target.value, ast.Name) else None
        if scope not in ("s", "render", "view"):
            continue
        key = _load_key_from_subtree(node.value, aliases)
        if key is None:
            continue
        type_name = _load_type_from_subtree(node.value, aliases)
        pairs.append(
            {"field": target.attr, "scope": scope, "key": key, "type": type_name}
        )
    return pairs


def _is_get_setting_call(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and call.func.attr == "_get_setting"
        and len(call.args) == 3
    )


def _literal_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _load_key_from_subtree(node: ast.expr, aliases: dict) -> str | None:
    if isinstance(node, ast.Name):
        key, _type = aliases.get(node.id, (None, None))
        return key
    if isinstance(node, ast.Call):
        if _is_get_setting_call(node):
            return _literal_str(node.args[0])
        for arg in node.args:
            key = _load_key_from_subtree(arg, aliases)
            if key is not None:
                return key
        for kw in node.keywords:
            key = _load_key_from_subtree(kw.value, aliases)
            if key is not None:
                return key
    return None


def _load_type_from_subtree(node: ast.expr, aliases: dict) -> str | None:
    if isinstance(node, ast.Name):
        _key, type_name = aliases.get(node.id, (None, None))
        return type_name
    if isinstance(node, ast.Call):
        if _is_get_setting_call(node):
            third = node.args[2]
            return third.id if isinstance(third, ast.Name) else None
        for arg in node.args:
            t = _load_type_from_subtree(arg, aliases)
            if t is not None:
                return t
    return None


def settings_save_keys(tree: ast.Module) -> set[str]:
    """Literal keys written by save_all_settings."""
    fn = _method_node(tree, "SettingsManager", "save_all_settings")
    if fn is None:
        return set()
    keys: set[str] = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_save_setting"
        ):
            key = _literal_str(node.value.args[0])
            if key is not None:
                keys.add(key)
    return keys


def settings_incremental_save_keys(tree: ast.Module) -> set[str]:
    """Literal keys saved outside the master pass (incremental apply paths)."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "_save_setting"
        ):
            key = _literal_str(node.value.args[0])
            if key is not None:
                keys.add(key)
    return keys


def store_settings_field_names(tree: ast.Module) -> list[str]:
    """Field names of the SettingsState dataclass, in declaration order."""
    cls = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "SettingsState"
        ),
        None,
    )
    if cls is None:
        return []
    fields = []
    for node in cls.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            fields.append(node.target.id)
    return fields
