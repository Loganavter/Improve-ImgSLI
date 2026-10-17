"""Stage-2 crown/reject/manual-rank actions for the Image Gallery controller (Wave 5).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the controller-side crown/reject wrappers (make-best /
keep-best-of-series / remove-from-grid / show-all), the manual-rank provenance
seam that freezes explicit triage winners, and the per-path item lookup those
wrappers use. The underlying crown / removal bodies stay in the
``use_cases/triage`` package; these wrappers add the owner-level tail — marking
the explicit picks manual and re-deriving the fusion ranks around them, so a
later automatic regroup never silently re-derives a user's decision. The owner
keeps thin delegators with the method names verbatim.

Audit-Meta: pattern=thin-owner-target size=exempt reason="crown/reject wrappers — owner-level manual-rank tail around the triage package bodies"
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger("ImproveImgSLI")


def _mark_triage_picks_manual(owner) -> int:
    """Freeze explicit triage winners (``triage_best``) as manual ranks.

    Keep best / Make best mark their winners ``triage_best``; those are the
    user's explicit decisions. The gallery UI reaches the triage helpers
    directly (not through ``make_best``/``keep_best_of_series``), so this is
    the seam that keeps the badge provenance truthful in production: it is
    invoked right before a rank snapshot is mirrored. Returns items flagged.
    """
    try:
        items = list(getattr(owner.state, "items", None) or ())
    except Exception:
        items = []
    picked = [it for it in items if bool(getattr(it, "triage_best", False))]
    return owner._mark_rank_manual(picked)


def _mark_rank_manual(owner, items) -> int:
    """Flag the ranks of *items* as explicit USER decisions.

    ``rank_source = "manual"`` so a later automatic regroup never silently
    re-derives them (``_apply_fusion_ranks`` leaves manual ranks alone).
    Only items that actually carry a rank are flagged — an unranked item
    has no manual decision to protect. Returns the number flagged.
    """
    count = 0
    for m in list(items or ()):
        if getattr(m, "rank", None) is None:
            continue
        try:
            m.rank_source = "manual"  # type: ignore[attr-defined]
            count += 1
        except Exception:
            pass
    return count


def _item_for_path(owner, path):
    try:
        target = path if isinstance(path, Path) else Path(path)
    except Exception:
        return None
    try:
        items = list(getattr(owner.state, "items", None) or ())
    except Exception:
        items = []
    for it in items:
        try:
            if Path(getattr(it, "path", None)) == target:
                return it
        except Exception:
            continue
    return None


def make_best(owner, path: Path) -> bool:
    from tabs.image_gallery.use_cases.triage import make_best as _make_best

    ok = bool(_make_best(owner, path))
    if ok:
        # The explicit pick is manual; the remaining members are re-derived
        # from the fusion around the anchored manual rank.
        owner._mark_rank_manual([owner._item_for_path(path)])
        owner._apply_fusion_ranks(getattr(owner.state, "series", None))
        try:
            from tabs.image_gallery.use_cases.triage import (
                _refresh_owner_grid as _refresh,
            )

            _refresh(owner)
        except Exception:
            pass
    return ok


def toggle_reject(owner, path: Path) -> bool:
    from tabs.image_gallery.use_cases.triage import toggle_reject as _toggle

    return bool(_toggle(owner, path))


def remove_from_grid(owner, path: Path) -> bool:
    from tabs.image_gallery.use_cases.triage import remove_from_grid as _remove

    return bool(_remove(owner, path))


def remove_paths_from_grid(owner, paths) -> int:
    from tabs.image_gallery.use_cases.triage import remove_paths_from_grid as _remove_many

    return int(_remove_many(owner, paths))


def keep_best_of_series(owner) -> dict:
    from tabs.image_gallery.use_cases.triage import keep_best_of_series as _keep

    result = _keep(owner)
    # Every keeper (explicit per-series user decision) is manual; the rest
    # is re-derived from the fusion around the anchored winners.
    try:
        items = list(getattr(owner.state, "items", None) or ())
    except Exception:
        items = []
    keepers = [it for it in items if bool(getattr(it, "is_best", False))]
    owner._mark_rank_manual(keepers)
    owner._apply_fusion_ranks(getattr(owner.state, "series", None))
    try:
        from tabs.image_gallery.use_cases.triage import (
            _refresh_owner_grid as _refresh,
        )

        _refresh(owner)
    except Exception:
        pass
    return result


def show_all(owner) -> int:
    from tabs.image_gallery.use_cases.triage import show_all as _show

    return int(_show(owner))
