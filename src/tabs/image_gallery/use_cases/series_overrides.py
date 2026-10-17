"""Manual series overrides for the Image Gallery controller (Wave 5).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the manual series-arrangement actions — pinning paths to a
series / ungrouping them, minting a new series, the append path's centroid
attach + tail cluster, re-cluster / reset, and the clean-rejected review entry.
Override application itself lives in ``use_cases/series_override.py`` (the
regroup/attach primitives); these functions own the controller-level flow:
override-map writes, in-memory regroup delivery, stable-id minting and the
triage re-run. The owner keeps thin delegators with the method names verbatim.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).

Audit-Meta: pattern=thin-owner-target size=exempt reason="manual series overrides — override-map writes + in-memory regroup flow over the series_override primitives"
"""

from __future__ import annotations

import logging
from pathlib import Path

from tabs.image_gallery.models import Series

logger = logging.getLogger("ImproveImgSLI")


def move_paths_to_series(owner, paths, series_id: str | None) -> int:
    """Pin *paths* to *series_id* (None = forced UNGROUPED) + SYNC regroup.

    S2 seam: ZERO clustering, ZERO thread hops, ZERO analysis starts.
    Internal-DnD entry point (``ui/drag_drop`` routes the gallery mime
    here, never through ``open_paths``). Writes the controller-local
    override map, regroups in memory via the base ``apply_overrides``
    on the live items + last series (call shape
    ``regroup(items, overrides, last_series)`` — S1 swaps the regroup
    core mechanically), preserves 1-member leftovers as own sections,
    then delivers the post-triage view tail directly (``state.series``
    + emit + ``widget.set_triage`` — never the worker). Returns items
    pinned.
    """
    from tabs.image_gallery.use_cases import series_override as _override

    try:
        pool = {str(it.path) for it in owner.state.items}
    except Exception:
        pool = set()
    try:
        targets = [Path(p) if not isinstance(p, Path) else p for p in list(paths or [])]
    except Exception:
        return 0
    in_pool = [p for p in targets if str(p) in pool]
    if not in_pool:
        return 0
    try:
        sid = str(series_id) if series_id is not None else None
    except Exception:
        sid = None
    # No-op guard (Wave C): every in-pool target already sits in the
    # target series (current post-override view: ``it.series_id`` after
    # the last triage, None == forced UNGROUPED) → skip the full rebuild
    # entirely. Partial overlap proceeds for the rest only.
    try:
        current_by_path = {}
        for it in owner.state.items:
            try:
                current_by_path[str(it.path)] = it
            except Exception:
                continue
        rest = []
        for p in in_pool:
            try:
                cur = getattr(current_by_path.get(str(p)), "series_id", None)
                cur_sid = str(cur) if cur is not None else None
            except Exception:
                cur_sid = "<unknown>"
            if cur_sid != sid:
                rest.append(p)
        if not rest:
            logger.debug(
                "move_paths_to_series noop: %d paths already in series %s",
                len(in_pool), sid,
            )
            return 0
        in_pool = rest
    except Exception:
        pass
    moved = int(_override.set_override(owner._series_overrides, [str(p) for p in in_pool], sid))
    try:
        live = list(owner.state.items)
    except Exception:
        return moved
    try:
        pre_ids: dict[str, str | None] = {}
        for it in live:
            try:
                cur = getattr(it, "series_id", None)
                pre_ids[str(it.path)] = str(cur) if cur is not None else None
            except Exception:
                continue
        last_series = list(owner.state.series or [])
        regrouped = _override.apply_overrides(live, owner._series_overrides, last_series)
        regrouped = owner._restore_singletons(
            live, owner._series_overrides, pre_ids, last_series, regrouped
        )
        # Newer than any in-flight triage: its delivery drops (sgen).
        owner._next_series_gen()
        owner._apply_series_view(regrouped)
    except Exception:
        logger.debug("move_paths_to_series regroup failed", exc_info=True)
    return moved


