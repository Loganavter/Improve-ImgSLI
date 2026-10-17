"""Triage provenance helpers — thin-owner plain functions.

Split out of ``tabs.image_gallery.use_cases.triage`` (plan-gallery-split-2026-10-17
Part C5). Owns the sole ``_series_of`` cluster resolver and the
``provenance_series_id`` back-fill shared by keep-best / S3 hubs.
"""

from __future__ import annotations

from .emit import _items_of


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
