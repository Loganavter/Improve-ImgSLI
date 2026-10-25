from __future__ import annotations

# Audit-Meta: pattern=single-owner reason="one discovery vocabulary: the manifest contract/load/fail-open, the filesystem AST scan and the import fallback share Entry/StartupTier and one resolvability rule, so a fix in one path can never silently miss the other (per-process scan state already lives in discovery_cache.py)"

# re-exported for the tests/tree-rewrite hooks
from core.plugin_system.discovery_cache import (  # noqa: F401
    cached_scan, reset_plugin_entry_scan_cache, reset_tab_entry_scan_cache)

import ast
import importlib.util
import json
import logging
import pkgutil
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from core.log_names import APP_LOGGER_NAME

StartupTier = Literal["bootstrap", "deferred"]
EntryKind = Literal["tab", "plugin"]

_SRC = Path(__file__).resolve().parents[2]
_PLUGINS_ROOT = _SRC / "plugins"
_TABS_ROOT = _SRC / "tabs"

_SKIP_TAB_PACKAGES = frozenset({"contract", "registry"})

# Build-time discovery manifest (written by src/devtools/gen_discovery_manifest.py).
# A frozen PyInstaller bundle ships no ``.py`` files on disk, so the filesystem
# AST scan finds nothing and every tab/plugin module has to be imported just to
# be discovered. The manifest carries those entry points as data instead; the
# import scan stays the dev path and the fail-open fallback.
_MANIFEST_PATH = Path(__file__).with_name("discovery_manifest.json")
MANIFEST_VERSION = 1
MANIFEST_GENERATED_BY = "src/devtools/gen_discovery_manifest.py"

#: Manifest paths already reported at INFO: one evidence line per process.
_LOGGED_MANIFESTS: set[Path] = set()

logger = logging.getLogger(f"{APP_LOGGER_NAME}.discovery_scan")


@dataclass(frozen=True, slots=True)
class Entry:
    """One manifest record: the module to import and what it provides.

    ``id`` is the tab package name or the ``@plugin(name=...)`` value; ``attr``
    is the concrete TabContract / Plugin subclass name.
    """

    kind: EntryKind
    id: str
    module: str
    attr: str
    startup_tier: StartupTier
    startup_order: int = 0


@dataclass(frozen=True, slots=True)
class PluginEntryPoint:
    module_name: str
    plugin_py: Path
    plugin_name: str
    startup_tier: StartupTier
    startup_order: int = 0


@dataclass(frozen=True, slots=True)
class TabEntryPoint:
    module_name: str
    tab_py: Path
    package_name: str
    startup_tier: StartupTier


def iter_plugin_entry_points(*, src_root: Path | None = None) -> tuple[PluginEntryPoint, ...]:
    """Discover plugin entry points (manifest, filesystem AST scan, import fallback).

    The manifest applies only to the real tree: an explicit ``src_root`` is a
    fixture tree, and a frozen bundle has no sources on disk, so both end at
    ``pkgutil`` + import.
    """
    manifest = _manifest_for(src_root)
    if manifest is not None:
        return tuple(
            PluginEntryPoint(
                e.module, Path(f"<manifest {e.module}>"), e.id, e.startup_tier, e.startup_order
            )
            for e in manifest
            if e.kind == "plugin"
        )
    return cached_scan("plugin", src_root,
        _iter_plugin_entry_points_from_filesystem, _iter_plugin_entry_points_via_import)


def plugin_modules_for_tier(tier: StartupTier, *, src_root: Path | None = None) -> tuple[str, ...]:
    entries = [e for e in iter_plugin_entry_points(src_root=src_root) if e.startup_tier == tier]
    entries.sort(key=lambda e: (e.startup_order, e.module_name))
    return tuple(e.module_name for e in entries)


def iter_tab_entry_points(*, src_root: Path | None = None) -> tuple[TabEntryPoint, ...]:
    """Discover tab packages (manifest, filesystem AST scan, import fallback)."""
    manifest = _manifest_for(src_root)
    if manifest is not None:
        return tuple(
            TabEntryPoint(e.module, Path(f"<manifest {e.module}>"), e.id, e.startup_tier)
            for e in manifest
            if e.kind == "tab"
        )
    return cached_scan("tab", src_root,
        _iter_tab_entry_points_from_filesystem, _iter_tab_entry_points_via_import)


def tab_packages_for_tier(tier: StartupTier, *, src_root: Path | None = None) -> tuple[str, ...]:
    return tuple(
        e.package_name
        for e in iter_tab_entry_points(src_root=src_root)
        if e.startup_tier == tier
    )


