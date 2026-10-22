"""``core.state_management``'s lazy export map must resolve.

``src/core/state_management/__init__.py`` exposes a fixed ``__all__`` whose
members are resolved lazily through ``_EXPORTS`` (name -> (module, attr)).
A stale entry is invisible to a static import of the package: the failure only
appears when the name is actually touched, so ``from core.state_management
import *`` or a new caller hits ``AttributeError: module
'core.state_management.reducers' has no attribute 'DocumentReducer'`` at use
time. That exact entry shipped: ``DocumentReducer`` is tab-owned
(``src/tabs/image_compare/state/reducer.py``) and is registered as the
``document`` slot reducer, never a core reducer.

This test checks the map statically (AST, no project import) so the promise
and its target cannot drift apart again:

* ``__all__`` and ``_EXPORTS`` name the same set;
* every target module exists under ``src/``;
* every target module defines the exported name at module level (class,
  function, or assignment).

Dogma source: ``docs/dev/STORE.md`` (reducers live where their slot lives) and
``AGENTS.md`` ("All state mutation goes through Dispatcher -> RootReducer";
core must not import tab code).
"""

from __future__ import annotations

import ast

from ._framework import SRC, parse, rel


def _state_root():
    return SRC / "core" / "state_management"


def _literal_string_list(node: ast.expr | None) -> list[str]:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return []
    return [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]


def _exports_map(tree: ast.Module) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "_EXPORTS" not in targets or not isinstance(node.value, ast.Dict):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if isinstance(value, ast.Tuple) and len(value.elts) == 2:
                module, attr = value.elts
                if isinstance(module, ast.Constant) and isinstance(attr, ast.Constant):
                    out[key.value] = (module.value, attr.value)
    return out


def _declared_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, ast.ImportFrom):
            names.update(a.asname or a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
    return names


def _module_path(dotted: str):
    parts = dotted.split(".")
    if len(parts) < 2:
        return None
    # ``core.state_management.reducers`` -> src/core/state_management/reducers.py
    base = SRC.joinpath(*parts[:-1]) / f"{parts[-1]}.py"
    pkg = SRC.joinpath(*parts) / "__init__.py"
    if base.is_file():
        return base
    if pkg.is_file():
        return pkg
    return None


def test_state_management_export_map_resolves():
    """Every name in ``__all__`` must resolve through ``_EXPORTS`` in a real module."""
    init = _state_root() / "__init__.py"
    tree = parse(init)
    assert tree is not None, "cannot parse core/state_management/__init__.py"

    all_names: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            all_names = _literal_string_list(node.value)

    assert all_names, "core/state_management/__init__.py must declare a literal __all__"

    exports = _exports_map(tree)
    assert exports, "core/state_management/__init__.py must declare a literal _EXPORTS map"

    missing_from_map = sorted(set(all_names) - set(exports))
    extra_in_map = sorted(set(exports) - set(all_names))
    assert not missing_from_map, (
        f"__all__ names without an _EXPORTS entry: {missing_from_map} "
        "(the lazy __getattr__ would raise AttributeError)"
    )
    assert not extra_in_map, f"_EXPORTS entries not listed in __all__: {extra_in_map}"

    broken: list[str] = []
    for name in all_names:
        module_name, attr_name = exports[name]
        path = _module_path(module_name)
        if path is None:
            broken.append(f"{name}: module '{module_name}' does not exist")
            continue
        target_tree = parse(path)
        if target_tree is None:
            broken.append(f"{name}: cannot parse {rel(path)}")
            continue
        if attr_name not in _declared_names(target_tree):
            broken.append(
                f"{name}: {rel(path)} does not define '{attr_name}' "
                "(the export map promises a name its target does not own)"
            )
    assert not broken, (
        "core.state_management export map promises names their targets do not define:\n  "
        + "\n  ".join(broken)
    )
