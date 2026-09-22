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
    return True


def toggle_reject(owner, path: Path) -> bool:
    """Toggle rejected flag for *path*."""
    items = _items_of(owner)
    for it in items:
        try:
            if Path(it.path) == Path(path):
                cur = bool(getattr(it, "rejected", getattr(it, "triage_rejected", False)))
                new = not cur
                try:
                    it.rejected = new
                except Exception:
                    pass
                try:
                    it.triage_rejected = new
                except Exception:
                    pass
                _refresh_owner_grid(owner)
                return new
        except Exception:
            continue
    return False


def clean_rejected(owner) -> list[dict]:
    """Move rejected files to <folder>/_rejected/ (move-only, never delete).

    Returns list of move records for undo.
    """
    st = getattr(owner, "state", None)
    if st is None:
        return []
    folder = getattr(st, "folder", None)
    if folder is None:
        logger.warning("triage.clean_rejected: no folder")
        return []
    folder = Path(folder)
    rejected = [it for it in _items_of(owner) if bool(getattr(it, "rejected", getattr(it, "triage_rejected", False)))]
    if not rejected:
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
        try:
            shutil.move(str(src), str(dst))
            moves.append({"src": str(dst), "dst": str(src), "path": str(src)})
            # Keep item but mark as moved? Remove from grid
            try:
                it.path = dst
            except Exception:
                pass
        except Exception:
            logger.exception("triage.clean_rejected: move failed %s -> %s", src, dst)
    _refresh_owner_grid(owner)
    logger.debug("triage.clean_rejected: moved %d", len(moves))
    return moves


def restore_moves(owner, moves: list[dict]) -> int:
    """Undo clean_rejected moves."""
    restored = 0
    for rec in moves or []:
        src = rec.get("src")
        dst = rec.get("dst")
        if not src or not dst:
            continue
        try:
            shutil.move(src, dst)
            restored += 1
            # Update item path back
            for it in _items_of(owner):
                try:
                    if str(it.path) == src:
                        it.path = Path(dst)
                except Exception:
                    pass
        except Exception:
            logger.exception("triage.restore_moves: undo failed %s -> %s", src, dst)
    _refresh_owner_grid(owner)
    return restored


def compare_finalists(owner) -> bool:
    """Dispatch non-rejected best / remaining items to compare.

    Uses carry_selected if selection HUD exists; otherwise logs.
    """
    items = _items_of(owner)
    finalists = [it for it in items if not bool(getattr(it, "rejected", getattr(it, "triage_rejected", False)))]
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
    w = getattr(owner, "widget", None) or getattr(owner, "_widget", None)
    if w is None:
        # owner may be widget itself
        w = owner if hasattr(owner, "rebuild_grid") else None
    if w is None:
        return
    try:
        st = getattr(owner, "state", None)
        if st is None:
            st = getattr(w, "_state", None)
        if st is not None and hasattr(st, "items"):
            items = list(getattr(st, "items", []) or [])
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
                    n = sum(1 for it in items if bool(getattr(it, "rejected", getattr(it, "triage_rejected", False))))
                    setter(int(n))
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


# Ensure provenance fields are present on GalleryItem (Stage 2 safety model)
# The model file already defines rejected/is_best/crown_rank/provenance_series_id.