def _manifest_for(src_root: Path | None) -> list[Entry] | None:
    return None if src_root is not None else load_discovery_manifest()


def load_discovery_manifest(path: Path | None = None) -> list[Entry] | None:
    """Load the build-time discovery manifest, or ``None`` if unusable.

    ``None`` = "no usable manifest": missing, unreadable, corrupt, unknown
    version or a malformed record all fail OPEN with one warning — the import
    scan then runs unchanged, so a bad manifest can never crash startup.
    """
    manifest_path = path or _MANIFEST_PATH
    if not manifest_path.is_file():
        return None
    try:
        entries = _entries_from_manifest_payload(
            json.loads(manifest_path.read_text(encoding="utf-8"))
        )
    except Exception:
        logger.warning(
            "%s unusable; falling back to the import-based discovery scan",
            manifest_path,
            exc_info=True,
        )
        return None
    _log_manifest_used(manifest_path, len(entries))
    return entries


def _log_manifest_used(manifest_path: Path, entry_count: int) -> None:
    """Name the manifest a discovery consumed, once per process.

    Silent success is not evidence: without this line nobody can tell whether a
    frozen start used the shipped data or paid for the import scan it exists to
    avoid. One line per path keeps the repeated discovery call sites (bootstrap
    tier, deferred tier, session-picker grid) from repeating it.
    """
    if manifest_path in _LOGGED_MANIFESTS:
        return
    _LOGGED_MANIFESTS.add(manifest_path)
    logger.info("Discovery manifest: %d entry points from %s", entry_count, manifest_path)


def _entries_from_manifest_payload(payload: object) -> list[Entry]:
    if not isinstance(payload, dict) or payload.get("version") != MANIFEST_VERSION:
        raise ValueError(f"unsupported manifest version: {payload!r:.120}")
    records = payload.get("entries")
    if not isinstance(records, list) or not records:
        raise ValueError("manifest carries no entries")
    keys = ("kind", "id", "module", "attr", "startup_tier")
    entries: list[Entry] = []
    for rec in records:
        fields = [rec.get(k) for k in keys] if isinstance(rec, dict) else []
        order = rec.get("startup_order", 0) if isinstance(rec, dict) else None
        if len(fields) != 5 or not all(isinstance(v, str) and v for v in fields):
            raise ValueError(f"malformed manifest entry: {rec!r:.120}")
        kind, ident, module, attr, tier = fields
        if kind not in ("tab", "plugin") or tier not in ("bootstrap", "deferred"):
            raise ValueError(f"malformed manifest entry: {rec!r:.120}")
        bad_module = not module.startswith(("tabs.", "plugins.")) or isinstance(order, bool)
        if bad_module or not isinstance(order, int):
            raise ValueError(f"malformed manifest entry: {rec!r:.120}")
        entries.append(Entry(kind, ident, module, attr, tier, order))
    return entries


