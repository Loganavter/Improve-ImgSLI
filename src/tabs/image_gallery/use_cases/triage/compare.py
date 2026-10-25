"""Triage compare / show-all helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). The rejected predicate (cross-cutting policy B5) is the single owner
here, plus compare-finalists dispatch and the keep-best ↔ show-all mode gate.

``keep_best_of_series`` imports ``keep_best`` lazily: ``crown`` imports
``_refresh_owner_grid`` from this module at load time, so the reverse edge is
deferred to call time to keep the package importable.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .emit import _emit_rank_snapshot, _items_of
from .provenance import (
    _series_of,
    _sync_provenance_from_series,
    ensure_provenance_series_ids,
)
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


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
    # Fallback to keep_best (local import breaks the crown<->compare cycle).
    try:
        from .crown import keep_best

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
