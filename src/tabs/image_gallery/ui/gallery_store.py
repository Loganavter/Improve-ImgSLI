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

# Single source of truth for the seam literals (Wave-1 frozen interface):
# slot + scope both come from bootstrap_reducers — no second definition.
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME

GALLERY_SCOPE = GALLERY_SLOT_NAME


def resolve_store(owner: Any) -> Any | None:
    """Find the Redux store reachable from *owner* (widget/controller/tab).

    Walks explicit owner links only (``_context.store``, ``widget``,
    the ``_owner_for_triage`` protocol) — no implied global lookups, no
    window-attribute scans (no writers since G1/G2 deleted the pokes).
    """
    seen: set[int] = set()
    stack: list[Any] = [owner]
    # Protocol-first (G5): seed the attached controller when the owner is
    # a widget, so controller-side store/dispatcher resolve directly.
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        proto = resolve() if callable(resolve) else None
        if proto is not None and proto is not owner:
            stack.append(proto)
    except Exception:
        pass
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
        for attr in ("widget", "_widget"):
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


def resolve_owner_session_id(owner: Any) -> str | None:
    """Own session id for *owner* (widget/controller/tab) — never the active default.

    Walks explicit owner links only (``_gallery_session_id`` on the owner
    itself, the ``_owner_for_triage`` protocol, the tab's
    ``_active_session_id``, then ``widget``/``_widget``/``_attached_controller``
    child links) — no implied global lookups. Returns None when no copy has
    been bound yet (unbound legacy contexts); callers then address the
    active session EXPLICITLY, never via the omitted default.
    """
    seen: set[int] = set()
    stack: list[Any] = [owner]
    # Protocol-first (G5): the attached controller owns the binding when the
    # owner is a widget, so controller-side ids resolve directly.
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        proto = resolve() if callable(resolve) else None
        if proto is not None and proto is not owner:
            stack.append(proto)
    except Exception:
        pass
    while stack:
        obj = stack.pop()
        if obj is None or id(obj) in seen:
            continue
        seen.add(id(obj))
        try:
            sid = getattr(obj, "_gallery_session_id", None)
            if sid:
                return sid
        except Exception:
            pass
        try:
            # TabContract side: the tab tracks its own active session id.
            sid = getattr(obj, "_active_session_id", None)
            if sid:
                return sid
        except Exception:
            pass
        for attr in ("widget", "_widget", "_attached_controller"):
            try:
                nxt = getattr(obj, attr, None)
            except Exception:
                continue
            if nxt is not None and id(nxt) not in seen:
                stack.append(nxt)
    return None


def read_gallery_slot(
    owner: Any, session_id: str | None = None, store: Any | None = None
) -> Any | None:
    """Read the ``gallery`` session slot for the OWNER's session; None when absent.

    ``session_id`` wins when given; otherwise the owner's own bound id
    (``resolve_owner_session_id``). Unbound owners fall back to the active
    session EXPLICITLY (same value the old default produced, but addressed,
    never omitted) so storeless-era callers keep working.

    ``None`` means "no Redux state here" (no store, no session, or a
    foreign session type without the slot) — callers must skip rendering,
    never clear the grid on it.
    """
    try:
        store = store if store is not None else resolve_store(owner)
        if store is None or not hasattr(store, "get_session_state_slot"):
            return None
        if session_id is None:
            session_id = resolve_owner_session_id(owner)
        if session_id is None:
            try:
                active = store.get_active_workspace_session()
                session_id = getattr(active, "id", None)
            except Exception:
                session_id = None
        return store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=session_id)
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