def iter_plugin_files(*, src_root: Path | None = None) -> tuple[tuple[str, Path], ...]:
    """Every plugin entry module on disk as ``(module_name, plugin.py)``.

    Shared by the filesystem scan and the manifest generator: the nested
    ``tabs/<tab>/plugins/<name>/`` walk exists once; empty for a frozen bundle.
    """
    root = src_root or _SRC
    plugins_root = root / "plugins"
    tabs_root = root / "tabs"
    found: list[tuple[str, Path]] = []

    if plugins_root.is_dir():
        for child in sorted(plugins_root.iterdir()):
            if (child / "plugin.py").is_file():
                found.append((f"plugins.{child.name}.plugin", child / "plugin.py"))

    if tabs_root.is_dir():
        for child in sorted(tabs_root.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            if (child / "plugin.py").is_file():
                found.append((f"tabs.{child.name}.plugin", child / "plugin.py"))
            nested_root = child / "plugins"
            if not nested_root.is_dir():
                continue
            for nested in sorted(nested_root.iterdir()):
                if (nested / "plugin.py").is_file():
                    module = f"tabs.{child.name}.plugins.{nested.name}.plugin"
                    found.append((module, nested / "plugin.py"))

    return tuple(found)


def _iter_plugin_entry_points_from_filesystem(
    src_root: Path | None,
) -> tuple[PluginEntryPoint, ...]:
    return tuple(
        _parse_plugin_entry(module_name=module_name, plugin_py=plugin_py)
        for module_name, plugin_py in iter_plugin_files(src_root=src_root)
    )


def _iter_tab_entry_points_from_filesystem(
    src_root: Path | None,
) -> tuple[TabEntryPoint, ...]:
    root = src_root or _SRC
    tabs_root = root / "tabs"
    entries: list[TabEntryPoint] = []

    if not tabs_root.is_dir():
        return ()

    for child in sorted(tabs_root.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name in _SKIP_TAB_PACKAGES:
            continue
        tab_py = child / "tab.py"
        if not tab_py.is_file():
            continue
        entries.append(
            TabEntryPoint(
                module_name=f"tabs.{child.name}.tab",
                tab_py=tab_py,
                package_name=child.name,
                startup_tier=_parse_tab_startup_tier(tab_py),
            )
        )

    return tuple(entries)


def _import_candidate(module_name: str, kind: str) -> types.ModuleType | None:
    """Import one discovery candidate, or ``None`` when it is not a module.

    A package that ships no entry module — ``tabs/use_cases`` has no ``tab.py``,
    a nested ``tabs/<tab>/plugins`` may have no ``plugin.py`` — is a candidate,
    not a broken entry point, and a datas-only bundle cannot tell the two apart
    from the tree. ``find_spec`` skips a non-resolving candidate cheaply and
    quietly (DEBUG); only a module that exists and fails to import stays an
    ERROR with a traceback, and one broken entry hides only itself.
    """
    try:
        resolvable = importlib.util.find_spec(module_name) is not None
    except (ImportError, ValueError):
        resolvable = False  # broken parent package / relative name
    except Exception:
        resolvable = True  # let the import below report it loudly
    if not resolvable:
        logger.debug("Import-based %s discovery skipped %s", kind, module_name)
        return None
    try:
        return importlib.import_module(module_name)
    except Exception:
        logger.exception("Import-based %s discovery failed for %s", kind, module_name)
        return None


def _iter_plugin_entry_points_via_import() -> tuple[PluginEntryPoint, ...]:
    entries: list[PluginEntryPoint] = []

    try:
        import plugins as plugins_pkg
    except ImportError:
        plugins_pkg = None

    if plugins_pkg is not None:
        for _, name, is_pkg in pkgutil.iter_modules(list(plugins_pkg.__path__)):
            if not is_pkg or name.startswith("_"):
                continue
            entry = _plugin_entry_from_import(f"plugins.{name}.plugin")
            if entry is not None:
                entries.append(entry)

    try:
        import tabs as tabs_pkg
    except ImportError:
        return tuple(entries)

    for _, tab_name, is_pkg in pkgutil.iter_modules(list(tabs_pkg.__path__)):
        if not is_pkg or tab_name.startswith("_") or tab_name in _SKIP_TAB_PACKAGES:
            continue
        entry = _plugin_entry_from_import(f"tabs.{tab_name}.plugin")
        if entry is not None:
            entries.append(entry)
        try:
            nested_pkg = importlib.import_module(f"tabs.{tab_name}.plugins")
        except ImportError:
            continue
        nested_path = getattr(nested_pkg, "__path__", None)
        if nested_path is None:
            continue
        for _, nested_name, nested_is_pkg in pkgutil.iter_modules(list(nested_path)):
            if not nested_is_pkg or nested_name.startswith("_"):
                continue
            entry = _plugin_entry_from_import(f"tabs.{tab_name}.plugins.{nested_name}.plugin")
            if entry is not None:
                entries.append(entry)

    return tuple(entries)


def _iter_tab_entry_points_via_import() -> tuple[TabEntryPoint, ...]:
    from tabs.contract import TabContract

    try:
        import tabs as tabs_pkg
    except ImportError:
        return ()

    entries: list[TabEntryPoint] = []
    for _, name, is_pkg in pkgutil.iter_modules(list(tabs_pkg.__path__)):
        if not is_pkg or name.startswith("_") or name in _SKIP_TAB_PACKAGES:
            continue
        module_name = f"tabs.{name}.tab"
        # A package under ``tabs/`` need not ship a ``tab.py`` (``use_cases``):
        # skip a candidate that does not resolve, and let a real failure stay
        # loud — both rules live in ``_import_candidate``.
        mod = _import_candidate(module_name, "tab")
        if mod is None:
            continue

        tier: StartupTier = "deferred"
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            is_tab_class = isinstance(obj, type) and issubclass(obj, TabContract)
            if is_tab_class and obj is not TabContract:
                raw = getattr(obj, "startup_tier", "deferred")
                if raw in ("bootstrap", "deferred"):
                    tier = raw  # type: ignore[assignment]
                else:
                    logger.warning(
                        "%s: invalid startup_tier %r; treating as 'deferred'",
                        module_name,
                        raw,
                    )
                break

        module_file = getattr(mod, "__file__", None)
        entries.append(
            TabEntryPoint(
                module_name=module_name,
                tab_py=Path(module_file) if module_file else Path(f"<import {module_name}>"),
                package_name=name,
                startup_tier=tier,
            )
        )

    return tuple(entries)


def _plugin_entry_from_import(module_name: str) -> PluginEntryPoint | None:
    mod = _import_candidate(module_name, "plugin")
    if mod is None:
        return None

    for attr_name in dir(mod):
        obj = getattr(mod, attr_name)
        if not isinstance(obj, type):
            continue
        meta = getattr(obj, "_plugin_meta", None)
        if not isinstance(meta, dict):
            continue
        name = meta.get("name")
        tier = meta.get("startup_tier")
        if not isinstance(name, str) or tier not in ("bootstrap", "deferred"):
            continue
        order = meta.get("startup_order", 0)
        if not isinstance(order, int):
            order = 0
        module_file = getattr(mod, "__file__", None)
        return PluginEntryPoint(
            module_name=module_name,
            plugin_py=Path(module_file) if module_file else Path(f"<import {module_name}>"),
            plugin_name=name,
            startup_tier=tier,
            startup_order=order,
        )
    return None


def _parse_plugin_entry(*, module_name: str, plugin_py: Path) -> PluginEntryPoint:
    meta = _parse_plugin_decorator(plugin_py)
    if meta is None:
        raise ValueError(
            f"{plugin_py}: @plugin(...) with name= and startup_tier= is required"
        )
    name, tier, order = meta
    return PluginEntryPoint(
        module_name=module_name,
        plugin_py=plugin_py,
        plugin_name=name,
        startup_tier=tier,
        startup_order=order,
    )


def _parse_plugin_decorator(
    plugin_py: Path,
) -> tuple[str, StartupTier, int] | None:
    tree = _parse_ast(plugin_py)
    if tree is None:
        return None

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call) or not _is_plugin_decorator_call(deco):
                continue
            kwargs = _keyword_map(deco)
            name = _string_kw(kwargs, "name")
            if name is None:
                continue
            tier = _startup_tier_kw(kwargs)
            if tier is None:
                continue
            order = _int_kw(kwargs, "startup_order", default=0)
            return name, tier, order
    return None


def _parse_tab_startup_tier(tab_py: Path) -> StartupTier:
    tree = _parse_ast(tab_py)
    if tree is None:
        return "deferred"

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if not _inherits_tab_contract(node):
            continue
        for stmt in node.body:
            found, raw = _tab_tier_statement(stmt)
            if not found:
                continue
            if raw in ("bootstrap", "deferred"):
                return raw  # type: ignore[return-value]
            # Present but invalid (typo or non-literal): fail loud here at
            # scan time; the contract-level __init_subclass__ check raises
            # again at import time so the typo can never slip into a tier.
            logger.warning(
                "%s: invalid startup_tier %r (expected 'bootstrap' or 'deferred');"
                " treating as 'deferred'", tab_py, raw,
            )
            return "deferred"
    return "deferred"


def _tab_tier_statement(stmt: ast.stmt) -> tuple[bool, str | None]:
    """``(is the startup_tier statement, its literal value)`` for a class body stmt."""
    if isinstance(stmt, ast.Assign):
        named = any(_expr_name(t) == "startup_tier" for t in stmt.targets)
        return named, _const_str(stmt.value) if named else None
    if isinstance(stmt, ast.AnnAssign) and _expr_name(stmt.target) == "startup_tier":
        return True, _const_str(stmt.value)
    return False, None


def _inherits_tab_contract(class_def: ast.ClassDef) -> bool:
    return any(_expr_name(base) == "TabContract" for base in class_def.bases)


def _parse_ast(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _is_plugin_decorator_call(call: ast.Call) -> bool:
    func = call.func
    return (isinstance(func, ast.Name) and func.id == "plugin") or (
        isinstance(func, ast.Attribute) and func.attr == "plugin"
    )


def _keyword_map(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def _string_kw(kwargs: dict[str, ast.expr], key: str) -> str | None:
    return _const_str(kwargs.get(key))


def _startup_tier_kw(kwargs: dict[str, ast.expr]) -> StartupTier | None:
    value = _const_str(kwargs.get("startup_tier"))
    return value if value in ("bootstrap", "deferred") else None  # type: ignore[return-value]


def _int_kw(kwargs: dict[str, ast.expr], key: str, *, default: int) -> int:
    node = kwargs.get(key)
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return default


def _const_str(node: ast.expr | None) -> str | None:
    value = getattr(node, "value", None)
    return value if isinstance(node, ast.Constant) and isinstance(value, str) else None


def _expr_name(node: ast.expr) -> str | None:
    return node.id if isinstance(node, ast.Name) else getattr(node, "attr", None)
