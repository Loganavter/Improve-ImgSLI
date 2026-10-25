"""Triage grid-removal / restore helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). Removing cards from the gallery mirror (Reject / Delete) and
re-inserting them on Undo.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.state_management.gallery_actions import (
    GalleryItemsRemoved,
    GalleryPathsAppended,
)
from core.log_names import APP_LOGGER_NAME

from .compare import _refresh_owner_grid
from .emit import _emit_gallery, _mtime_of, _resolve_state

logger = logging.getLogger(APP_LOGGER_NAME)


def remove_from_grid(owner, path: Path) -> bool:
    """Remove *path* from the gallery grid (Reject-button behavior).

    File on disk is untouched — only the grid mirror + slot membership
    change. Single-path wrapper over :func:`remove_paths_from_grid`.
    Returns True when a card was removed.
    """
    return remove_paths_from_grid(owner, [path]) > 0


def _detach_pool_items(owner, target_set) -> list:
    """Remove items whose path is in *target_set* from the local pool.

    Shared pool half of :func:`remove_paths_from_grid` and
    :func:`clean_rejected`: mutates ``state.items``, prunes
    ``selected_paths``/``selected_order`` and series clusters, and returns
    the removed item objects (so callers can stash them for Undo). No slot
    emit and no grid refresh — callers own those.
    """
    st = _resolve_state(owner)
    if st is None:
        return []
    removed: list = []
    try:
        kept = []
        for it in list(getattr(st, "items", []) or []):
            try:
                if Path(getattr(it, "path")) in target_set:
                    removed.append(it)
                    continue
            except Exception:
                pass
            kept.append(it)
        if not removed:
            return []
        try:
            st.items[:] = kept
        except Exception:
            try:
                st.items = kept
            except Exception:
                return []
    except Exception:
        return []
    # Prune selection / order.
    for attr in ("selected_paths", "selected_order"):
        try:
            cur = getattr(st, attr, None)
            if cur is None:
                continue
            if isinstance(cur, set):
                for cand in list(cur):
                    try:
                        if Path(cand) in target_set:
                            cur.discard(cand)
                    except Exception:
                        continue
            elif isinstance(cur, list):
                kept_sel = []
                for cand in cur:
                    try:
                        if Path(cand) in target_set:
                            continue
                    except Exception:
                        pass
                    kept_sel.append(cand)
                try:
                    cur[:] = kept_sel
                except Exception:
                    setattr(st, attr, kept_sel)
        except Exception:
            pass
    # Prune series clusters holding the same item objects (owner + state).
    for holder in (owner, st):
        for attr in ("_triage_series", "triage_series", "_series", "series"):
            try:
                clusters = getattr(holder, attr, None)
                if not clusters:
                    continue
                pruned_clusters = []
                changed = False
                for cl in list(clusters):
                    try:
                        if hasattr(cl, "members"):
                            members = [m for m in list(getattr(cl, "members", []) or []) if Path(getattr(m, "path")) not in target_set]
                            if len(members) != len(list(getattr(cl, "members", []) or [])):
                                changed = True
                                try:
                                    cl.members[:] = members
                                except Exception:
                                    try:
                                        cl.members = members
                                    except Exception:
                                        pass
                            pruned_clusters.append(cl)
                        elif isinstance(cl, (list, tuple)):
                            members = [m for m in list(cl) if Path(getattr(m, "path")) not in target_set]
                            if len(members) != len(list(cl)):
                                changed = True
                            if members:
                                pruned_clusters.append(members)
                            # Empty clusters drop out.
                        else:
                            pruned_clusters.append(cl)
                    except Exception:
                        try:
                            pruned_clusters.append(cl)
                        except Exception:
                            pass
                if changed:
                    try:
                        if isinstance(clusters, list):
                            clusters[:] = pruned_clusters
                        else:
                            setattr(holder, attr, pruned_clusters)
                    except Exception:
                        pass
            except Exception:
                pass
    return removed


def remove_paths_from_grid(owner, paths) -> int:
    """Remove every path in *paths* from the gallery grid in one batch.

    File on disk is untouched — only the grid mirror + slot membership
    change. Mirrors the controller write path: mutate the local
    ``state.items`` mirror first, prune selection/order + series clusters,
    emit a single ``GalleryItemsRemoved`` so the slot stays in sync, then
    refresh the grid once. Returns the number of cards removed.
    """
    from tabs.image_gallery.debug import gallery_debug as _dbg

    try:
        targets: list = []
        for p in list(paths or []):
            try:
                targets.append(Path(p) if not isinstance(p, Path) else p)
            except Exception:
                continue
    except Exception:
        return 0
    if not targets:
        return 0
    try:
        target_set = set(targets)
    except Exception:
        target_set = set()
        for t in targets:
            try:
                target_set.add(t)
            except Exception:
                continue
    _dbg(
        "remove_paths_from_grid ENTER n=%d owner=%s",
        len(targets),
        type(owner).__name__,
    )
    st = _resolve_state(owner)
    if st is None:
        _dbg("remove_paths_from_grid MISS-NOSTATE n=%d", len(targets))
        return 0
    try:
        before = len(list(getattr(st, "items", []) or []))
    except Exception:
        before = -1
    removed = _detach_pool_items(owner, target_set)
    if not removed:
        _dbg("remove_paths_from_grid MISS pool=%d", before)
        return 0
    doomed_s: set[str] = set()
    for it in removed:
        try:
            doomed_s.add(str(getattr(it, "path")))
        except Exception:
            continue
    try:
        _emit_gallery(owner, GalleryItemsRemoved(paths=sorted(doomed_s)))
    except Exception:
        pass
    try:
        remaining = len(list(getattr(st, "items", []) or []))
    except Exception:
        remaining = -1
    _dbg("remove_paths_from_grid applied n=%d pool=%d remaining=%d", len(doomed_s), before, remaining)
    _refresh_owner_grid(owner)
    return len(doomed_s)


def _reinsert_pool_item(owner, item, index=None) -> bool:
    """Put *item* back into ``state.items`` at (or near) *index* (Undo).

    No-op when the same object is already a member. Returns True on insert.
    """
    st = _resolve_state(owner)
    if st is None:
        return False
    try:
        items = list(getattr(st, "items", []) or [])
        if any(existing is item for existing in items):
            return False
        try:
            pos = int(index)
        except Exception:
            pos = len(items)
        pos = max(0, min(pos, len(items)))
        items.insert(pos, item)
        try:
            st.items[:] = items
        except Exception:
            st.items = items
        return True
    except Exception:
        return False


def restore_moves(owner, moves: list[dict]) -> int:
    """Undo clean_rejected moves (files + cards).

    Restores the files AND re-inserts the card objects ``clean_rejected``
    dropped from ``state.items`` (the only reason the old code kept them).
    """
    restored = 0
    restored_recs: list[dict] = []
    for rec in moves or []:
        src = rec.get("src")
        dst = rec.get("dst")
        if not src or not dst:
            continue
        try:
            shutil.move(src, dst)
            restored += 1
            restored_recs.append(rec)
            # Re-insert the stashed card. The item path was never rewritten
            # by clean_rejected, so only pool membership returns.
            item = rec.get("item")
            if item is not None:
                _reinsert_pool_item(owner, item, rec.get("index"))
        except Exception:
            logger.exception("triage.restore_moves: undo failed %s -> %s", src, dst)
    # Mirror the undo through the slot: re-append the restored originals.
    # Their removal was the only slot change clean_rejected made; the
    # _rejected/ locations were never slot members.
    if restored_recs:
        try:
            _emit_gallery(
                owner,
                GalleryPathsAppended(
                    entries=[(r["dst"], _mtime_of(r["dst"])) for r in restored_recs]
                ),
            )
        except Exception:
            logger.debug("triage.restore_moves: slot append failed", exc_info=True)
    _refresh_owner_grid(owner)
    return restored
