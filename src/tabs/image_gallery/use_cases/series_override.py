"""Manual series overrides — pure post-pass over clustering results.

Thin-owner helpers: plain functions taking an explicit
``overrides: dict[str, str | None]`` map plus item lists. The map itself is
owned by ``GalleryController`` (``controller._series_overrides``, in-memory
only — no cross-restart persistence); this module never looks an owner up
and never touches the store (ownership-guard clean: no Qt, no ``.state``
writes — only ``GalleryItem.series_id``/``rank`` fixups, the same fields
``services.clustering.cluster_items`` already mutates).

Semantics (frozen Wave A/B seam):

* override value = series id string → item is pinned to that series;
* override value ``None`` = forced UNGROUPED → item is excluded from every
  cluster even when its content matches;
* absent key = auto → computed ``series_id`` stands.
* ``apply_overrides`` runs immediately after EVERY ``cluster_items`` result
  (override wins over the computed ``series_id``).

``apply_overrides`` returns a corrected ``list[Series]`` (reusing the
computed ``Series`` objects whose membership did not change, so downstream
view code can keep them as-is) because flipping ``series_id`` alone would
leave the computed ``Series.members`` lists stale: overridden items are
re-grouped by final ``series_id``, groups that fall below 2 members
dissolve to UNGROUPED, and ranks are recomputed positionally inside
regrouped clusters only (untouched clusters keep their centroid ranks, so
hub/crown order never churns when an unrelated override exists).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.image_gallery.models import GalleryItem, Series


def _key(path) -> str:
    try:
        return str(path)
    except Exception:
        return ""


def get_override(overrides: dict, path) -> str | None:
    """Return the stored override for *path* (series id, or None).

    Returns None both when no override exists (auto) and when the item is
    forced UNGROUPED — use ``_key(path) in overrides`` membership (or the
    ``apply_overrides`` outcome) to tell the two apart.
    """
    try:
        return overrides.get(_key(path))
    except Exception:
        return None


def set_override(overrides: dict, paths, series_id: str | None) -> int:
    """Pin every path in *paths* to *series_id* (None = forced UNGROUPED).

    Returns the number of entries written.
    """
    count = 0
    try:
        sid = str(series_id) if series_id is not None else None
    except Exception:
        sid = None
    try:
        targets = list(paths or [])
    except Exception:
        return 0
    for p in targets:
        try:
            overrides[_key(p)] = sid
            count += 1
        except Exception:
            continue
    return count


def clear_override(overrides: dict, paths) -> int:
    """Drop overrides for *paths* (items return to auto on re-cluster).

    Returns the number of entries removed.
    """
    count = 0
    try:
        targets = list(paths or [])
    except Exception:
        return 0
    for p in targets:
        try:
            if _key(p) in overrides:
                del overrides[_key(p)]
                count += 1
        except Exception:
            continue
    return count


def _series_members(entry):
    """Normalize one computed cluster to a member list (Series or list)."""
    try:
        if hasattr(entry, "members"):
            return list(getattr(entry, "members", None) or [])
        if isinstance(entry, (list, tuple)):
            return list(entry)
    except Exception:
        pass
    return []


def apply_overrides(items: list, overrides: dict, series=None) -> list:
    """Apply *overrides* onto *items* + the computed *series* clusters.

    *series* is the ``cluster_items`` result (``list[Series]`` or member
    lists; None/empty tolerated). Every item whose path is in *overrides*
    gets ``series_id`` = the override (None for forced UNGROUPED);
    computed ids stand otherwise. Final groups (by ``series_id``) with ≥2
    members become the returned clusters; smaller groups dissolve (members
    get ``series_id``/``rank`` None). Unchanged computed ``Series`` objects
    are reused verbatim (ranks kept); regrouped clusters are fresh
    ``Series`` objects with positional ranks and a member-count-weighted
    centroid blend (None when no source centroid exists).

    Returns the corrected cluster list.
    """
    from tabs.image_gallery.models import Series as _Series

    try:
        item_list = list(items or [])
    except Exception:
        return []
    try:
        overrides_map = dict(overrides or {})
    except Exception:
        overrides_map = {}

    # 1. Per-item override wins (computed ids stand otherwise).
    for it in item_list:
        try:
            k = _key(getattr(it, "path", None))
        except Exception:
            continue
        if k in overrides_map:
            try:
                it.series_id = overrides_map[k]
            except Exception:
                pass
            if overrides_map[k] is None:
                try:
                    it.rank = None
                except Exception:
                    pass

    # 2. Regroup by final series_id (None → UNGROUPED, excluded).
    groups: dict[str, list] = {}
    order: list[str] = []
    for it in item_list:
        try:
            sid = getattr(it, "series_id", None)
        except Exception:
            sid = None
        if sid is None:
            continue
        try:
            sid_s = str(sid)
        except Exception:
            continue
        if sid_s not in groups:
            groups[sid_s] = []
            order.append(sid_s)
        groups[sid_s].append(it)

    # Index computed Series by id for reuse.
    computed_by_id: dict[str, object] = {}
    try:
        for entry in list(series or []):
            members = _series_members(entry)
            if not members:
                continue
            try:
                cid = getattr(entry, "id", None)
            except Exception:
                cid = None
            if cid is None:
                try:
                    cid = getattr(members[0], "series_id", None)
                except Exception:
                    cid = None
            if cid is not None:
                try:
                    computed_by_id[str(cid)] = entry
                except Exception:
                    pass
    except Exception:
        pass

    out: list = []
    for sid_s in order:
        members = groups[sid_s]
        if len(members) < 2:
            # Dissolved: manual singletons join UNGROUPED (rank cleared).
            for m in members:
                try:
                    m.series_id = None
                except Exception:
                    pass
                try:
                    m.rank = None
                except Exception:
                    pass
            continue
        # Reuse the computed Series object when membership is identical
        # (same objects) — ranks/centroid stay exactly as clustered.
        try:
            prev = computed_by_id.get(sid_s)
            prev_members = _series_members(prev) if prev is not None else []
            prev_ids = {id(m) for m in prev_members}
            same = prev is not None and prev_ids == {id(m) for m in members}
        except Exception:
            same = False
        if same:
            out.append(prev)
            continue
        # Regrouped: positional ranks + blended centroid.
        for rank, m in enumerate(members, start=1):
            try:
                m.rank = rank
            except Exception:
                pass
        centroid = _blend_centroid(members, computed_by_id)
        phash_centroid = _blend_phash(members)
        try:
            out.append(_Series(id=sid_s, members=list(members), centroid=centroid, phash_centroid=phash_centroid))
        except Exception:
            out.append(list(members))

    # 3. UNGROUPED fixup: every item without a surviving group is bare.
    try:
        grouped_ids = {id(m) for cl in out for m in _series_members(cl)}
    except Exception:
        grouped_ids = set()
    for it in item_list:
        try:
            if id(it) not in grouped_ids:
                it.series_id = None
                it.rank = None
        except Exception:
            continue

    # Stable order: size desc, then id (mirrors cluster_items).
    try:
        out.sort(key=lambda s: (-len(_series_members(s)), str(getattr(s, "id", ""))))
    except Exception:
        pass
    return out


def _blend_centroid(members: list, computed_by_id: dict) -> list[float] | None:
    """Member-count-weighted mean of source clusters' centroids (no I/O)."""
    try:
        # Attribute each member to its computed source cluster (pre-override
        # snapshot is gone here; use current computed_by_id membership).
        buckets: dict[int, tuple] = {}  # id(source) -> (centroid, count)
        for m in members:
            for src in computed_by_id.values():
                try:
                    src_members = _series_members(src)
                except Exception:
                    continue
                if any(m is sm for sm in src_members):
                    try:
                        c = getattr(src, "centroid", None)
                    except Exception:
                        c = None
                    if c:
                        key = id(src)
                        prev_c, prev_n = buckets.get(key, (None, 0))
                        buckets[key] = (c if prev_c is None else prev_c, prev_n + 1)
                    break
        total = sum(n for _, n in buckets.values())
        if not total:
            return None
        dim = 0
        for c, _ in buckets.values():
            try:
                dim = max(dim, len(c))
            except Exception:
                pass
        if not dim:
            return None
        acc = [0.0] * dim
        for c, n in buckets.values():
            try:
                for i, v in enumerate(c[:dim]):
                    acc[i] += float(v) * n
            except Exception:
                continue
        return [v / total for v in acc]
    except Exception:
        return None


def _blend_phash(members: list) -> int | None:
    """Medoid phash of regrouped members (pure int math, no I/O)."""
    try:
        hashes: list[int] = []
        for m in members:
            try:
                h = (getattr(m, "metrics", None) or {}).get("phash")
            except Exception:
                h = None
            if isinstance(h, int) and h:
                hashes.append(h)
        if not hashes:
            return None
        best = hashes[0]
        best_sum: int | None = None
        for h in hashes:
            s = sum(bin(h ^ o).count("1") for o in hashes if o != h)
            if best_sum is None or s < best_sum:
                best_sum = s
                best = h
        return best
    except Exception:
        return None
