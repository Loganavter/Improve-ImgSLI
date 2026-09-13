"""Sync paths must not swallow failures silently (no bare except-pass).

Dogma source: docs/dev/STORE.md + docs/dev/CONTRACTS.md sync boundary --
a ``refresh_*toolbar`` / ``_resolve_*presenter`` / ``handle_store_domain``
that catches ``Exception`` and does ``pass`` / ``return None`` hides a
Store->widget desync (e.g. ``refresh_filename_overlay_toolbar`` resolving
no presenter on early-bootstrap restore: Store True, button False, zero
log lines). Silent ``return None`` is the same hole with a different
spelling -- sync helpers must return ``bool`` (synced or not) and log.

Template: tests/contracts/test_no_direct_store_mutation.py (discovery via
live shape + filesystem, EXEMPT impl files, per-site offender list).
Scope is deliberately narrow: only ``ExceptHandler`` bodies inside sync
functions (by function name, any tab), not every try/except in the tree.
"""

from __future__ import annotations

import ast

from ._framework import SRC, read, rel

_SYNC_FUNCTION_HINTS = (
    "handle_store_domain",
    "apply_initial_state",
    "apply_host_session_mode",
    "refresh_",
    "_resolve_",
    "restore_viewport_block",
    "_restore_render_config",
    "update_toolbar_states",
    "_sync_",
    "toggle_edit_layout_visibility",
)

_SYNC_FILE_HINTS = (
    "chrome_sync.py",
    "session_persistence.py",
    "toolbar/state.py",
    "transient_",
)


def _is_sync_file(path) -> bool:
    name = path.name
    return any(h in name for h in _SYNC_FILE_HINTS)


def _is_sync_function(fn: ast.FunctionDef) -> bool:
    return any(h in fn.name for h in _SYNC_FUNCTION_HINTS)


def _iter_sync_files():
    tabs_root = SRC / "tabs"
    if not tabs_root.is_dir():
        return
    for py in tabs_root.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        if _is_sync_file(py):
            yield py


def _handler_is_silent(handler: ast.ExceptHandler) -> bool:
    if not handler.body:
        return True
    for stmt in handler.body:
        if isinstance(stmt, ast.Pass):
            continue
        if isinstance(stmt, ast.Return):
            if stmt.value is None:
                return True
            if isinstance(stmt.value, ast.Constant) and stmt.value.value is None:
                return True
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            # bare docstring / Ellipsis body
            continue
        return False
    return True


def _handler_logs(handler: ast.ExceptHandler) -> bool:
    for node in ast.walk(handler):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in (
                "warning",
                "error",
                "exception",
                "debug",
                "info",
            ):
                return True
    return False


def _scan_file(path) -> list[str]:
    try:
        tree = ast.parse(read(path))
    except SyntaxError:
        return []
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not _is_sync_function(node):
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.ExceptHandler):
                continue
            if _handler_is_silent(sub) and not _handler_logs(sub):
                offenders.append(
                    f"{rel(path)}:{sub.lineno} {node.name}() swallows Exception "
                    f"silently (log + return bool instead of pass/return None)"
                )
    return offenders


def _scan_all() -> list[str]:
    out: list[str] = []
    for path in _iter_sync_files():
        out.extend(_scan_file(path))
    return sorted(out)


def test_sync_paths_do_not_swallow_exceptions_silently():
    offenders = _scan_all()
    assert not offenders, (
        "Silent except-pass in Store->widget sync paths hides desyncs "
        "(Store True, button stale, no log). Log the failure and return "
        "bool instead:\n  - " + "\n  - ".join(offenders)
    )


def test_refresh_toolbar_helpers_report_bool():
    """ ``refresh_*toolbar`` helpers must be typed ``-> bool`` (synced or not)."""
    offenders: list[str] = []
    for path in _iter_sync_files():
        try:
            tree = ast.parse(read(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            if "refresh_" not in node.name or "toolbar" not in node.name:
                continue
            returns = node.returns
            is_bool = (
                isinstance(returns, ast.Name)
                and returns.id == "bool"
            )
            if not is_bool:
                offenders.append(
                    f"{rel(path)}:{node.lineno} {node.name}() must be typed "
                    f"-> bool so a missed presenter sync (early restore) is "
                    f"visible instead of silent None"
                )
    assert not offenders, (
        "Sync helpers with silent None return hide missed toolbar syncs:\n  - "
        + "\n  - ".join(offenders)
    )
