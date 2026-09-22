"""Store-projection fanout symmetry: every sync entry point moves all projections.

Dogma source: docs/dev/STORE.md (all state changes go through Dispatcher,
widgets sync from the Store) + docs/dev/CONTRACTS.md sync-boundary rules.

A Store->widget sync function that moves one projection (panel visibility)
must move the sibling projections (toolbar/button sync via the toolbar
fanout) in the SAME branch. Otherwise the Store flips, the panel follows,
the button stays stale -- e.g. image_compare's ``handle_store_domain``
visible branch once moved only the edit row while the deferred branch
moved both (button unchecked after restart while the flag was True).

Keys are sync-vocabulary CONVENTIONS, not tab names (template:
tests/contracts/test_no_tab_to_tab_service.py discovery +
test_no_direct_store_mutation.py live-shape thinking):
- entry points: ``handle_store_domain`` / ``apply_initial_state`` /
  ``apply_host_session_mode`` (chrome-sync / TabContract surface);
- visibility moves: ``setVisible`` or ``toggle_*_visibility``;
- toolbar fanout: ``update_toolbar_states`` (toolbar-presenter fanout
  entry convention), ``sync_state`` / ``get_feature_toolbar_bindings``
  (shared CanvasFeatureToolbarBinding API), ``refresh_*toolbar``.
Tabs without this sync shape (stubs) pass vacuously; any tab that grows
it is covered automatically. One owner per invariant (TESTING.md).

Template for branch walking: test_no_drag_overlay_desync.py (per-branch
offenders, early-return guard handling).
"""

from __future__ import annotations

import ast
import re

from ._framework import SRC, parse, read, rel

_SYNC_FUNCTIONS = frozenset(
    {
        "handle_store_domain",
        "apply_initial_state",
        "apply_host_session_mode",
    }
)

_TOGGLE_ATTRS = frozenset({"setVisible"})
_TOGGLE_RE = re.compile(r"^toggle_.*_visibility$")

_FANOUT_ATTRS = frozenset(
    {
        "update_toolbar_states",
        "sync_state",
        "get_feature_toolbar_bindings",
    }
)
_FANOUT_NAMES = frozenset(
    {
        "update_toolbar_states",
        "refresh_filename_overlay_toolbar",
    }
)
_FANOUT_REFRESH_RE = re.compile(r"^refresh_.*toolbar$")


def _known_tab_roots() -> list:
    tabs_root = SRC / "tabs"
    if not tabs_root.is_dir():
        return []
    return sorted(
        d for d in tabs_root.iterdir() if d.is_dir() and (d / "tab.py").exists()
    )


def _sync_files():
    out = []
    for tab in _known_tab_roots():
        for name in ("use_cases/chrome_sync.py", "tab.py"):
            p = tab / name
            if p.is_file():
                out.append(p)
    return out


def _is_toggle(attr: str) -> bool:
    return attr in _TOGGLE_ATTRS or bool(_TOGGLE_RE.match(attr))


def _is_fanout_attr(attr: str) -> bool:
    return attr in _FANOUT_ATTRS or bool(_FANOUT_REFRESH_RE.match(attr))


def _is_fanout_name(name: str) -> bool:
    return name in _FANOUT_NAMES or bool(_FANOUT_REFRESH_RE.match(name))


def _call_marks(call: ast.Call) -> set[str]:
    marks: set[str] = set()
    func = call.func
    if isinstance(func, ast.Attribute):
        if _is_toggle(func.attr):
            marks.add("toggle")
        if _is_fanout_attr(func.attr):
            marks.add("toolbar_sync")
    elif isinstance(func, ast.Name):
        if _is_fanout_name(func.id):
            marks.add("toolbar_sync")
    return marks


def _block_marks(stmts: list[ast.stmt]) -> set[str]:
    marks: set[str] = set()
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call):
                marks |= _call_marks(node)
    return marks


def _block_has_return(stmts: list[ast.stmt]) -> bool:
    return any(isinstance(n, ast.Return) for stmt in stmts for n in ast.walk(stmt))


def _is_visibility_branch(node: ast.If) -> bool:
    try:
        src = ast.unparse(node.test)
    except Exception:
        return False
    low = src.lower()
    return ("is_visible" in low) or ("isvisible" in low)


def _statements_after(body: list[ast.stmt], pivot: ast.If) -> list[ast.stmt]:
    try:
        idx = next(i for i, s in enumerate(body) if s is pivot)
    except StopIteration:
        return []
    return body[idx + 1 :]


def _find_functions(tree: ast.Module, name: str) -> list[ast.FunctionDef]:
    return [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == name
    ]


def _check_branch(path, fname: str, lineno: int, label: str, branch) -> list[str]:
    marks = _block_marks(branch)
    if "toggle" in marks and "toolbar_sync" not in marks:
        return [
            f"{rel(path)}:{lineno} {fname}() {label} branch moves panel "
            f"visibility without toolbar fanout (add the toolbar sync entry "
            f"next to the visibility toggle)"
        ]
    return []


def _scan_file(path) -> list[str]:
    tree = parse(path)
    if tree is None:
        return []
    offenders: list[str] = []
    for fname in _SYNC_FUNCTIONS:
        for fn in _find_functions(tree, fname):
            handled_guard = False
            for if_node in [
                n for n in ast.walk(fn) if isinstance(n, ast.If) and _is_visibility_branch(n)
            ]:
                if if_node.orelse:
                    for label, branch in (
                        ("visible", if_node.body),
                        ("deferred", if_node.orelse),
                    ):
                        offenders.extend(
                            _check_branch(path, fname, if_node.lineno, label, branch)
                        )
                    handled_guard = True
                    continue
                # Early-return guard (if not visible: ...; return): the code
                # AFTER the guard is the visible branch.
                if _block_has_return(if_node.body):
                    tail = _statements_after(fn.body, if_node)
                    for label, branch in (
                        ("deferred", if_node.body),
                        ("visible", tail),
                    ):
                        offenders.extend(
                            _check_branch(path, fname, if_node.lineno, label, branch)
                        )
                    handled_guard = True
            if handled_guard:
                continue
            # Straight-line sync entry point (e.g. apply_host_session_mode):
            # a lone visibility toggle without toolbar fanout desyncs.
            if fname == "apply_host_session_mode":
                offenders.extend(
                    _check_branch(path, fname, fn.lineno, "straight-line", [fn])
                )
    return offenders


def _scan_all() -> list[str]:
    out: list[str] = []
    for path in _sync_files():
        out.extend(_scan_file(path))
    return sorted(out)


def test_store_projection_fanout_is_symmetric():
    offenders = _scan_all()
    assert not offenders, (
        "Store->widget fanout asymmetry: panel visibility moves without the "
        "sibling toolbar/button fanout in the same branch. The Store flips, "
        "one projection follows, the other stays stale:\n  - "
        + "\n  - ".join(offenders)
    )
