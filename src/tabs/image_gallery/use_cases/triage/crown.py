"""Triage crown / reject helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). Keep-best / make-best crowning plus the reject-flag writers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .compare import _refresh_owner_grid, is_rejected
from .emit import _emit_rank_snapshot, _items_of
from .provenance import _series_of, ensure_provenance_series_ids

logger = logging.getLogger("ImproveImgSLI")


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
