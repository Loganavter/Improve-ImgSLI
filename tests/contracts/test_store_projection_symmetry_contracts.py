"""Store-projection fanout symmetry: every sync entry point moves all projections.

Dogma source: docs/dev/STORE.md (all state changes go through Dispatcher,
widgets sync from the Store) + docs/dev/CONTRACTS.md sync-boundary rules.

A Store->widget sync function that moves one projection (panel visibility,
``toggle_*_visibility``/``setVisible``) must move the sibling projections
(toolbar/button sync via ``update_toolbar_states``/``sync_state``/
``refresh_*toolbar``) in the SAME branch. Otherwise the Store flips, the
panel follows, the button stays stale -- e.g. image_compare
``handle_store_domain`` visible branch moved only the edit row while the
deferred branch moved both (``btn_file_names`` unchecked after restart
while ``include_file_names_in_saved`` was True).

Template: tests/contracts/test_no_drag_overlay_desync.py (walk inside one
function, per-branch offender list). Discovery: tests/contracts/
test_no_tab_to_tab_service.py (concrete tabs = dirs with tab.py, no
hard-coded tab names).
"""

from __future__ import annotations

import ast

from ._framework import SRC, iter_py, read, rel

_SYNC_FUNCTIONS = frozenset(
    {
        "handle_store_domain",
        "apply_initial_state",
        "apply_host_session_mode",
    }
)

_TOGGLE_ATTRS = frozenset(
    {
        "toggle_edit_layout_visibility",
        "setVisible",
    }
)

_TOOLBAR_SYNC_ATTRS = frozenset(
    {
        "update_toolbar_states",
        "sync_state",
    }
)

_TOOLBAR_SYNC_NAMES = frozenset(
    {
        "update_toolbar_states",
        "refresh_filename_overlay_toolbar",
    }
)


def _known_tab_roots() -> list:
    tabs_root = SRC / "tabs"
    if not tabs_root.is_dir():
        return []
    return sorted(
        d for d in tabs_root.iterdir() if d.is_dir() and (d / "tab.py").exists()
    )


def _sync_files():
    tabs = _known_tab_roots()
    if not tabs:
        return list(iter_py(SRC))
    out = []
    for tab in tabs:
        for name in ("use_cases/chrome_sync.py", "tab.py"):
            p = tab / name
            if p.is_file():
                out.append(p)
    return out


def _func_calls(fn: ast.FunctionDef) -> list[ast.Call]:
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call)]


def _call_marks(call: ast.Call) -> set[str]:
    marks: set[str] = set()
    func = call.func
    if isinstance(func, ast.Attribute):
        if func.attr in _TOGGLE_ATTRS:
            marks.add("toggle")
        if func.attr in _TOOLBAR_SYNC_ATTRS:
            marks.add("toolbar_sync")
        if func.attr.startswith("refresh_") and "toolbar" in func.attr:
            marks.add("toolbar_sync")
    elif isinstance(func, ast.Name):
        if func.id in _TOOLBAR_SYNC_NAMES:
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


def _scan_file(path) -> list[str]:
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return []
    offenders: list[str] = []
    for fname in _SYNC_FUNCTIONS:
        for fn in _find_functions(tree, fname):
            handled_guard = False
            for if_node in [
                n for n in ast.walk(fn) if isinstance(n, ast.If) and _is_visibility_branch(n)
            ]:
                # Classic if/else: compare both branches.
                if if_node.orelse:
                    for label, branch in (
                        ("visible", if_node.body),
                        ("deferred", if_node.orelse),
                    ):
                        marks = _block_marks(branch)
                        if "toggle" in marks and "toolbar_sync" not in marks:
                            offenders.append(
                                f"{rel(path)}:{if_node.lineno} {fname}() {label} branch "
                                f"moves panel visibility without toolbar sync "
                                f"(add update_toolbar_states/sync_state next to "
                                f"toggle_edit_layout_visibility)"
                            )
                    handled_guard = True
                    continue
                # Early-return guard (if not visible: ...; return): the code
                # AFTER the guard is the visible branch. Compare guard body
                # (deferred) vs tail (visible).
                if _block_has_return(if_node.body):
                    tail = _statements_after(fn.body, if_node)
                    for label, branch in (
                        ("deferred", if_node.body),
                        ("visible", tail),
                    ):
                        marks = _block_marks(branch)
                        if "toggle" in marks and "toolbar_sync" not in marks:
                            offenders.append(
                                f"{rel(path)}:{if_node.lineno} {fname}() {label} branch "
                                f"moves panel visibility without toolbar sync "
                                f"(add update_toolbar_states/sync_state next to "
                                f"toggle_edit_layout_visibility)"
                            )
                    handled_guard = True
            if handled_guard:
                continue
            # Straight-line sync entry point (e.g. apply_host_session_mode):
            # a lone panel toggle without toolbar fanout desyncs button vs panel.
            if fname == "apply_host_session_mode":
                marks: set[str] = set()
                for call in _func_calls(fn):
                    marks |= _call_marks(call)
                if "toggle" in marks and "toolbar_sync" not in marks:
                    offenders.append(
                        f"{rel(path)}:{fn.lineno} {fname}() moves panel visibility "
                        f"without toolbar sync (button stays stale while the Store "
                        f"flag is True)"
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
        "sibling toolbar/button sync in the same branch. The Store flips, "
        "one projection follows, the other stays stale:\n  - "
        + "\n  - ".join(offenders)
    )
