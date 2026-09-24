"""Redux helpers for the gallery widget side — Wave 2c (plan-gallery-redux-2026-09-24).

Thin-owner support: plain functions taking the owning widget/controller as
first argument (CODE_PATTERNS.md). All dispatch goes through the frozen
Wave-1 seam — slot ``gallery`` (``GALLERY_SLOT_NAME``), actions from
``core.state_management.gallery_actions``, scope ``"gallery"`` — and every
helper is fail-open: with no store/dispatcher (tests, unbootstrapped tabs)
each dispatch returns ``False`` and each slot read returns ``None`` so the
legacy controller path runs exactly as before.

Never raises: every resolver guards with ``try/except`` and returns a
sentinel — gestures must never crash on store wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

GALLERY_SCOPE = "gallery"
GALLERY_SLOT_NAME = "gallery"


def resolve_store(owner: Any) -> Any | None:
    """Find the Redux store reachable from *owner* (widget/controller/tab).

    Walks explicit owner links only (``_context.store``, ``widget``,
    ``_controller``/``_owner``) — no implied global lookups.
    """
    seen: set[int] = set()
    stack: list[Any] = [owner]
    while stack:
        obj = stack.pop()
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        try:
            ctx = getattr(obj, "_context", None)
            store = getattr(ctx, "store", None) if ctx is not None else None
            if store is not None and hasattr(store, "get_dispatcher"):
                return store
            store = getattr(obj, "store", None)
            if store is not None and hasattr(store, "get_dispatcher"):
                return store
        except Exception:
            pass
        for attr in ("widget", "_widget", "_controller", "_owner", "_gallery_controller"):
            try:
                nxt = getattr(obj, attr, None)
            except Exception:
                continue
            if nxt is not None and id(nxt) not in seen:
                stack.append(nxt)
        try:
            win = obj.window() if hasattr(obj, "window") else None
        except Exception:
            win = None
        if win is not None and id(win) not in seen:
            stack.append(win)
            for attr in ("_gallery_controller", "_controller"):
                try:
                    nxt = getattr(win, attr, None)
                except Exception:
                    continue
                if nxt is not None and id(nxt) not in seen:
                    stack.append(nxt)
    return None


def dispatch_gallery(owner: Any, action: Any) -> bool:
    """Dispatch a gallery action with scope ``"gallery"``; fail-open.

    Returns True when the action reached the dispatcher, False when there
    is no store/dispatcher (caller keeps the legacy controller path).
    """
    try:
        store = resolve_store(owner)
        if store is None:
            return False
        dispatcher = store.get_dispatcher()
        if dispatcher is None:
            return False
        dispatcher.dispatch(action, scope=GALLERY_SCOPE)
        return True
    except Exception:
        return False


def read_gallery_slot(owner: Any, store: Any | None = None) -> Any | None:
    """Read the ``gallery`` session slot for the active session; None when absent.

    ``None`` means "no Redux state here" (no store, no active session, or a
    foreign session type without the slot) — callers must skip rendering,
    never clear the grid on it.
    """
    try:
        store = store if store is not None else resolve_store(owner)
        if store is None or not hasattr(store, "get_session_state_slot"):
            return None
        return store.get_session_state_slot(GALLERY_SLOT_NAME)
    except Exception:
        return None


def entries_for_paths(paths: list) -> list[tuple[str, int]]:
    """Build ``[(path_str, mtime_ns), ...]`` action entries; mtime 0 on stat failure."""
    entries: list[tuple[str, int]] = []
    for p in paths or []:
        try:
            pp = Path(p)
        except Exception:
            continue
        try:
            mtime = pp.stat().st_mtime_ns if pp.is_file() else 0
        except Exception:
            mtime = 0
        entries.append((str(pp), int(mtime or 0)))
    return entries


def entries_for_folder(folder: Path) -> list[tuple[str, int]]:
    """Scan *folder* into action entries via the shared folder scanner.

    Raises nothing: scan failure yields ``[]`` (caller falls back to the
    legacy controller path, which owns error UX).
    """
    try:
        from tabs.image_gallery.services.folder_scanner import scan_folder

        items = scan_folder(Path(folder))
        out: list[tuple[str, int]] = []
        for it in items or []:
            try:
                out.append((str(it.path), int(getattr(it, "mtime_ns", 0) or 0)))
            except Exception:
                continue
        return out
    except Exception:
        return []
