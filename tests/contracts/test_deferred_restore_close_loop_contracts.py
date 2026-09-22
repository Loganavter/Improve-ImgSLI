"""Deferred restores must close the loop (retry + re-sync in the callback).

Dogma source: docs/dev/STORE.md (dispatcher may be unbound at bootstrap;
``QTimer.singleShot(0, dispatch)`` retry rule -- dispatcher.py:118) +
STATE_SLOT_MANIFEST.md (post-restore toolbar sync runs at the end of BOTH
the immediate and the deferred dispatch completions).

Every ``QTimer.singleShot`` in persistence/chrome_sync code (any tab,
discovered via filesystem -- template: test_no_tab_to_tab_service.py)
must carry the close-out inside the deferred callback: a retry or re-sync
reference (``dispatch`` / ``refresh`` / ``sync`` / ``restore``). A bare
defer that only re-writes slots without re-syncing projections replays
the restart desync one tick later (Store True, button False, no log).

Template: tests/contracts/test_no_drag_overlay_desync.py (walk inside one
call site, unparse the payload, offender list with file:line).
"""

from __future__ import annotations

import ast

from ._framework import SRC, parse, read, rel

_CLOSE_TOKENS = (
    "dispatch",
    "refresh",
    "sync_state",
    "update_toolbar",
    "restore",
    # Retry indirection: the callback re-invokes a ``_deferred_*`` helper that
    # dispatches on retry (settings_persistence._deferred_auto_calculate), or
    # re-emits via the slot API (set_session_state_slot with emit_scope /
    # emit_state_change notifies subscribers the same way a dispatch does).
    "deferred",
    "set_session_state_slot",
    "emit_state_change",
    "emit_scope",
)

_DEFER_FILES_HINTS = ("persistence", "chrome_sync")


def _iter_defer_files():
    tabs_root = SRC / "tabs"
    if not tabs_root.is_dir():
        return
    for py in tabs_root.rglob("*.py"):
        if "__pycache__" in py.parts or "tests" in py.parts:
            continue
        if any(h in py.name for h in _DEFER_FILES_HINTS):
            yield py


def _callback_source(call: ast.Call) -> str:
    if len(call.args) < 2:
        return ""
    try:
        return ast.unparse(call.args[1])
    except Exception:
        return ""


def _is_singleshot(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Attribute) and func.attr == "singleShot":
        return True
    return False


def _scan_file(path) -> list[str]:
    tree = parse(path)
    if tree is None:
        return []
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_singleshot(node):
            continue
        src = _callback_source(node).lower()
        if not any(tok in src for tok in _CLOSE_TOKENS):
            offenders.append(
                f"{rel(path)}:{node.lineno} QTimer.singleShot defers without "
                f"retry/re-sync in the callback (must reference "
                f"dispatch/refresh/sync/restore or the desync replays a tick later)"
            )
    return offenders


def _scan_all() -> list[str]:
    out: list[str] = []
    for path in _iter_defer_files():
        out.extend(_scan_file(path))
    return sorted(out)


def test_deferred_restores_close_the_loop():
    offenders = _scan_all()
    assert not offenders, (
        "Deferred persistence callbacks that never re-sync projections:\n  - "
        + "\n  - ".join(offenders)
    )
