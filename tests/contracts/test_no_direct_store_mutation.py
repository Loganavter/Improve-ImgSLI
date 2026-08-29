"""No direct Store mutation outside Dispatcher.

Covers ``docs/dev/STORE.md`` invariant 1-2:

    Action ──► Dispatcher.dispatch ──► RootReducer.reduce (replace) ──► Store ──► emit_state_change

Any direct assignment to tab-owned session/document state must go through
``store.get_dispatcher().dispatch(Action, scope=...)`` and a reducer that
uses ``dataclasses.replace``. Direct ``store.viewport.session_data.image_state.image1 =``
or ``render_cache.unification_in_progress =`` etc bypasses lock/history/subscribers/
session re-pointing and causes races like preview vanishing / left-on-right.

This AST dogma scans ``src/`` for assignments whose LHS chain contains
``session_data / image_state / render_cache / document`` and fails if found
outside the reducer/store implementation or a transient ``Store()`` builder.

Transient builders (``Store()`` → ``store.get_session_state_slot("document")`` etc)
are exempted via data-flow tracking of ``Store()``-derived variables.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ._framework import SRC, iter_py, read, rel

# Intermediate attributes that denote Store-owned session/document state.
INTERMEDIATE = {"session_data", "image_state", "render_cache", "document"}

# Files that *implement* the Store/Reducer machinery and are allowed to touch
# the underlying dataclasses / slots directly.
EXEMPT = frozenset(
    {
        "src/core/store.py",
        "src/core/store_viewport.py",
        "src/core/store_workspace.py",
        "src/core/store_settings.py",
        "src/core/store_operations.py",
        "src/core/store_runtime_cache.py",
        "src/domain/workspace.py",
        "src/core/state_management/reducers.py",
        "src/core/state_management/extension_reducers.py",
        "src/core/state_management/slot_reducers.py",
        "src/core/state_management/dispatcher.py",
        "src/core/state_management/action_base.py",
        "src/tabs/image_compare/state/reducers.py",
        "src/tabs/image_compare/state/reducer.py",
        "src/tabs/image_compare/state/models.py",
    }
)


def _get_chain(node: ast.AST) -> list[str] | None:
    """Return dotted chain for ``a.b.c`` as ``[a, b, c]`` or None."""
    chain: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        chain.append(cur.attr)
        cur = cur.value  # type: ignore[assignment]
    if isinstance(cur, ast.Name):
        chain.append(cur.id)
        return chain[::-1]
    if isinstance(cur, ast.Attribute):
        sub = _get_chain(cur)
        if sub is not None:
            return sub + chain[::-1]
    return None


def _collect_transients(tree: ast.Module) -> set[str]:
    """Variables directly or transitively derived from ``Store()`` construction."""
    transients: set[str] = set()
    # direct Store()/SessionData() constructors
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            val = node.value
            if isinstance(val, ast.Call):
                func = val.func
                func_name = ""
                if isinstance(func, ast.Name):
                    func_name = func.id
                elif isinstance(func, ast.Attribute):
                    func_name = func.attr
                if func_name in {
                    "Store",
                    "SessionData",
                    "ImageSessionState",
                    "RenderCacheState",
                    "ViewportState",
                    "DocumentModel",
                }:
                    transients.add(name)
    # transitively derived: x = <expr containing transient var>
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                lhs = node.targets[0].id
                if lhs in transients:
                    continue
                rhs = node.value
                for sub in ast.walk(rhs):
                    if isinstance(sub, ast.Name) and sub.id in transients:
                        transients.add(lhs)
                        changed = True
                        break
                    if isinstance(sub, ast.Attribute):
                        chain = _get_chain(sub)
                        if chain and chain[0] in transients:
                            transients.add(lhs)
                            changed = True
                            break
                if changed:
                    break
    return transients


def _direct_store_mutations() -> list[tuple[str, int, str]]:
    offenders: list[tuple[str, int, str]] = []
    for path in iter_py(SRC):
        rel_path = rel(path)
        if rel_path in EXEMPT:
            continue
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        transients = _collect_transients(tree)
        for node in ast.walk(tree):
            targets: list[ast.AST] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AnnAssign) and node.target is not None:
                targets = [node.target]
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                elts: list[ast.AST] = []
                if isinstance(target, ast.Attribute):
                    elts = [target]
                elif isinstance(target, ast.Tuple):
                    elts = target.elts
                else:
                    continue
                for elt in elts:
                    if not isinstance(elt, ast.Attribute):
                        continue
                    chain = _get_chain(elt)
                    if chain is None:
                        continue
                    if not any(part in INTERMEDIATE for part in chain):
                        continue
                    if chain[0] in transients:
                        continue
                    # ``self._foo =`` inside Store impl already exempted via file,
                    # but also skip private attrs that are not Store state.
                    offenders.append((rel_path, node.lineno, ".".join(chain)))
    return sorted(offenders)


def test_no_direct_store_mutation():
    offenders = _direct_store_mutations()
    assert not offenders, (
        "Direct Store mutation outside Dispatcher/Reducer — "
        "use store.get_dispatcher().dispatch(Action, scope=...) → replace() instead "
        f"({len(offenders)} hits):\n  " + "\n  ".join(f"{p}:{ln} — {chain} = ..." for p, ln, chain in offenders)
    )