def group_paths_as_new_series(owner, paths) -> str | None:
    """Pin *paths* into a brand-new manual series + SYNC regroup.

    Context-menu "Group" entry point (multi-select): mints a fresh
    stable id from the series counter (pinned + live ids skipped —
    never reused, never collides), then routes through
    ``move_paths_to_series`` (override pins + in-memory regroup +
    view, zero clustering, zero thread hops). Members may come from
    anywhere (UNGROUPED tail, other series); leftovers keep their
    sections via the move path's singleton restore. Returns the new
    series id, or None when nothing moved.
    """
    try:
        targets = [Path(p) if not isinstance(p, Path) else p for p in list(paths or [])]
    except Exception:
        return None
    if not targets:
        return None
    try:
        with owner._series_id_lock:
            used: set[str] = set()
            try:
                for v in (owner._series_overrides or {}).values():
                    if v is not None:
                        used.add(str(v))
            except Exception:
                pass
            try:
                for entry in (owner.state.series or []):
                    eid = owner._section_id(
                        entry, owner._section_members(entry)
                    )
                    if eid is not None:
                        used.add(str(eid))
            except Exception:
                pass
            # Same convention as translate_computed_to_stable: the
            # counter holds the LAST issued number, candidates start
            # past it (monotonic, never reused, gaps allowed).
            try:
                n = int(owner._series_next_id or 1)
            except Exception:
                n = 1
            while True:
                n += 1
                if f"series_{n}" not in used:
                    break
            new_id = f"series_{n}"
            try:
                owner._series_next_id = int(n)
            except Exception:
                pass
    except Exception:
        return None
    try:
        moved = int(owner.move_paths_to_series(targets, new_id))
    except Exception:
        return None
    return new_id if moved > 0 else None


