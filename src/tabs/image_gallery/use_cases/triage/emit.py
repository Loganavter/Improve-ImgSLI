"""Triage Redux emit + owner-read helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). Every sibling triage submodule reads owner state (``_items_of`` /
``_resolve_state``) and/or dispatches through ``_emit_gallery`` /
``_transact_gallery`` / ``_emit_rank_snapshot``, so those shared seams live
here.
"""

from __future__ import annotations

from pathlib import Path

from core.state_management.gallery_actions import GalleryTriageFinished
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME


def _emit_gallery(owner, action) -> bool:
    """Dispatch one gallery action with scope 'gallery' via the owner chain.

    Prefers the controller's ``_emit_gallery`` (session-aware write path);
    falls back to a direct dispatcher dispatch resolved from any visible
    context/store. Returns False when no dispatcher is wired (storeless
    unit contexts keep pure-local behavior). Never mutates slot values.
    """
    seen: set[int] = set()
    candidates = [owner]
    # Protocol-first (G5): the widget's attached controller carries the
    # session-aware write path (own-dispatch accounting). Legacy
    # ``_controller``/``_owner`` scans are gone (no writers since G1/G2);
    # ``widget``/``_widget`` child links stay as last resort.
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        proto = resolve() if callable(resolve) else None
        if proto is not None:
            candidates.append(proto)
    except Exception:
        pass
    for attr in ("widget", "_widget"):
        try:
            candidates.append(getattr(owner, attr, None))
        except Exception:
            pass
    for cand in candidates:
        if cand is None or id(cand) in seen:
            continue
        seen.add(id(cand))
        emit = getattr(cand, "_emit_gallery", None)
        if callable(emit):
            try:
                if bool(emit(action)):
                    return True
            except Exception:
                pass
    for cand in candidates:
        if cand is None:
            continue
        try:
            ctx = getattr(cand, "_context", None) or getattr(cand, "context", None)
            store = getattr(ctx, "store", None) or getattr(cand, "store", None)
            dispatcher = store.get_dispatcher() if store is not None else None
            if dispatcher is None:
                continue
            dispatcher.dispatch(action, scope=GALLERY_SLOT_NAME)
            return True
        except Exception:
            continue
    return False


def _transact_gallery(owner, actions) -> bool:
    """Batch path: Store.transact([...], scope='gallery'), else sequential."""
    batch = [a for a in actions or []]
    if not batch:
        return False
    seen: set[int] = set()
    candidates = [owner]
    # Protocol-first (G5): see _emit_gallery above — same candidate order.
    try:
        resolve = getattr(owner, "_owner_for_triage", None)
        proto = resolve() if callable(resolve) else None
        if proto is not None:
            candidates.append(proto)
    except Exception:
        pass
    for attr in ("widget", "_widget"):
        try:
            candidates.append(getattr(owner, attr, None))
        except Exception:
            pass
    for cand in candidates:
        if cand is None or id(cand) in seen:
            continue
        seen.add(id(cand))
        meth = getattr(cand, "_transact_gallery", None)
        if callable(meth):
            try:
                if bool(meth(batch)):
                    return True
            except Exception:
                pass
    ok = False
    for action in batch:
        try:
            ok = _emit_gallery(owner, action) or ok
        except Exception:
            pass
    return ok


def _emit_rank_snapshot(owner) -> bool:
    """Mirror local ranks into the slot (GalleryTriageFinished, same summary).

    keep_best / make_best / keep_best_of_series re-rank locally; the slot's
    per-item ranks would otherwise go stale. Triage state/mode/source pass
    through unchanged — only ranks move.
    """
    try:
        st = getattr(owner, "state", None)
        if st is None:
            return False
        ranks: dict[str, int] = {}
        for it in list(getattr(st, "items", []) or []):
            try:
                r = getattr(it, "rank", None)
                if r is not None:
                    ranks[str(getattr(it, "path"))] = int(r)
            except Exception:
                continue
        ts = getattr(getattr(st, "triage_state", "done"), "value", None)
        if ts is None:
            ts = getattr(st, "triage_state", "done")
        try:
            triage_state = str(ts or "done")
        except Exception:
            triage_state = "done"
        mode = getattr(st, "mode", None)
        mode = getattr(mode, "value", mode)
        try:
            mode_s = str(mode) if mode is not None else None
        except Exception:
            mode_s = None
        source = getattr(st, "source_path", None)
        try:
            source_s = str(source) if source is not None else None
        except Exception:
            source_s = None
        return _emit_gallery(
            owner,
            GalleryTriageFinished(
                triage_state=triage_state,
                mode=mode_s,
                source_path=source_s,
                ranks=ranks,
            ),
        )
    except Exception:
        return False


def _mtime_of(path) -> int:
    try:
        return int(Path(path).stat().st_mtime_ns)
    except Exception:
        return 0


def _items_of(owner) -> list:
    st = getattr(owner, "state", None)
    if st is None:
        # Try widget state
        w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
        if w is not None:
            st = getattr(w, "_state", None) or getattr(getattr(w, "_controller", None), "state", None)
    if st is None:
        return []
    items = getattr(st, "items", None) or []
    return list(items)


def _resolve_state(owner):
    """Resolve the state holder that owns ``.items`` (controller/state/widget).

    Single resolution order used by the pool-membership helpers: ``owner.state``
    first, then the widget's ``_state``/``_controller.state`` fallback, then
    ``owner._state``. Returns None when no holder exposes ``items``.
    """
    st = getattr(owner, "state", None)
    if st is not None and hasattr(st, "items"):
        return st
    w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
    if w is not None:
        st = getattr(w, "_state", None) or getattr(
            getattr(w, "_controller", None), "state", None
        )
    if (st is None or not hasattr(st, "items")) and hasattr(owner, "_state"):
        st = getattr(owner, "_state", None)
    if st is not None and hasattr(st, "items"):
        return st
    return None
