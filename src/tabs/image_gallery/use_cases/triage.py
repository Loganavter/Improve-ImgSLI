"""Stage 2 triage helpers — keep best / clean rejected / compare finalists.
Audit-Meta: pattern=thin-owner size=exempt reason="thin owner helpers — keep_best/provenance/clean wiring shares one triage lifecycle"

Thin-owner helpers: plain functions taking the owner (controller or widget).
No implied lookups — owner and paths are passed explicitly.

These helpers work on the current GalleryItem flags (rejected, triage_best,
etc.) and are wired to StatsStrip signals. Series resolution goes through
the sole ``_series_of`` implementation below.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from core.state_management.gallery_actions import (
    GalleryItemsRemoved,
    GalleryPathsAppended,
    GalleryTriageFinished,
)
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME

# Toolkit usage per S3 spec: scaled_px + ThemeManager tokens (no QSS) — ensure
# provenance logic respects theme scaling where UI consumes it (clean_review).
# No direct ThemeManager.get_color calls (contracts forbid outside theme infra)
# — keep import for token awareness only, no runtime call.
try:
    from sli_ui_toolkit.managers import scaled_px as _scaled_px  # noqa: F401

    ThemeManager = None  # type: ignore  # placeholder for token palette (Button variants own visuals)
    scaled_px = _scaled_px  # type: ignore
except Exception:
    scaled_px = lambda x: int(x)  # type: ignore
    ThemeManager = None  # type: ignore

logger = logging.getLogger("ImproveImgSLI")


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


def ensure_provenance_series_ids(owner) -> int:
    """Fill ``provenance_series_id`` from ``series_id`` for all items.

    Called from ``clean_review`` before grouping and from triage helpers
    so S3 provenance ``SERIES N · hub (cnt)`` always has data. Returns
    number of items updated.
    """
    items = _items_of(owner)
    # Also try to derive from series objects if item has no series_id yet
    # but belongs to a Series members list.
    series = _series_of(owner)
    # Build path -> series_id map from series objects (covers freshly
    # clustered items where cluster_items already set series_id but
    # provenance may still be None).
    path_to_sid: dict[str, str] = {}
    for cl in series:
        # cl may be list[GalleryItem] or Series dataclass with .members/.id
        if hasattr(cl, "members"):
            sid = getattr(cl, "id", None)
            members = list(getattr(cl, "members", []) or [])
        elif isinstance(cl, (list, tuple)):
            # For plain list clusters, derive sid from first member's series_id
            members = list(cl)
            sid = getattr(members[0], "series_id", None) if members else None
        else:
            continue
        if sid is None:
            continue
        sid_s = str(sid)
        for m in members:
            try:
                path_to_sid[str(getattr(m, "path"))] = sid_s
            except Exception:
                continue
    updated = 0
    for it in items:
        cur = getattr(it, "provenance_series_id", None)
        if cur is not None:
            continue
        # Prefer existing series_id
        sid = getattr(it, "series_id", None)
        if sid is None:
            # Fallback via path map
            try:
                sid = path_to_sid.get(str(getattr(it, "path")))
            except Exception:
                sid = None
        if sid is not None:
            try:
                it.provenance_series_id = str(sid)  # type: ignore[attr-defined]
                updated += 1
            except Exception:
                pass
    # If still none and we have series, ensure series_id also sets provenance
    # for items that are in series but had stale None.
    return updated


def _sync_provenance_from_series(owner, series_list) -> None:
    """Wiring helper: after clustering, mirror series membership into
    ``provenance_series_id`` for every member (keep_best_provenance wiring).
    """
    if not series_list:
        return
    try:
        ensure_provenance_series_ids(owner)
    except Exception:
        pass
    # Also ensure state respects provenance for hub resolver.
    try:
        st = getattr(owner, "state", None)
        if st is not None and hasattr(st, "series"):
            # series_list may be list[Series]; keep as is
            pass
    except Exception:
        pass


def _series_of(owner) -> list[list]:
    """Resolve triage series clusters for *owner* (sole implementation).

    Attribute order: ``_triage_series``, ``triage_series``, ``_series``,
    ``series`` on the owner, then on ``owner.state``. Wave A owns this
    helper — no second copy may exist anywhere.
    """
    for attr in ("_triage_series", "triage_series", "_series", "series"):
        val = getattr(owner, attr, None)
        if val:
            return list(val)
        st = getattr(owner, "state", None)
        if st is not None:
            val = getattr(st, attr, None)
            if val:
                return list(val)
    return []


def keep_best(owner) -> int:
    """Mark best per series: first item of each cluster becomes best.

    Returns number of items marked best.
    """
    # Wire provenance before ranking (S3 provenance SERIES N).
    try:
        ensure_provenance_series_ids(owner)
    except Exception:
        pass
    series = _series_of(owner)
    if not series:
        # Fallback: mark nothing but log
        logger.debug("triage.keep_best: no series, nothing to mark")
        return 0
    count = 0
    for cluster in series:
        if not cluster:
            continue
        # Clear previous best in cluster
        for it in cluster:
            try:
                it.triage_best = False
                it.triage_rank = None
                # Also clear legacy is_best / crown_rank for badge parity
                it.is_best = False
                it.crown_rank = None
                it.rank = None
            except Exception:
                pass
        best = cluster[0]
        try:
            best.triage_best = True
            best.is_best = True
            best.triage_rank = 1
            best.crown_rank = 1
            best.rank = 1
            count += 1
            # Rank others
            for idx, other in enumerate(cluster[1:], start=2):
                other.triage_rank = idx
                other.crown_rank = idx
                other.rank = idx
                other.triage_best = False
                other.is_best = False
        except Exception:
            pass
    # Refresh grid if owner has widget
    _refresh_owner_grid(owner)
    try:
        _emit_rank_snapshot(owner)
    except Exception:
        pass
    logger.debug("triage.keep_best: marked %d best", count)
    return count


def make_best(owner, path: Path) -> bool:
    """Make *path* the best within its series."""
    items = _items_of(owner)
    series = _series_of(owner)
    target: Path = Path(path) if not isinstance(path, Path) else path
    # Find cluster containing path
    cluster: list | None = None
    for cl in series:
        try:
            if any(Path(it.path) == target for it in cl):
                cluster = cl
                break
        except Exception:
            continue
    if cluster is None:
        # Standalone item: just mark it best alone
        for it in items:
            try:
                if Path(it.path) == target:
                    it.triage_best = True
                    it.is_best = True
                    it.crown_rank = 1
                    it.triage_rank = 1
                    it.rank = 1
                    _refresh_owner_grid(owner)
                    try:
                        _emit_rank_snapshot(owner)
                    except Exception:
                        pass
                    return True
            except Exception:
                continue
        return False
    for it in cluster:
        try:
            is_target = Path(it.path) == target
            it.triage_best = bool(is_target)
            it.is_best = bool(is_target)
            # Winner invariant (same as keep_best and VLM crowning): rank,
            # crown_rank and triage_rank are all 1 for the winner, sequential
            # from 2 for the rest. Never leave rank None on a crowned item.
            it.crown_rank = 1 if is_target else None
            it.triage_rank = 1 if is_target else None
            it.rank = 1 if is_target else None
        except Exception:
            pass
    # Assign ranks: best =1, others = sequential
    rank = 2
    for it in cluster:
        try:
            if not bool(getattr(it, "triage_best", False)):
                it.triage_rank = rank
                it.crown_rank = rank
                it.rank = rank
                rank += 1
            else:
                it.triage_rank = 1
        except Exception:
            pass
    _refresh_owner_grid(owner)
    try:
        _emit_rank_snapshot(owner)
    except Exception:
        pass
    return True


def toggle_reject(owner, path: Path) -> bool:
    """Toggle rejected flag for *path*."""
    from tabs.image_gallery.debug import gallery_debug as _dbg

    items = _items_of(owner)
    _dbg(
        "toggle_reject ENTER path=%s owner=%s pool=%d",
        path,
        type(owner).__name__,
        len(items),
    )
    for it in items:
        try:
            if Path(it.path) == Path(path):
                cur = is_rejected(it)
                new = not cur
                try:
                    it.rejected = new
                except Exception:
                    pass
                try:
                    it.triage_rejected = new
                except Exception:
                    pass
                _dbg("toggle_reject applied path=%s rejected=%s", path, new)
                _refresh_owner_grid(owner)
                return new
        except Exception:
            continue
    _dbg("toggle_reject MISS path=%s pool_paths=%r", path, [str(getattr(it, "path", None)) for it in items[:5]])
    return False


def set_rejected_paths(owner, paths, rejected: bool) -> int:
    """Set the rejected flag on every path in *paths* (group Reject).

    Uniform direction (unlike per-item toggle): all targets end with
    ``rejected``. File on disk is untouched — only item flags. Single
    grid refresh. Returns the number of items updated.
    """
    try:
        targets = set()
        for p in list(paths or []):
            try:
                targets.add(Path(p) if not isinstance(p, Path) else p)
            except Exception:
                continue
    except Exception:
        return 0
    if not targets:
        return 0
    count = 0
    for it in _items_of(owner):
        try:
            if Path(it.path) in targets:
                try:
                    it.rejected = bool(rejected)
                except Exception:
                    pass
                try:
                    it.triage_rejected = bool(rejected)
                except Exception:
                    pass
                count += 1
        except Exception:
            continue
    if count:
        _refresh_owner_grid(owner)
    return count


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


def resolve_move_folder(owner, rejected: list | None = None) -> Path | None:
    """Folder whose ``_rejected/`` receives the move (single source of truth).

    State folder first; file-drop sessions carry no folder context, so fall
    back to the rejected items' common parent. None when neither resolves
    (the overlay subtitle shows the ``<folder>`` literal in that case).
    """
    try:
        folder = getattr(getattr(owner, "state", None), "folder", None)
    except Exception:
        folder = None
    if folder:
        try:
            return Path(folder)
        except Exception:
            pass
    try:
        parents = {
            str(Path(getattr(it, "path", None)).parent)
            for it in list(rejected or [])
            if getattr(it, "path", None)
        }
    except Exception:
        parents = set()
    if len(parents) == 1:
        try:
            return Path(next(iter(parents)))
        except Exception:
            return None
    return None


def clean_rejected(owner) -> list[dict]:
    """Move rejected files to <folder>/_rejected/ (move-only, never delete).

    Mirrors :func:`remove_paths_from_grid`: the moved items are dropped from
    the local pool (their ``path`` is never rewritten), selection/series are
    pruned, and ONLY ``GalleryItemsRemoved`` is emitted — the ``_rejected/``
    locations are NOT gallery members, so nothing re-renders them. The
    removed item objects ride on the move records so :func:`restore_moves`
    can put the cards back (files + cards). Returns list of move records
    for undo.
    """
    st = getattr(owner, "state", None)
    if st is None:
        return []
    rejected = [it for it in _items_of(owner) if is_rejected(it)]
    if not rejected:
        return []
    folder = resolve_move_folder(owner, rejected)
    if folder is None:
        logger.warning("triage.clean_rejected: no folder")
        return []
    target = folder / "_rejected"
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("triage.clean_rejected: mkdir failed %s", target)
        return []
    moves: list[dict] = []
    for it in rejected:
        src = Path(it.path)
        if not src.is_file():
            continue
        dst = target / src.name
        # Avoid overwrite: suffix with counter
        counter = 1
        base_dst = dst
        while dst.exists():
            dst = base_dst.with_name(f"{base_dst.stem}_{counter}{base_dst.suffix}")
            counter += 1
        # Remember the pool slot so Undo can re-insert in order.
        try:
            index = list(getattr(st, "items", []) or []).index(it)
        except Exception:
            index = None
        try:
            shutil.move(str(src), str(dst))
            moves.append(
                {
                    "src": str(dst),
                    "dst": str(src),
                    "path": str(src),
                    "item": it,
                    "index": index,
                }
            )
        except Exception:
            logger.exception("triage.clean_rejected: move failed %s -> %s", src, dst)
    if moves:
        # Drop the moved cards from the local pool (no path rewrite), prune
        # selection/series, then emit ONLY the removal — the _rejected/
        # locations are not gallery members (working-sibling parity with
        # remove_paths_from_grid).
        try:
            target_set = set()
            for m in moves:
                try:
                    target_set.add(Path(m["path"]))
                except Exception:
                    continue
            _detach_pool_items(owner, target_set)
            _emit_gallery(
                owner,
                GalleryItemsRemoved(paths=sorted({str(m["path"]) for m in moves})),
            )
        except Exception:
            logger.debug("triage.clean_rejected: pool removal failed", exc_info=True)
    _refresh_owner_grid(owner)
    logger.debug("triage.clean_rejected: moved %d", len(moves))
    return moves


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


def compare_finalists(owner) -> bool:
    """Dispatch non-rejected best / remaining items to compare.

    Uses carry_selected if selection HUD exists; otherwise logs.
    """
    items = _items_of(owner)
    finalists = [it for it in items if not is_rejected(it)]
    if not finalists:
        logger.debug("triage.compare_finalists: no finalists")
        return False
    # If series exists, take best per series + ungrouped
    series = _series_of(owner)
    if series:
        picks: list[Path] = []
        for cluster in series:
            best = next((x for x in cluster if bool(getattr(x, "triage_best", False))), None)
            if best is None and cluster:
                best = cluster[0]
            if best is not None:
                picks.append(Path(best.path))
        # Add ungrouped survivors not in picks
        member_paths = {str(p) for p in picks}
        ungrouped = [it for it in finalists if str(it.path) not in member_paths]
        picks.extend(Path(it.path) for it in ungrouped)
        paths = picks
    else:
        paths = [Path(it.path) for it in finalists]
    paths = [p for p in paths if p.is_file()][:12]  # cap
    if not paths:
        return False
    try:
        from tabs.image_gallery.use_cases.carry import _dispatch_via_image_carry

        ok = _dispatch_via_image_carry(paths)
        if ok:
            return True
    except Exception:
        pass
    # Fallback: log
    logger.debug("triage.compare_finalists: would compare %d files", len(paths))
    return False


def _refresh_owner_grid(owner) -> None:
    from tabs.image_gallery.debug import gallery_debug as _dbg

    w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
    if w is None:
        # owner may be widget itself
        w = owner if hasattr(owner, "rebuild_grid") else None
    if w is None:
        _dbg("_refresh_owner_grid NOWIDGET owner=%s", type(owner).__name__)
        return
    try:
        st = getattr(owner, "state", None)
        if st is None:
            st = getattr(w, "_state", None)
        if st is not None and hasattr(st, "items"):
            items = list(getattr(st, "items", []) or [])
            _dbg("_refresh_owner_grid n=%d widget=%s", len(items), type(w).__name__)
            if hasattr(w, "rebuild_grid"):
                w.rebuild_grid(items)
            # Notify card refresh for rejected/badge
            for it in items:
                if hasattr(w, "refresh_card"):
                    w.refresh_card(it)
            # P0-2 live "Clean rejected (n)": toggle_reject funnels through
            # here, so push the count to the strip on every refresh.
            # Existing StatsStrip.set_rejected_count(n) — signature unchanged.
            try:
                strip = getattr(w, "stats_strip", None)
                setter = getattr(strip, "set_rejected_count", None) if strip is not None else None
                if callable(setter):
                    n = sum(1 for it in items if is_rejected(it))
                    setter(int(n))
            except Exception:
                pass
            # Keep best ↔ Show all: when every series has exactly one
            # non-rejected left, the strip button flips to "Show all".
            try:
                strip = getattr(w, "stats_strip", None)
                mode_setter = getattr(strip, "set_keep_mode", None) if strip is not None else None
                if callable(mode_setter):
                    mode_setter("show" if is_keep_best_done(owner) else "keep")
            except Exception:
                pass
            # Re-run the action gate AFTER the mode flip. ``rebuild_grid``
            # above already ran it with the STALE mode ("keep"), where a
            # keep-best'd series has a single survivor -> the gate disabled the
            # button; the mode flip then relabelled it "Show all" while leaving
            # it disabled (the reported dead button).
            try:
                refresher = getattr(w, "_refresh_action_states", None)
                if callable(refresher):
                    refresher()
            except Exception:
                pass
    except Exception:
        pass


# -- Aliases for design.md spec (Stage 2 crown/reject/S3 flow) ----------

def keep_best_of_series(owner):  # type: ignore[no-untyped-def]
    """Keep best of each series, reject the rest (mockup spec ``gallery.keep-best-of-series``).

    Collects provenance per series (mirrors triage.keep_best_of_series spec).
    Returns provenance dict ``{series_id: {kept, rejected}}``. Also delegates
    to ``keep_best`` for rank/badge handling so existing logic stays.

    Wiring: ensures ``provenance_series_id`` is filled before grouping and
    stores result in ``owner._keep_best_provenance`` + ``owner.state.series``
    provenance sync for S3 hub resolver.
    """
    # Wire provenance first — ensure every item has provenance_series_id.
    try:
        ensure_provenance_series_ids(owner)
    except Exception:
        pass
    # Use the detailed provenance-aware logic first.
    # Try to group by provenance_series_id / series_id if available.
    try:
        from pathlib import Path as _Path  # local

        items = _items_of(owner)
        groups: dict[str | None, list] = {}
        for _it in items:
            _k = getattr(_it, "provenance_series_id", None) or getattr(_it, "series_id", None)
            _k = str(_k) if _k is not None else None
            groups.setdefault(_k, []).append(_it)

        provenance: dict[str, dict] = {}
        for _key, _members in groups.items():
            if _key is None or len(_members) < 2:
                continue
            # Determine keeper (existing is_best else first)
            _keeper = None
            for _m in _members:
                if bool(getattr(_m, "is_best", False) or getattr(_m, "triage_best", False)):
                    _keeper = _m
                    break
            if _keeper is None:
                _keeper = _members[0]
            # Mark keeper best, others rejected — winner invariant: rank,
            # crown_rank and triage_rank all 1 for the keeper (same as
            # make_best/keep_best/VLM crowning), sequential from 2 below.
            _rank = 2
            for _m in _members:
                try:
                    is_k = _m is _keeper
                    _m.is_best = bool(is_k)
                    _m.triage_best = bool(is_k)  # type: ignore[attr-defined]
                    if is_k:
                        _m.crown_rank = 1
                        _m.triage_rank = 1  # type: ignore[attr-defined]
                        _m.rank = 1
                        _m.rejected = False
                        try:
                            _m.triage_rejected = False  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    else:
                        _m.crown_rank = _rank
                        _m.triage_rank = _rank  # type: ignore[attr-defined]
                        _m.rank = _rank
                        _rank += 1
                        _m.rejected = True
                        try:
                            _m.triage_rejected = True  # type: ignore[attr-defined]
                        except Exception:
                            pass
                except Exception:
                    pass
            rejected_paths = [Path(_m.path) for _m in _members if _m is not _keeper]
            provenance[str(_key)] = {
                "kept": Path(_keeper.path),
                "rejected": rejected_paths,
                "series_id": str(_key),
            }
        try:
            owner._keep_best_provenance = provenance  # type: ignore[attr-defined]
        except Exception:
            pass
        # Keep-best provenance wiring: also mirror to state for hub resolver.
        try:
            st = getattr(owner, "state", None)
            if st is not None:
                st._keep_best_provenance = provenance  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            _sync_provenance_from_series(owner, _series_of(owner))
        except Exception:
            pass
        _refresh_owner_grid(owner)
        try:
            _emit_rank_snapshot(owner)
        except Exception:
            pass
        if provenance:
            return provenance
    except Exception:
        pass
    # Fallback to keep_best
    try:
        keep_best(owner)
    except Exception:
        pass
    # Ensure wiring even on fallback.
    try:
        ensure_provenance_series_ids(owner)
    except Exception:
        pass
    return {}


def is_rejected(it) -> bool:
    """Single rejected predicate — THE owner (cross-cutting policy B5).

    True when either ``rejected`` or ``triage_rejected`` is set. Both
    flags exist because ``GalleryItem`` only declares ``rejected`` while
    triage writers mirror into ``triage_rejected``; readers must never
    check just one (``getattr(it, "rejected", getattr(it,
    "triage_rejected", ...))`` silently drops a ``triage_rejected``-only
    item since ``rejected`` always exists). Every rejected read outside
    this module calls this function — never restates the predicate.
    Never raises.
    """
    try:
        return bool(
            getattr(it, "rejected", False) or getattr(it, "triage_rejected", False)
        )
    except Exception:
        return False


def _is_rejected(it) -> bool:
    """Legacy alias of :func:`is_rejected` (kept: callers reach in by name)."""
    return bool(is_rejected(it))


def should_show_all(items, groups) -> bool:
    """Pure predicate: every series (≥2 members) has exactly one survivor.

    *groups* are member lists (series clusters or series_id groupings).
    Returns True only when at least one group has ≥2 members, every such
    group keeps exactly one non-rejected item, and at least one item is
    rejected (i.e. ``keep_best`` output — not an untouched gallery).
    """
    series_groups = [list(g) for g in (groups or []) if len(list(g or [])) >= 2]
    if not series_groups:
        return False
    any_rejected = False
    for members in series_groups:
        survivors = 0
        for m in members:
            if _is_rejected(m):
                any_rejected = True
            else:
                survivors += 1
        if survivors != 1:
            return False
    return any_rejected


def _flat_series_groups(items) -> list[list]:
    """Group *items* by ``provenance_series_id``/``series_id`` (≥2 kept)."""
    groups: dict[str, list] = {}
    for it in items or []:
        try:
            key = getattr(it, "provenance_series_id", None) or getattr(it, "series_id", None)
        except Exception:
            key = None
        if key is None:
            continue
        groups.setdefault(str(key), []).append(it)
    return [members for members in groups.values() if len(members) >= 2]


def is_keep_best_done(owner) -> bool:
    """True when every series has exactly one non-rejected item left."""
    try:
        items = _items_of(owner)
    except Exception:
        items = []
    try:
        clusters = _series_of(owner)
    except Exception:
        clusters = []
    # Normalize clusters to member lists (Series dataclass or plain list).
    groups: list[list] = []
    for cl in clusters or []:
        try:
            if hasattr(cl, "members"):
                members = list(getattr(cl, "members", []) or [])
            elif isinstance(cl, (list, tuple)):
                members = list(cl)
            else:
                continue
            if len(members) >= 2:
                groups.append(members)
        except Exception:
            continue
    if not groups:
        # No cluster view (flat grid) — fall back to series_id grouping,
        # mirroring keep_best_of_series.
        try:
            groups = _flat_series_groups(items)
        except Exception:
            groups = []
    try:
        return bool(should_show_all(items, groups))
    except Exception:
        return False


def show_all(owner) -> int:
    """Clear all rejected flags (inverse of ``keep_best_of_series``).

    Returns number of items restored.
    """
    items = _items_of(owner)
    restored = 0
    for it in items:
        if not _is_rejected(it):
            continue
        try:
            it.rejected = False
        except Exception:
            pass
        try:
            it.triage_rejected = False  # type: ignore[attr-defined]
        except Exception:
            pass
        restored += 1
    _refresh_owner_grid(owner)
    try:
        _emit_rank_snapshot(owner)
    except Exception:
        pass
    logger.debug("triage.show_all: restored %d", restored)
    return restored


# Ensure provenance fields are present on GalleryItem (Stage 2 safety model)
# The model file already defines rejected/is_best/crown_rank/provenance_series_id.