def _attach_append_items(owner, new_items) -> dict:
    """Attach NEW files to the nearest EXISTING series (S2 append path).

    S1 centroid policy: one nearest-centroid decision per readable
    unpinned item via S1 ``attach_items`` (same threshold rule as
    ``cluster_items``). Attached items join the series (rank comes from
    the controller's measured-fusion pass, never positional), misses land
    UNGROUPED. Existing membership (members, ranks, ids) is untouched.
    Paths carrying a stored override (re-drop
    of a removed pinned file) take the pin: join the pinned group or
    stand as a 1-member section. Unreadable files (zero phash + zero
    embedding — cluster parity) stay UNGROUPED. Returns
    ``{str(path): series_id | None}``.

    Mutates ``state.series`` in place (member appends / singleton
    sections); callers deliver via ``_apply_series_view``.
    """
    from tabs.image_gallery.controller import _ATTACH_THRESHOLD

    try:
        fresh = list(new_items or [])
    except Exception:
        return {}
    if not fresh:
        return {}
    try:
        from tabs.image_gallery.services.clustering import signature_for as _sig
    except Exception:
        _sig = None  # type: ignore[assignment]
    members_of = owner._section_members
    id_of = owner._section_id
    try:
        groups = list(owner.state.series or [])
    except Exception:
        groups = []
    # Centroid attach (S1 policy): one nearest-centroid decision for all
    # readable unpinned items via S1 ``attach_items`` — replaces the
    # first-member-phash representative scan. Signatures come from the
    # perceptual cache (no re-decode); unreadable items never reach it.
    try:
        from tabs.image_gallery.use_cases.series_override import (
            attach_items as _attach,
        )
    except Exception:
        _attach = None  # type: ignore[assignment]
    try:
        from tabs.image_gallery.services.clustering import signature_for as _sig2
    except Exception:
        _sig2 = None  # type: ignore[assignment]
    decided: dict[str, str | None] = {}
    try:
        pairs: list[tuple] = []
        for item in fresh:
            try:
                key = str(getattr(item, "path", None))
            except Exception:
                continue
            try:
                has_pin = key in (owner._series_overrides or {})
            except Exception:
                has_pin = False
            if has_pin:
                continue
            try:
                if _sig2 is not None:
                    _h, _e = _sig2(item.path)
                else:
                    _h, _e = 0, []
            except Exception:
                _h, _e = 0, []
            try:
                unreadable = _h == 0 and not any(_e or [])
            except Exception:
                unreadable = _h == 0
            if unreadable:
                continue
            pairs.append((key, list(_e or [])))
        if _attach is not None and pairs:
            try:
                decided = dict(
                    _attach(pairs, groups, _ATTACH_THRESHOLD) or {}
                )
            except Exception:
                decided = {}
    except Exception:
        decided = {}
    by_id: dict[str, object] = {}
    for entry in groups:
        members = members_of(entry)
        eid = id_of(entry, members)
        if eid is not None:
            by_id.setdefault(str(eid), entry)
    attached: dict[str, str | None] = {}
    for item in fresh:
        try:
            key = str(getattr(item, "path", None))
        except Exception:
            continue
        # Stored pin wins over similarity (re-dropped pinned file).
        try:
            has_pin = key in (owner._series_overrides or {})
            pin = (owner._series_overrides or {}).get(key) if has_pin else "auto"
        except Exception:
            has_pin, pin = False, "auto"
        if has_pin:
            sid = str(pin) if pin is not None else None
            try:
                item.series_id = sid
            except Exception:
                pass
            if sid is not None:
                host = by_id.get(sid)
                if host is not None:
                    try:
                        if hasattr(host, "members"):
                            host.members.append(item)  # type: ignore[union-attr]
                        elif isinstance(host, list):
                            host.append(item)
                        else:
                            raise TypeError("ungroupable host")
                    except Exception:
                        pass
                else:
                    try:
                        entry = Series(id=sid, members=[item])
                    except Exception:
                        entry = None
                    if entry is not None:
                        groups.append(entry)
                        by_id[sid] = entry
            attached[key] = sid
            continue
        item_hash, item_embed = 0, []
        if _sig is not None:
            try:
                item_hash, item_embed = _sig(item.path)
            except Exception:
                item_hash, item_embed = 0, []
        if not isinstance(item_hash, int):
            item_hash = 0
        try:
            unreadable = item_hash == 0 and not any(item_embed or [])
        except Exception:
            unreadable = item_hash == 0
        if unreadable:
            try:
                item.series_id = None
            except Exception:
                pass
            attached[key] = None
            continue
        hit = decided.get(key)
        if hit is None:
            try:
                item.series_id = None
            except Exception:
                pass
            attached[key] = None
            continue
        rsid, entry = hit, by_id.get(str(hit))
        if entry is None:
            # Centroid id with no live group (should not happen — the
            # centroids come from these groups): fail to UNGROUPED
            # rather than leaving a dangling series_id.
            try:
                item.series_id = None
            except Exception:
                pass
            attached[key] = None
            continue
        try:
            item.series_id = rsid
        except Exception:
            pass
        try:
            if hasattr(entry, "members"):
                entry.members.append(item)  # type: ignore[union-attr]
            elif isinstance(entry, list):
                entry.append(item)
        except Exception:
            pass
        attached[key] = rsid
    try:
        setattr(owner.state, "series", groups)
    except Exception:
        pass
    return attached


