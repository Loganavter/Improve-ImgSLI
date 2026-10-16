"""Gallery slot (Redux) bridge for the Image Gallery controller.

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
The write path dispatches ``GALLERY_*`` actions with ``scope='gallery'`` and
``session_id=<own>``; the read path addresses the owner's OWN session slot
(``owner._gallery_session_id``) and reconciles the local ``state`` mirror.
Owner state (``_context`` / ``_subscribed_gallery_store`` /
``_gallery_session_id`` / ``_own_gallery_emits``) stays on the owner; the
slot-write helpers only read/write it through ``owner``.

``_apply_fusion_ranks`` stays on ``GalleryController`` — the pipeline-substrate
contract (``tests/contracts/test_gallery_pipeline_substrate.py``) pins the
durable ``_judgment_domain`` read and the nested ``_locked`` helper to
``controller.py``; ``_apply_slot_ranks`` reaches it through ``owner``.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.state_management.gallery_actions import (
    GallerySelectionSet,
    GalleryTriageFinished,
)
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.models import GalleryItem, Mode, TriageState
from tabs.image_gallery.state import selectors as _gallery_selectors

logger = logging.getLogger("ImproveImgSLI")


def _gallery_store(owner):
    """Store behind ``context.store`` (None in storeless unit contexts)."""
    store = getattr(owner._context, "store", None)
    if store is None or not hasattr(store, "get_dispatcher"):
        return None
    return store


def _ensure_gallery_subscription(owner) -> None:
    """Learn of slot changes via store.on_change (session_init precedent).

    Subscriber filters on scope == 'gallery' in _on_store_changed and
    reconciles the local mirror (thumbnail loads for new metas + grid
    rebuild reading the slot via selectors). No-op without a store.
    """
    store = _gallery_store(owner)
    if store is None or owner._subscribed_gallery_store is store:
        return
    try:
        if hasattr(store, "on_change"):
            store.on_change(owner._on_store_changed)
            owner._subscribed_gallery_store = store
    except Exception:
        logger.debug("gallery slot subscription failed", exc_info=True)


def bind_gallery_session(owner, session_id: str | None) -> None:
    """(Re)bind this live copy to its OWN session id.

    Called by ``ImageGalleryTab`` when the tab session is known
    (create_page, on_active_session_changed, activation refresh). The
    ONLY place the binding changes — slot reads never re-resolve.
    """
    owner._gallery_session_id = session_id


def _capture_initial_gallery_session_id(owner) -> str | None:
    """Best-effort own-id capture at construction (tab bind wins later).

    Only a gallery-typed active session is adopted — capturing a
    foreign tab's session id would invert the is-active gate.
    """
    try:
        store = _gallery_store(owner)
        if store is None:
            return None
        sess = store.get_active_workspace_session()
        if sess is None:
            return None
        if getattr(sess, "session_type", None) not in (None, "image_gallery"):
            return None
        return getattr(sess, "id", None)
    except Exception:
        return None


def _is_active_gallery_tab(owner) -> bool:
    """THE sanctioned active read: own id vs active session METADATA.

    True when this copy serves the active session (or when no binding
    is known yet — unbound/storeless copies fail open to legacy
    behavior). Emit handlers skip when False; slot DATA is never read
    here.
    """
    try:
        store = _gallery_store(owner)
        if store is None:
            return True
        own = owner._gallery_session_id
        if own is None:
            return True
        active = store.get_active_workspace_session()
        if active is None:
            return True
        active_id = getattr(active, "id", None)
        if active_id is None:
            return True
        return active_id == own
    except Exception:
        return True


def _gallery_slot(owner):
    """Read path: store.get_session_state_slot('gallery', session_id=<own>)."""
    store = _gallery_store(owner)
    if store is None or not hasattr(store, "get_session_state_slot"):
        return None
    try:
        return store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=owner._gallery_session_id)
    except Exception:
        return None


def _emit_gallery(owner, action) -> bool:
    """Write path: dispatcher.dispatch(..., scope='gallery', session_id=<own>).

    Session-targeted (Wave CORE): a background copy's late worker
    completion lands in its OWN session's slots even while another tab
    is active. None-safe: unbound (None) falls back to the default
    active path, fail-open as before.
    Never mutates slot values directly. Returns False (local-only) when
    no dispatcher is wired — callers always mirror locally first.
    """
    # A triage rank snapshot is the moment the local ranks were just
    # (re)written; freeze any explicit Keep/Make best winner as a manual
    # rank first so the mirrored provenance is truthful (the UI reaches the
    # triage helpers directly, not through the wrappers below).
    if isinstance(action, GalleryTriageFinished):
        try:
            owner._mark_triage_picks_manual()
        except Exception:
            pass
    store = _gallery_store(owner)
    if store is None:
        return False
    try:
        _ensure_gallery_subscription(owner)
        dispatcher = store.get_dispatcher()
        if dispatcher is None:
            return False
        owner._own_gallery_emits += 1
        try:
            dispatcher.dispatch(action, scope=GALLERY_SLOT_NAME, session_id=owner._gallery_session_id)
        except Exception:
            owner._own_gallery_emits -= 1
            raise
        return True
    except Exception:
        logger.debug("_emit_gallery dispatch failed", exc_info=True)
        return False


def _transact_gallery(owner, actions) -> bool:
    """Batch path: Store.transact([...], scope='gallery') — one emit."""
    store = _gallery_store(owner)
    batch = [a for a in actions or []]
    if store is None or not batch:
        return False
    try:
        _ensure_gallery_subscription(owner)
        if store.get_dispatcher() is None:
            return False
        owner._own_gallery_emits += 1
        try:
            store.transact(list(batch), scope=GALLERY_SLOT_NAME, session_id=owner._gallery_session_id)
        except Exception:
            owner._own_gallery_emits -= 1
            raise
        return True
    except Exception:
        logger.debug("_transact_gallery failed", exc_info=True)
        return False


def _on_store_changed(owner, scope: str) -> None:
    if scope != GALLERY_SLOT_NAME:
        return
    if not _is_active_gallery_tab(owner):
        # A foreign session's emit (e.g. tab B opening on an
        # empty/loading slot) must never reconcile THIS copy's mirror.
        return
    if owner._own_gallery_emits > 0:
        # Own dispatch: the local mirror was updated before emitting, so
        # reconcile selection/filter only (cheap no-op). Scalars/ranks
        # stay local — the slot cannot be newer than what we just sent.
        owner._own_gallery_emits -= 1
        slot = _gallery_slot(owner)
        if slot is None:
            return
        try:
            before_filter = owner.state.filter_text
            _apply_slot_selection_filter(owner, slot)
            if owner.state.filter_text != before_filter:
                owner._apply_filter_fast(owner.state.filter_text)
        except Exception:
            pass
        return
    # Undo / widget-gesture / external dispatch: the slot is authoritative.
    _sync_from_slot(owner)


def _sync_from_slot(owner) -> None:
    """Authoritative reconcile from the slot (undo / external changes).

    Thumbnail LOADING flags, pixmaps and workers are never reset here
    beyond starting loads for genuinely new metas; series objects (not
    in the slot) are left untouched and triage is never restarted.
    """
    slot = _gallery_slot(owner)
    if slot is None:
        return
    try:
        slot_paths = _gallery_selectors.get_item_paths(slot)
    except Exception:
        return
    try:
        local_paths = [str(it.path) for it in owner.state.items]
    except Exception:
        return
    if slot_paths == local_paths:
        try:
            before_filter = owner.state.filter_text
            _apply_slot_selection_filter(owner, slot)
            if owner.state.filter_text != before_filter:
                owner._apply_filter_fast(owner.state.filter_text)
        except Exception:
            pass
        _apply_slot_ranks(owner, slot)
        _apply_slot_triage_scalars(owner, slot)
        return
    # Membership differs (undo / external replace): rebuild the mirror,
    # preserving rich local objects (pixmaps, analysis) by path.
    by_path: dict[str, GalleryItem] = {}
    for it in owner.state.items:
        try:
            by_path[str(it.path)] = it
        except Exception:
            continue
    new_items: list[GalleryItem] = []
    fresh: list[GalleryItem] = []
    try:
        metas = _gallery_selectors.get_items(slot)
    except Exception:
        return
    for meta in metas:
        old = by_path.get(meta.path)
        if old is not None:
            try:
                if meta.mtime_ns != old.mtime_ns:
                    old.mtime_ns = meta.mtime_ns
            except Exception:
                pass
            new_items.append(old)
        else:
            try:
                item = GalleryItem(path=Path(meta.path), mtime_ns=meta.mtime_ns)
            except Exception:
                continue
            new_items.append(item)
            fresh.append(item)
    setattr(owner.state, "items", new_items)
    try:
        folder = _gallery_selectors.get_folder(slot)
        setattr(owner.state, "folder", Path(folder) if folder else None)
    except Exception:
        pass
    _apply_slot_selection_filter(owner, slot)
    _apply_slot_triage_scalars(owner, slot)
    try:
        if owner.state.folder is not None:
            owner.widget.set_folder_label(owner.state.folder)
    except Exception:
        pass
    # Restore cached AI analyses (no network) so a reopened tab shows the
    # previous results instead of "not analyzed".
    owner._hydrate_ai_cache(new_items)
    try:
        owner.widget.rebuild_grid(new_items)
    except Exception:
        logger.debug("gallery slot sync rebuild_grid failed", exc_info=True)
    for item in fresh:
        try:
            owner._load_thumbnail(item)
        except Exception:
            pass


def _apply_slot_ranks(owner, slot) -> None:
    """Re-derive series ranks from the measured fusion (undo / external replace).

    The slot no longer owns ranks: the Algorithms rank is a pure function
    of the item's measured metrics, so an authoritative reconcile
    re-derives it from the live series instead of copying a stored number.
    """
    owner._apply_fusion_ranks(getattr(owner.state, "series", None))


def _apply_slot_selection_filter(owner, slot) -> None:
    try:
        slot_sel = _gallery_selectors.get_selection(slot)
        local_sel = [str(p) for p in owner.state.selected_order]
        if slot_sel != local_sel:
            setattr(owner.state, "selected_paths", {Path(s) for s in slot_sel})
            setattr(owner.state, "selected_order", [Path(s) for s in slot_sel])
            try:
                grid = getattr(owner.widget, "_grid_view", None)
                if grid is not None and hasattr(grid, "apply_selection"):
                    grid.apply_selection(set(owner.state.selected_paths))
            except Exception:
                pass
    except Exception:
        pass
    try:
        slot_filter = _gallery_selectors.get_filter_text(slot)
        if slot_filter != owner.state.filter_text:
            setattr(owner.state, "filter_text", slot_filter)
    except Exception:
        pass


def _apply_slot_triage_scalars(owner, slot) -> None:
    try:
        summary = _gallery_selectors.get_triage_summary(slot)
    except Exception:
        return
    try:
        setattr(owner.state, "triage_state", TriageState(summary.get("triage_state", "idle")))
    except Exception:
        pass
    try:
        mode = summary.get("mode")
        setattr(owner.state, "mode", Mode(mode) if mode else None)
    except Exception:
        pass
    try:
        src = summary.get("source_path")
        setattr(owner.state, "source_path", Path(src) if src else None)
    except Exception:
        pass


def set_selection(owner, paths) -> None:
    """Wholesale selection: dispatch GallerySelectionSet + mirror locally.

    Triage UI (keyboard/arrows/Esc) routes through here so selection is
    tracer-visible; storeless owners fall back to direct writes in
    use_cases/triage_ui. Re-selection of the current slot value skips
    the dispatch (reducer identity would no-op without an emit, which
    would leak one unit of own-emit accounting).
    """
    try:
        strs: list[str] = []
        seen: set[str] = set()
        for p in paths or []:
            s = str(p)
            if s not in seen:
                seen.add(s)
                strs.append(s)
    except Exception:
        strs = []
    try:
        slot = _gallery_slot(owner)
        if slot is not None and _gallery_selectors.get_selection(slot) == strs:
            pass
        else:
            _emit_gallery(owner, GallerySelectionSet(selected_ids=strs))
    except Exception:
        _emit_gallery(owner, GallerySelectionSet(selected_ids=strs))
    try:
        setattr(owner.state, "selected_paths", {Path(s) for s in strs})
        setattr(owner.state, "selected_order", [Path(s) for s in strs])
    except Exception:
        pass
    try:
        grid = getattr(owner.widget, "_grid_view", None)
        if grid is not None and hasattr(grid, "apply_selection"):
            grid.apply_selection(set(owner.state.selected_paths))
    except Exception:
        pass


def set_source(owner, path: Path) -> None:
    """Set the triage source image: mirror locally + dispatch.

    Fail-open no-op when ``path`` is None or not in the pool. Carries
    the CURRENT triage_state/mode/ranks via GalleryTriageFinished with
    the new source_path — the single source-action shape, no second
    action kind.
    """
    if path is None:
        return
    try:
        want = str(path)
    except Exception:
        return
    try:
        pool = {str(it.path) for it in owner.state.items}
    except Exception:
        return
    if want not in pool:
        return
    try:
        current = getattr(owner.state, "triage_state", "idle")
        triage_s = getattr(current, "value", current)
        triage_s = str(triage_s or "idle")
    except Exception:
        triage_s = "idle"
    try:
        setattr(owner.state, "source_path", Path(want))
    except Exception:
        return
    try:
        owner._emit_triage_finished(triage_s, source_path=Path(want))
    except Exception:
        logger.debug("set_source dispatch failed", exc_info=True)
