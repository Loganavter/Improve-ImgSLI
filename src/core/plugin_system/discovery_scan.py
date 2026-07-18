from __future__ import annotations

import ast
import importlib
import logging
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

StartupTier = Literal["bootstrap", "deferred"]

_SRC = Path(__file__).resolve().parents[2]
_PLUGINS_ROOT = _SRC / "plugins"
_TABS_ROOT = _SRC / "tabs"

_SKIP_TAB_PACKAGES = frozenset({"contract", "registry"})

logger = logging.getLogger("ImproveImgSLI.discovery_scan")


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
    """Discover plugin entry points (filesystem AST scan, import fallback).

    Dev checkouts have ``plugin.py`` on disk. Frozen PyInstaller bundles often
    ship only ``resources/`` under ``plugins/`` / ``tabs/`` as datas, so the
    filesystem scan finds nothing — fall back to ``pkgutil`` + import.
    """
    entries = _iter_plugin_entry_points_from_filesystem(src_root)
    if entries:
        return entries
    return _iter_plugin_entry_points_via_import()


def plugin_modules_for_tier(tier: StartupTier, *, src_root: Path | None = None) -> tuple[str, ...]:
    entries = [
        e
        for e in iter_plugin_entry_points(src_root=src_root)
        if e.startup_tier == tier
    ]
    entries.sort(key=lambda e: (e.startup_order, e.module_name))
    return tuple(e.module_name for e in entries)


def iter_tab_entry_points(*, src_root: Path | None = None) -> tuple[TabEntryPoint, ...]:
    """Discover tab packages (filesystem AST scan, import fallback)."""
    entries = _iter_tab_entry_points_from_filesystem(src_root)
    if entries:
        return entries
    return _iter_tab_entry_points_via_import()


def tab_packages_for_tier(tier: StartupTier, *, src_root: Path | None = None) -> tuple[str, ...]:
    return tuple(
        e.package_name
        for e in iter_tab_entry_points(src_root=src_root)
        if e.startup_tier == tier
    )


def _iter_plugin_entry_points_from_filesystem(
    src_root: Path | None,
) -> tuple[PluginEntryPoint, ...]:
    root = src_root or _SRC
    plugins_root = root / "plugins"
    tabs_root = root / "tabs"
    entries: list[PluginEntryPoint] = []

    if plugins_root.is_dir():
        for child in sorted(plugins_root.iterdir()):
            plugin_py = child / "plugin.py"
            if child.is_dir() and plugin_py.is_file():
                entries.append(
                    _parse_plugin_entry(
                        module_name=f"plugins.{child.name}.plugin",
                        plugin_py=plugin_py,
                    )
                )

    if tabs_root.is_dir():
        for child in sorted(tabs_root.iterdir()):
            if not child.is_dir() or child.name.startswith("_"):
                continue
            plugin_py = child / "plugin.py"
            if plugin_py.is_file():
                entries.append(
                    _parse_plugin_entry(
                        module_name=f"tabs.{child.name}.plugin",
                        plugin_py=plugin_py,
                    )
                )
            nested_plugins = child / "plugins"
            if nested_plugins.is_dir():
                for nested in sorted(nested_plugins.iterdir()):
                    nested_py = nested / "plugin.py"
                    if nested.is_dir() and nested_py.is_file():
                        entries.append(
                            _parse_plugin_entry(
                                module_name=(
                                    f"tabs.{child.name}.plugins.{nested.name}.plugin"
                                ),
                                plugin_py=nested_py,
                            )
                        )

    return tuple(entries)


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
            entry = _plugin_entry_from_import(
                f"tabs.{tab_name}.plugins.{nested_name}.plugin"
            )
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
        try:
            mod = importlib.import_module(module_name)
        except ImportError:
            logger.exception("Import-based tab discovery failed for %s", module_name)
            continue

        tier: StartupTier = "deferred"
        for attr_name in dir(mod):
            obj = getattr(mod, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, TabContract)
                and obj is not TabContract
            ):
                raw = getattr(obj, "startup_tier", "deferred")
                if raw in ("bootstrap", "deferred"):
                    tier = raw  # type: ignore[assignment]
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
    try:
        mod = importlib.import_module(module_name)
    except ImportError:
        logger.debug("Import-based plugin discovery skipped %s", module_name, exc_info=True)
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
            call = _unwrap_decorator_call(deco)
            if call is None or not _is_plugin_decorator_call(call):
                continue
            kwargs = _keyword_map(call)
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
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id == "startup_tier":
                        value = _const_str(stmt.value)
                        if value in ("bootstrap", "deferred"):
                            return value  # type: ignore[return-value]
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                if stmt.target.id == "startup_tier" and stmt.value is not None:
                    value = _const_str(stmt.value)
                    if value in ("bootstrap", "deferred"):
                        return value  # type: ignore[return-value]
    return "deferred"


def _inherits_tab_contract(class_def: ast.ClassDef) -> bool:
    for base in class_def.bases:
        name = _expr_name(base)
        if name == "TabContract":
            return True
    return False


def _parse_ast(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _unwrap_decorator_call(node: ast.expr) -> ast.Call | None:
    if isinstance(node, ast.Call):
        return node
    return None


def _is_plugin_decorator_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "plugin":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "plugin":
        return True
    return False


def _keyword_map(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def _string_kw(kwargs: dict[str, ast.expr], key: str) -> str | None:
    return _const_str(kwargs.get(key))


def _startup_tier_kw(kwargs: dict[str, ast.expr]) -> StartupTier | None:
    value = _const_str(kwargs.get("startup_tier"))
    if value in ("bootstrap", "deferred"):
        return value  # type: ignore[return-value]
    return None


def _int_kw(kwargs: dict[str, ast.expr], key: str, *, default: int) -> int:
    node = kwargs.get(key)
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    return default


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _expr_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