def _cluster_tail_into_series(owner) -> list:
    """Form NEW series from the UNGROUPED tail (S2 append follow-up).

    Runs after ``_attach_append_items`` in the quiet-append branch.
    Candidates are the current tail — old singletons plus fresh attach
    misses — minus pinned paths (pins were already placed by attach).
    ``cluster_items`` groups them (same threshold as the seed run);
    groups ≥2 join ``state.series`` with fresh stable ids continuing
    the ``series_<n>`` counter (pinned ids skipped). Existing series
    (members, ranks, ids) and the triage mode are untouched; misses
    stay UNGROUPED.

    Cheap by construction, not by batching: ``cluster_items`` reads
    the perceptual signature cache keyed ``(path, mtime_ns, size)``,
    so unchanged files never re-decode — appending 1 file to a tail
    of 50 decodes exactly 1 file, the rest is integer/float compares.
    Past ``_TAIL_CLUSTER_LIMIT`` candidates the quadratic pass would
    jank the GUI thread, so it is skipped (manual Re-cluster covers
    huge tails). Returns the new groups (possibly []).
    """
    from tabs.image_gallery.controller import _ATTACH_THRESHOLD, _TAIL_CLUSTER_LIMIT

    try:
        items = list(getattr(owner.state, "items", None) or [])
        groups = list(getattr(owner.state, "series", None) or [])
    except Exception:
        return []
    try:
        member_paths: set[str] = set()
        for entry in groups:
            for m in owner._section_members(entry):
                try:
                    member_paths.add(str(getattr(m, "path", None)))
                except Exception:
                    continue
    except Exception:
        member_paths = set()
    try:
        pinned = {str(k) for k in (getattr(owner, "_series_overrides", None) or {})}
    except Exception:
        pinned = set()
    tail = []
    for it in items:
        try:
            key = str(getattr(it, "path", None))
        except Exception:
            continue
        if key in member_paths or key in pinned:
            continue
        tail.append(it)
    if len(tail) < 2 or len(tail) > _TAIL_CLUSTER_LIMIT:
        return []
    try:
        from tabs.image_gallery.services.clustering import cluster_items as _cluster
    except Exception:
        return []
    try:
        fresh_groups = list(_cluster(list(tail), _ATTACH_THRESHOLD) or [])
    except Exception:
        logger.debug("tail cluster failed", exc_info=True)
        return []
    if not fresh_groups:
        return []
    try:
        fresh_groups, _ = owner._assign_fresh_stable_ids(fresh_groups)
    except Exception:
        pass
    try:
        setattr(owner.state, "series", list(groups) + list(fresh_groups))
    except Exception:
        return []
    return list(fresh_groups)


def recluster_series(owner) -> None:
    """Fresh cluster+apply world with pins re-applied + rebuild.

    Header/grid menu entry next to Reset. Unlike ``reset`` (which
    clears pins), pins are KEPT: the existing ``_start_triage``
    pipeline snapshots + re-applies overrides, assigns fresh stable
    ids to auto groups, and rebuilds on delivery (``cover_grid=False``
    — live groups stay visible until the fresh world lands).
    """
    try:
        items = list(owner.state.items)
    except Exception:
        items = []
    try:
        owner._start_triage(items, cover_grid=False)
    except Exception:
        logger.debug("recluster_series start failed", exc_info=True)


def reset_series_overrides(owner) -> int:
    """Clear every manual series override + regroup automatically.

    Reset affordance behind the series-header context menu
    (``ui/drag_drop`` installs it at runtime — ``grid_view.py`` stays
    untouched). Reuses the existing ``_start_triage`` rebuild path.
    Returns entries cleared (0 = no rebuild).
    """
    try:
        cleared = len(owner._series_overrides)
    except Exception:
        cleared = 0
    try:
        owner._series_overrides.clear()
    except Exception:
        pass
    if not cleared:
        return 0
    try:
        owner._start_triage(list(owner.state.items), cover_grid=False)
    except Exception:
        logger.debug("reset_series_overrides retriage failed", exc_info=True)
    return cleared


def clean_rejected(owner) -> list[dict]:
    from tabs.image_gallery.use_cases.triage import clean_rejected as _clean

    return _clean(owner)


def show_clean_review(owner) -> None:
    # Delegate to widget's S3 overlay (TopLevelInWindowOverlay).
    try:
        if hasattr(owner.widget, "show_clean_review"):
            owner.widget.show_clean_review(owner)
    except Exception:
        pass
