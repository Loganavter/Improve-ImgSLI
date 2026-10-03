"""Manual series overrides — pure post-pass over clustering results.
Audit-Meta: pattern=single-seam size=exempt reason="one override/translate/regroup/attach seam — splitting across modules would create a second implementation of the same seam (orchestrator interface rule)"

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


def _regroup_core(item_list: list, overrides_map: dict, prev_entries, keep_singletons: bool) -> list:
    """Shared regroup engine: override wins → group by id → fixup → sort.

    ``keep_singletons=False`` is the legacy ``apply_overrides`` rule
    (groups <2 dissolve to UNGROUPED); ``True`` is the Wave S1 0-close
    rule (1-member groups stay visible). Pure apart from the
    ``series_id``/``rank`` fixups on member items.
    """
    from tabs.image_gallery.models import Series as _Series

    # 1. Per-item override wins (other ids stand).
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

    # Index previous Series by id for reuse.
    prev_by_id: dict[str, object] = {}
    try:
        for entry in list(prev_entries or []):
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
                    prev_by_id[str(cid)] = entry
                except Exception:
                    pass
    except Exception:
        pass

    out: list = []
    for sid_s in order:
        members = groups[sid_s]
        if len(members) < 2 and not keep_singletons:
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
        # Reuse the previous Series object when membership is identical
        # (same objects) — ranks/centroid stay exactly as they were.
        try:
            prev = prev_by_id.get(sid_s)
            prev_members = _series_members(prev) if prev is not None else []
            prev_ids = {id(m) for m in prev_members}
            same = prev is not None and prev_ids == {id(m) for m in members}
        except Exception:
            same = False
        if same:
            out.append(prev)
            continue
        # Regrouped (0-close: incl. 1-member survivors): positional ranks.
        for rank, m in enumerate(members, start=1):
            try:
                m.rank = rank
            except Exception:
                pass
        centroid = _blend_centroid(members, prev_by_id)
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
    try:
        item_list = list(items or [])
    except Exception:
        return []
    try:
        overrides_map = dict(overrides or {})
    except Exception:
        overrides_map = {}
    return _regroup_core(item_list, overrides_map, series, keep_singletons=False)


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


# -- Wave S1 stable-id seam (pure, no Qt/store) ------------------------------
#
# ``Series.id`` is STABLE within the session: monotonic ``series_<n>``,
# never reused. The controller owns the counter (S2 wires it); the
# functions below take it as an explicit arg and never look an owner up.
# ``cluster_items`` output ids are SEED-ONLY: never compared, stored, or
# shown after translation.


def translate_computed_to_stable(computed_series, start_counter: int, skip_ids=None) -> tuple:
    """Rename seed ids from ``cluster_items`` to stable ``series_<n>`` ids.

    Fresh world, no matching needed: every entry in *computed_series*
    (``Series`` or member list) gets the next monotonic id
    ``series_<start_counter+1>`` … and its members' ``series_id`` is
    rewritten to match. Member order, ranks, centroids and
    ``phash_centroid`` are carried over verbatim; output order mirrors
    ``cluster_items`` (size desc, then id).

    *skip_ids* (optional set of id strings, e.g. live pinned sections):
    issued ids colliding with it are skipped — a fresh auto group must
    never merge into a pinned manual section. Skips still consume counter
    values (monotonic, never reused, gaps allowed).

    Returns ``(stable_series, next_counter)`` where ``next_counter`` is
    the last id number issued (pass it back as ``start_counter`` next
    time so ids are never reused). Pure apart from the ``series_id``
    fixup on member items — the same fields ``cluster_items`` mutates.
    """
    from tabs.image_gallery.models import Series as _Series

    try:
        entries = list(computed_series or [])
    except Exception:
        return ([], int(start_counter) if isinstance(start_counter, int) else 0)
    try:
        counter = int(start_counter)
    except Exception:
        counter = 0
    try:
        skip = {str(s) for s in (skip_ids or set())}
    except Exception:
        skip = set()

    out: list = []
    for entry in entries:
        members = _series_members(entry)
        if not members:
            continue
        counter += 1
        sid_s = f"series_{counter}"
        while sid_s in skip:
            counter += 1
            sid_s = f"series_{counter}"
        for m in members:
            try:
                m.series_id = sid_s
            except Exception:
                pass
        try:
            centroid = getattr(entry, "centroid", None)
        except Exception:
            centroid = None
        try:
            phash_centroid = getattr(entry, "phash_centroid", None)
        except Exception:
            phash_centroid = None
        try:
            out.append(
                _Series(
                    id=sid_s,
                    members=list(members),
                    centroid=list(centroid) if centroid else None,
                    phash_centroid=phash_centroid,
                )
            )
        except Exception:
            out.append(list(members))
    try:
        out.sort(key=lambda s: (-len(_series_members(s)), str(getattr(s, "id", ""))))
    except Exception:
        pass
    return (out, counter)


def regroup_items(items: list, overrides: dict, last_series=None) -> list:
    """Pure regroup WITHOUT clustering: override wins, group by final id.

    Steps 2-3 of ``apply_overrides`` with the ``<2 dissolve`` replaced by
    **0-close**: 1-member manual sections STAY visible (positional rank 1,
    id kept); zero-member groups simply never appear; the UNGROUPED fixup
    (every item outside a surviving group is bare) is unchanged.

    Items whose path is absent from *overrides* keep their current
    ``series_id`` (no re-cluster here — fresh clustering goes through
    ``translate_computed_to_stable`` first). ``None`` overrides force
    UNGROUPED. Unchanged groups reuse the ``last_series`` object verbatim
    (ranks/centroid kept); regrouped groups are fresh ``Series`` with
    positional ranks and a member-count-weighted centroid blend.

    Returns the regrouped cluster list.
    """
    try:
        item_list = list(items or [])
    except Exception:
        return []
    try:
        overrides_map = dict(overrides or {})
    except Exception:
        overrides_map = {}
    return _regroup_core(item_list, overrides_map, last_series, keep_singletons=True)


def attach_items(new_items_with_signatures, existing_series, threshold: int = 10) -> dict:
    """Map new items to existing stable series via nearest centroid.

    *new_items_with_signatures* is a ``dict`` mapping path-or-key to an
    embedding vector, or a list of ``(path_or_item, vector)`` pairs.
    Each vector attaches to the nearest series centroid (embedding
    distance, same threshold rule as ``cluster_items``' secondary gate)
    or to ``None`` when no centroid is close enough.

    Pure: never mutates items or series — the caller assigns the
    returned ids. Existing membership is untouched by construction.
    Returns ``dict[str(path-or-key), series_id | None]``.
    """
    from tabs.image_gallery.services import clustering as _clustering

    try:
        pairs: list[tuple] = []
        if isinstance(new_items_with_signatures, dict):
            try:
                iterable = list(new_items_with_signatures.items())
            except Exception:
                iterable = []
            for k, v in iterable:
                pairs.append((k, v))
        else:
            for entry in list(new_items_with_signatures or []):
                try:
                    k, v = entry
                except Exception:
                    continue
                pairs.append((k, v))
    except Exception:
        return {}

    try:
        centroids = _clustering.series_centroids(list(existing_series or []))
    except Exception:
        centroids = {}

    out: dict = {}
    for key, vec in pairs:
        try:
            if hasattr(key, "path"):
                label = _key(getattr(key, "path", None))
            else:
                label = _key(key)
        except Exception:
            continue
        try:
            out[label] = _clustering.nearest_series_id(vec, centroids, threshold)
        except Exception:
            out[label] = None
    return out
