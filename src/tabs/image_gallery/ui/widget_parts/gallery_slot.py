"""Redux subscription + render-from-slot for the gallery widget (plan Part B, Wave 1).

Bodies extracted from ``ImageGalleryWidget`` per ``CODE_PATTERNS.md``
(thin owner + functions-taking-owner); the widget keeps same-named
one-line delegators. All functions are fail-open like the surrounding
slot bridge — no store / unbootstrapped tab means no subscription and no
render, never an exception.
"""

from __future__ import annotations

from pathlib import Path

from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.models import GalleryItem


def _on_filter_text_dispatch(owner, text: str) -> None:
    """Dispatch ``GalleryFilterSet`` for a filter gesture (fail-open)."""
    try:
        from core.state_management.gallery_actions import GalleryFilterSet
        from tabs.image_gallery.ui.gallery_store import dispatch_gallery

        dispatch_gallery(owner, GalleryFilterSet(filter_text=text or ""))
    except Exception:
        pass


def _init_gallery_store_subscription(owner) -> None:
    """Render grid/selection/filter from the ``gallery`` slot on emit."""
    try:
        from tabs.image_gallery.ui.gallery_store import resolve_store

        store = resolve_store(owner)
    except Exception:
        return
    if store is None:
        return
    try:
        qt_signal = getattr(store, "state_changed", None)
        if qt_signal is not None and hasattr(qt_signal, "connect"):
            qt_signal.connect(owner._on_gallery_store_changed)
            owner._gallery_store_connected = True
            return
    except Exception:
        pass
    try:
        if hasattr(store, "on_change"):
            store.on_change(owner._on_gallery_store_changed)
            owner._gallery_store_connected = True
    except Exception:
        pass


def bind_gallery_session(owner, session_id: str | None) -> None:
    """(Re)bind this live copy to its OWN session id.

    Called by ``ImageGalleryTab`` when the tab session is known
    (create_page, on_active_session_changed, activation refresh). The
    ONLY place the binding changes — slot reads never re-resolve.
    """
    owner._gallery_session_id = session_id


def _is_active_gallery_tab(owner) -> bool:
    """THE sanctioned active read: own id vs active session METADATA.

    True when this copy serves the active session (or when no binding
    is known yet — unbound copies fail open to legacy behavior).
    """
    try:
        from tabs.image_gallery.ui.gallery_store import (
            resolve_owner_session_id,
            resolve_store,
        )

        own = owner._gallery_session_id
        if own is None:
            own = resolve_owner_session_id(owner)
        if own is None:
            return True
        store = resolve_store(owner)
        if store is None:
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


def _on_gallery_store_changed(owner, scope: str) -> None:
    try:
        if scope != "gallery":
            return
    except Exception:
        return
    if not owner._is_active_gallery_tab():
        # A foreign session's emit must never re-render THIS copy
        # from the foreign slot (the empty-slot window wipes views).
        return
    try:
        owner._render_from_gallery_slot()
    except Exception:
        pass


def _render_from_gallery_slot(owner) -> None:
    """Re-render selection/filter/folder/pool from slot reads (no dispatch)."""
    try:
        from tabs.image_gallery.ui.gallery_store import read_gallery_slot

        slot = read_gallery_slot(owner)
    except Exception:
        return
    if slot is None:
        # No Redux state (foreign session, pre-first-dispatch) — never clear.
        return
    try:
        from tabs.image_gallery.state import selectors as _sel2

        owner._render_gallery_selection(_sel2.get_selection(slot))
        owner._render_gallery_filter(_sel2.get_filter_text(slot))
        owner._render_gallery_folder(_sel2.get_folder(slot))
        owner._render_gallery_pool(slot)
    except Exception:
        pass


def _render_gallery_selection(owner, selected_ids: list) -> None:
    """Apply slot selection to grid (visuals only, no dispatch)."""
    try:
        wanted = set(str(s) for s in (selected_ids or []))
    except Exception:
        return
    try:
        current = set()
        for p in (owner._grid_view._selection or set()):
            current.add(str(p))
    except Exception:
        current = set()
    if wanted == current:
        pass
    try:
        owner._grid_view.apply_selection(set(wanted))
    except Exception:
        pass


def _render_gallery_filter(owner, filter_text: str) -> None:
    """Sync the filter edit from the slot (signal-blocked, no loop)."""
    try:
        want = str(filter_text or "")
    except Exception:
        return
    try:
        edit = getattr(owner.toolbar, "_filter_edit", None) or getattr(owner, "_filter_edit", None)
        if edit is None:
            return
        try:
            cur = str(edit.text())
        except Exception:
            return
        if cur == want:
            return
        try:
            edit.blockSignals(True)
            edit.setText(want)
        finally:
            try:
                edit.blockSignals(False)
            except Exception:
                pass
    except Exception:
        pass


def _render_gallery_folder(owner, folder: str | None) -> None:
    """Sync the compat folder label from the slot (folder set only)."""
    if not folder:
        return
    try:
        label = getattr(owner, "_folder_label", None)
        if label is None:
            return
        try:
            cur = str(label.text())
        except Exception:
            cur = ""
        if cur != str(folder):
            label.setText(str(folder))
    except Exception:
        pass


def _render_gallery_pool(owner, slot) -> None:
    """Reconcile flat-grid membership with the slot pool (no dispatch).

    Skipped while a triage series view is active — grouping is owned by
    the controller triage reaction (W2b). New paths materialize as bare
    ``GalleryItem``\\ s WITHOUT pixmaps: thumbnail fetch for
    slot-materialized items is a missing controller reaction (see
    DONE.md) — during transition the legacy ``ctrl.open_*`` call that
    follows each gesture loads thumbnails right after this reconcile.
    """
    try:
        if getattr(owner, "_series", None):
            return
        from tabs.image_gallery.state import selectors as _selectors

        slot_paths = [str(p) for p in _selectors.get_item_paths(slot)]
    except Exception:
        return
    try:
        cur_paths = [str(it.path) for it in (owner._items or [])]
    except Exception:
        return
    if slot_paths == cur_paths:
        return
    _dbg("_render_gallery_pool reconcile slot=%d local=%d", len(slot_paths), len(cur_paths))
    try:
        from tabs.image_gallery.state import selectors as _sel3

        metas = {m.path: m for m in _sel3.get_items(slot)}
    except Exception:
        metas = {}
    try:
        by_path = {}
        for it in (owner._items or []):
            try:
                by_path[str(it.path)] = it
            except Exception:
                continue
        merged: list = []
        for sp in slot_paths:
            it = by_path.get(sp)
            if it is None:
                try:
                    meta = metas.get(sp)
                    mtime = int(getattr(meta, "mtime_ns", 0) or 0)
                except Exception:
                    mtime = 0
                try:
                    it = GalleryItem(path=Path(sp), mtime_ns=mtime)
                except Exception:
                    continue
            merged.append(it)
        owner.rebuild_grid(merged)
    except Exception:
        pass
