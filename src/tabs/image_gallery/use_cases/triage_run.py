"""Stage-2 triage-Pass-1 pipeline for the Image Gallery controller (Wave 3).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns the first Stage-2 pass — stable-id seeding, manual-override
singleton restore, the sync clustering pipeline (``_run_triage_sync``), the
worker entry (``_start_triage``) with its staleness generations, the
measured-metrics settle tail and its AI-domain ranker hooks, and the append
processing indicator. The owner keeps the shared primitives
(``_find_item`` / ``_tracked`` / ``_pool_start`` / folder+series generation
discipline / ``_apply_fusion_ranks``) and thin delegators keep the method
names verbatim.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).

Audit-Meta: pattern=thin-owner-target size=exempt reason="one Stage-2 triage pipeline (stable ids -> cluster -> settle) sharing GenericWorker + owner generation state"
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.models import (
    ActivityPhase,
    GalleryItem,
    Mode,
    Series,
    TriageState,
)
from tabs.image_gallery.services.activity import clear_activity, set_activity

logger = logging.getLogger("ImproveImgSLI")


def _next_series_gen(owner) -> int:
    """Bump the series-view generation: in-flight triage goes stale."""
    owner._series_gen += 1
    return owner._series_gen


def _assign_fresh_stable_ids(owner, computed) -> tuple:
    """Seed-assign fresh stable ids to computed groups IN ORDER.

    Thin owner over S1 ``translate_computed_to_stable`` (the single
    implementation): snapshot counter + pinned ids under the id lock,
    translate (collision-skip included), commit the returned counter.
    Member ``series_id`` fields are rewritten to match; computed
    ranks/centroids untouched. Returns ``(series, next_counter)``.
    """
    try:
        from tabs.image_gallery.use_cases.series_override import (
            translate_computed_to_stable as _translate,
        )
    except Exception:
        return (list(computed or []), owner._series_next_id)
    try:
        pinned = {
            str(v)
            for v in (owner._series_overrides or {}).values()
            if v is not None
        }
    except Exception:
        pinned = set()
    with owner._series_id_lock:
        try:
            start = int(owner._series_next_id or 1)
        except Exception:
            start = 1
        try:
            series, nxt = _translate(computed, start, skip_ids=pinned)
        except Exception:
            return (list(computed or []), owner._series_next_id)
        try:
            owner._series_next_id = int(nxt)
        except Exception:
            pass
        return (series, owner._series_next_id)


def _section_members(entry) -> list:
    """Member list of one cluster (Series dataclass or plain list)."""
    try:
        if hasattr(entry, "members"):
            return list(getattr(entry, "members", None) or [])
        if isinstance(entry, (list, tuple)):
            return list(entry)
    except Exception:
        pass
    return []


def _section_id(entry, members) -> str | None:
    """Cluster id string (Series.id, else first member's series_id)."""
    try:
        eid = getattr(entry, "id", None)
        if eid is not None:
            return str(eid)
    except Exception:
        pass
    try:
        if members:
            sid = getattr(members[0], "series_id", None)
            return str(sid) if sid is not None else None
    except Exception:
        pass
    return None


def _restore_singletons(owner, items, overrides, pre_ids, last_series, regrouped) -> list:
    """Preserve 1-member manual sections post-apply (S2).

    Base ``apply_overrides`` dissolves every group with <2 members.
    Sync paths keep two kinds of singletons visible as own 1-member
    ``Series`` sections instead: (a) items carrying a STRING override
    that end UNGROUPED — restored with the PINNED id (covers moves
    onto fresh ids plus pins surviving later moves/deliveries); (b)
    unpinned leftovers whose pre-apply group vanished (``pre_ids``
    given — the move path only) — restored with the PRE id.
    0-member series close (nothing to restore) and forced-UNGROUPED
    (None pin) never restores. Delivery calls with ``pre_ids=None``
    (pinned only — a fresh cluster world has no leftovers).
    """
    try:
        out = list(regrouped or [])
    except Exception:
        out = []
    try:
        live = list(items or [])
    except Exception:
        return out
    try:
        omap = dict(overrides or {})
    except Exception:
        omap = {}
    members_of = _section_members
    id_of = _section_id
    present: set[str] = set()
    by_id: dict[str, object] = {}
    for entry in out:
        members = members_of(entry)
        eid = id_of(entry, members)
        if eid is not None:
            present.add(eid)
            by_id.setdefault(eid, entry)
    last_centroid: dict[str, object] = {}
    last_phash: dict[str, object] = {}
    try:
        for entry in list(last_series or []):
            members = members_of(entry)
            eid = id_of(entry, members)
            if eid is None:
                continue
            try:
                last_centroid.setdefault(eid, getattr(entry, "centroid", None))
            except Exception:
                pass
            try:
                last_phash.setdefault(eid, getattr(entry, "phash_centroid", None))
            except Exception:
                pass
    except Exception:
        pass
    for it in live:
        try:
            cur = getattr(it, "series_id", None)
        except Exception:
            continue
        if cur is not None:
            continue
        try:
            key = str(getattr(it, "path", None))
        except Exception:
            continue
        sid: str | None = None
        try:
            if key in omap and omap[key] is not None:
                sid = str(omap[key])
        except Exception:
            sid = None
        if sid is None and pre_ids is not None:
            try:
                if key in omap:
                    # Explicit override wins — including forced
                    # UNGROUPED (None pin): the item must never be
                    # re-pinned to its pre-apply series, or the last
                    # member of a dissolved group resurrects it and
                    # can never be ungrouped.
                    continue
                pre = pre_ids.get(key)
                if pre is not None and str(pre) not in present:
                    sid = str(pre)
            except Exception:
                pass
        if sid is None:
            continue
        if sid in by_id:
            # Defensive rejoin: the group survived but the item fell
            # out (should not happen — apply groups by final sid).
            host = by_id[sid]
            try:
                if hasattr(host, "members"):
                    host.members.append(it)  # type: ignore[union-attr]
                elif isinstance(host, list):
                    host.append(it)
                else:
                    raise TypeError("ungroupable host")
                try:
                    it.series_id = sid
                except Exception:
                    pass
            except Exception:
                try:
                    it.series_id = sid
                except Exception:
                    pass
            continue
        try:
            ph = (getattr(it, "metrics", None) or {}).get("phash")
        except Exception:
            ph = None
        if not isinstance(ph, int):
            ph = last_phash.get(sid)
        try:
            it.series_id = sid
        except Exception:
            pass
        try:
            out.append(
                Series(
                    id=sid,
                    members=[it],
                    centroid=last_centroid.get(sid),  # type: ignore[arg-type]
                    phash_centroid=ph,  # type: ignore[arg-type]
                )
            )
        except Exception:
            continue
        try:
            by_id[sid] = out[-1]
            present.add(sid)
        except Exception:
            pass
    try:
        out.sort(
            key=lambda s: (
                -len(members_of(s)),
                str(getattr(s, "id", "") or ""),
            )
        )
    except Exception:
        pass
    return out


def _apply_series_view(owner, series) -> None:
    """Post-triage view tail for sync paths (move / append-attach).

    Same delivery as ``_on_triage_ready`` minus workers: ``state.series``
    + rank/mode/source emit + ``widget.set_triage`` + spinner off. No
    clustering, no thread hops, no analysis starts.
    """
    setattr(owner.state, "series", series)
    # Rank the regrouped view from the measured fusion (move / append
    # attach): same primitive as the triage tail, so a regroup never
    # resurrects the centroid order.
    owner._apply_fusion_ranks(series)
    try:
        ts = getattr(owner.state, "triage_state", "idle")
        triage_s = getattr(ts, "value", ts)
        triage_s = str(triage_s or "idle")
    except Exception:
        triage_s = "idle"
    try:
        owner._emit_triage_finished(triage_s)
    except Exception:
        logger.debug("_apply_series_view emit failed", exc_info=True)
    try:
        owner.widget.set_triage(series, owner.state.mode, owner.state.source_path)
    except Exception:
        logger.debug("_apply_series_view set_triage failed", exc_info=True)
    try:
        if hasattr(owner.widget, "set_triage_done"):
            owner.widget.set_triage_done()  # type: ignore[attr-defined]
        elif hasattr(owner.widget, "toolbar") and hasattr(
            owner.widget.toolbar, "set_triage_done"
        ):
            owner.widget.toolbar.set_triage_done()  # type: ignore[attr-defined]
    except Exception:
        logger.debug("_apply_series_view set_triage_done failed", exc_info=True)


def _run_triage_sync(
    owner, items: list[GalleryItem], overrides: dict | None = None
) -> tuple[list[Series], Path | None, Mode]:
    """Pure pipeline for GenericWorker: cluster → override → mode (no auto hub)."""
    from tabs.image_gallery.services.clustering import cluster_items
    from tabs.image_gallery.services.mode import select_mode
    from tabs.image_gallery.use_cases import series_override as _override

    series = cluster_items(items)
    # S2 stable ids: every seed run renames computed groups to fresh
    # ``series_<n>`` IN ORDER before overrides apply (pins keep their
    # stored ids verbatim — override wins in the post-pass below).
    try:
        series, _ = owner._assign_fresh_stable_ids(series)
    except Exception:
        logger.debug("stable-id seed assignment failed", exc_info=True)
    # Wave B post-pass (pure): manual overrides win over computed ids.
    # ``overrides`` is an explicit snapshot taken in _start_triage (the
    # worker must not read live controller state); None keeps old
    # callers working and means "no overrides".
    try:
        series = _override.apply_overrides(items, overrides or {}, series)
    except Exception:
        logger.debug("series override apply failed", exc_info=True)
    # No auto source: hub_detection disabled — source stays None until
    # the user picks one explicitly ("Set as source" / context menu).
    source = None
    mode = select_mode(series, items, source)
    return (series, source, mode)


def retriage_quiet(owner) -> bool:
    """Regroup the current pool after restore/activation (no rescan).

    Series live only in controller memory, so a pool restored from a
    slot comes back FLAT — without this, returning to a tab leaves
    every card UNGROUPED until the next folder open. Fast path: when
    every signature is cached (the common return-to-tab case) the
    pipeline runs INLINE on the GUI thread (~ms, no worker hop, no
    spinner flash); otherwise the background worker path. Staleness
    guarded by folder/series generations (a newer triage wins).
    Returns True when (re)grouping started or applied.
    """
    try:
        if getattr(owner.state, "triage_state", None) not in (
            TriageState.IDLE, TriageState.DONE, TriageState.ERROR,
        ):
            return False
        items = list(getattr(owner.state, "items", None) or [])
    except Exception:
        return False
    if not items:
        return False
    try:
        from tabs.image_gallery.debug import gallery_debug as _dbg
        from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_on

        if _dbg_on():
            _dbg("retriage_quiet: regrouping %d restored items", len(items))
    except Exception:
        pass
    try:
        from tabs.image_gallery.services.clustering import (
            signatures_cached as _cached,
        )

        if _cached(items):
            try:
                overrides = dict(getattr(owner, "_series_overrides", None) or {})
            except Exception:
                overrides = {}
            try:
                import time as _time

                _t0 = _time.perf_counter()
                series, source, mode = owner._run_triage_sync(
                    list(items), overrides
                )
                _t1 = _time.perf_counter()
                series = owner._commit_triage_series(series, source, mode)
                _t2 = _time.perf_counter()
                owner._apply_triage_result(series, source, mode)
                _t3 = _time.perf_counter()
                try:
                    from tabs.image_gallery.debug import gallery_debug as _dbg2
                    from tabs.image_gallery.debug import gallery_debug_enabled as _dbg_on2

                    if _dbg_on2():
                        _dbg2(
                            "retriage_quiet sync phases: pipeline=%.0fms commit=%.0fms apply=%.0fms",
                            (_t1 - _t0) * 1000.0,
                            (_t2 - _t1) * 1000.0,
                            (_t3 - _t2) * 1000.0,
                        )
                except Exception:
                    pass
            except Exception:
                logger.debug("retriage_quiet sync pipeline failed", exc_info=True)
                raise
            return True
    except Exception:
        pass
    try:
        owner._start_triage(items, cover_grid=False)
        return True
    except Exception:
        return False


def _start_triage(owner, items: list[GalleryItem], *, cover_grid: bool = True) -> None:
    """Cluster in a worker, then ``set_triage`` on delivery.

    ``cover_grid=True`` (folder switch / replace) hides the grid behind
    the S1 scanning state until groups are ready. ``False`` (appending
    to a live pool) keeps the current groups visible and only spins the
    toolbar — tearing down a good view for one new image is the jump
    users see on every drop.
    """
    from tabs.image_gallery.controller import TRIAGE_PRIORITY

    if not items:
        setattr(owner.state, "triage_state", TriageState.DONE)
        setattr(owner.state, "series", [])
        setattr(owner.state, "mode", None)
        setattr(owner.state, "source_path", None)
        owner._emit_triage_finished("done")
        try:
            owner.widget.set_triage([], None, None)
        except Exception:
            logger.debug("widget.set_triage failed for empty folder", exc_info=True)
        return
    setattr(owner.state, "triage_state", TriageState.RUNNING)
    # A1: S1 scanning n/N in toolbar + empty state (progressive grid)
    if cover_grid:
        try:
            owner.widget.set_scanning(0, len(items))
        except Exception:
            logger.debug("widget.set_scanning failed", exc_info=True)
    else:
        background = getattr(owner.widget, "set_background_scanning", None)
        if callable(background):
            try:
                background(0, len(items))
            except Exception:
                logger.debug("widget.set_background_scanning failed", exc_info=True)
        else:
            # Legacy doubles predate the background API — same covering
            # behavior as before rather than no progress at all.
            try:
                owner.widget.set_scanning(0, len(items))
            except Exception:
                logger.debug("widget.set_scanning failed", exc_info=True)
    owner._mark_local_pass(items, ActivityPhase.ANALYZING)
    worker = GenericWorker(owner._tracked(owner._run_triage_sync), list(items), dict(owner._series_overrides))
    gen = owner._folder_gen
    sgen = owner._series_gen
    worker.signals.result.connect(lambda res, g=gen, s=sgen: owner._on_triage_ready(res, g, s))
    # NOTE: the local "done" badge is NOT stamped here. Triage only clusters
    # series; the card's quality dots come from the Stage-2 proxy pass
    # (artifacts/fidelity/camera) started in ``_apply_triage_result`` and
    # settling 1-2 s later. Stamping done on the triage result made the
    # badge read "done" while the dots were still stale — the exact
    # inversion the append path avoids. ``_apply_triage_result`` now stamps
    # done on the proxy settle (or immediately when there is nothing to
    # compute). See ``_mark_local_pass`` callers.
    worker.signals.error.connect(lambda err, g=gen: owner._on_triage_error(err, g))
    worker.signals.error.connect(lambda _err, its=list(items): owner._mark_local_pass(its, None))
    # Triage outranks background thumbnails so the grid labels settle first.
    owner._pool_start(worker, TRIAGE_PRIORITY)


def _mark_local_pass(owner, items, phase) -> None:
    """Pass-level local activity: ``phase=None`` clears the local phase."""
    for item in items:
        try:
            if phase is None:
                if getattr(item, "activity_source", None) == "local":
                    clear_activity(item)
            else:
                set_activity(item, phase, "local")
        except Exception:
            continue
    try:
        refresh = getattr(owner.widget, "refresh_cards", None)
        if callable(refresh):
            refresh(items)
    except Exception:
        logger.debug("local-pass activity refresh failed", exc_info=True)


def _settle_metrics_pass(owner, items) -> None:
    """The measured-metrics pass for a folder settled (S2/J1 trigger).

    Retires the local "done" badge (the quality dots are in) AND, on the AI
    domain, (re)derives the pipeline: the VLM scorecards the rank reads
    (``_run_ai_on_settle``) and then the Jev rank of the ready series — the
    declared ``jev_rank`` stage requires ``metrics_ready``, and this settle
    is where that fact is published. LEVEL-triggered: a folder opened or a
    session RESTORED in the AI domain re-derives the work from the durable
    domain, not only via an explicit domain switch. The gate dedups, so the
    switch triggering the same run is harmless. Reads the DURABLE domain
    authority (``_judgment_domain``), not ``state`` (replaced by
    open_folder/append/clear_to_empty).
    """
    try:
        owner._mark_local_pass(list(items or []), ActivityPhase.DONE)
    except Exception:
        logger.debug("metrics settle local done failed", exc_info=True)
    # Finality: the metrics pass settled for this folder — now the winner
    # may be marked. Algorithms marks its fusion rank 1 here (AI lets Jev).
    try:
        owner._metrics_settled_gen = owner._folder_gen
    except Exception:
        logger.debug("metrics-settled gen stamp failed", exc_info=True)
    try:
        owner._apply_fusion_ranks(getattr(owner.state, "series", None))
    except Exception:
        logger.debug("settle fusion re-mark failed", exc_info=True)
    # Derive the producer (VLM scorecards) before the consumer (Jev rank):
    # a restored/opened AI domain must reproduce the WORK, not only the
    # persisted choice.
    _run_ai_on_settle(owner)
    _run_jev_on_settle(owner)


def _run_ai_on_settle(owner) -> None:
    """(Re)derive the AI-domain VLM scorecards the Jev rank reads (AI only).

    Level-triggered counterpart of the explicit domain switch: a folder
    opened — or a SESSION RESTORED — in the AI domain must re-derive the
    WORK out of the persisted CHOICE. Cache-first for the visible items; a
    cold item gets the bounded live analysis. The Jev rank then follows from
    the arriving scorecards (``_on_analysis_ready`` →
    ``_queue_ai_rank_on_settle``). A no-op off the AI domain, so the
    Algorithms domain never hits the network on open.
    """
    if str(getattr(owner, "_judgment_domain", "algorithms") or "").strip().lower() != "ai":
        return
    runner = getattr(owner, "_run_ai_for_visible", None)
    if callable(runner):
        try:
            runner()
        except Exception:
            logger.debug("ai analysis on settle failed", exc_info=True)


def _run_jev_on_settle(owner) -> None:
    """Run the AI-domain Jev batch from a settle point (AI domain only)."""
    if str(getattr(owner, "_judgment_domain", "algorithms") or "").strip().lower() != "ai":
        return
    runner = getattr(owner, "_run_jev_ranks", None)
    if callable(runner):
        try:
            runner()
        except Exception:
            logger.debug("jev rank on settle failed", exc_info=True)


def _queue_ai_rank_on_settle(owner) -> None:
    """Coalesce AI-domain Jev re-ranks triggered by arriving analyses.

    An AI batch delivers many analyses in one turn; each changes the ranking
    vector, so a per-arrival Jev pass would flood the API. Coalesce the
    arrivals into a single scheduling pass (the StageGate still dedups and
    ``jev_cache`` pins unchanged payloads). Mirrors the card-refresh idiom;
    a no-op on the Algorithms domain.
    """
    if str(getattr(owner, "_judgment_domain", "algorithms") or "").strip().lower() != "ai":
        return
    if getattr(owner, "_ai_rank_flush_scheduled", False):
        return
    owner._ai_rank_flush_scheduled = True
    try:
        if QCoreApplication.instance() is None:
            # No event loop (headless unit context) — settle synchronously.
            owner._flush_ai_rank_on_settle()
        else:
            QTimer.singleShot(0, owner._flush_ai_rank_on_settle)
    except Exception:
        try:
            owner._flush_ai_rank_on_settle()
        except Exception:
            pass


def _flush_ai_rank_on_settle(owner) -> None:
    owner._ai_rank_flush_scheduled = False
    try:
        _run_jev_on_settle(owner)
    except Exception:
        logger.debug("coalesced AI rank on settle failed", exc_info=True)


def _begin_append_processing(owner, items: list[GalleryItem]) -> None:
    """Append path: mirror the first-load processing UX for NEW items.

    The attach branch deliberately skips retriage (live groups stay
    untouched), but that must not silently drop the processing feedback a
    first load gives: a per-card activity pill (``analyzing``) plus the
    toolbar spinner + count. Without this the appended cards showed no
    badge and the toolbar showed no progress, because ``_load_thumbnail``
    sets ``thumbnail_status = LOADING`` without repainting the card and
    no local activity phase was ever stamped.

    Closed by :meth:`_finish_append_processing` when the batch settles.
    """
    batch = list(items or [])
    if not batch:
        return
    try:
        background = getattr(owner.widget, "set_background_scanning", None)
        if callable(background):
            background(0, len(batch))
    except Exception:
        logger.debug("append background scanning failed", exc_info=True)
    try:
        owner._mark_local_pass(batch, ActivityPhase.ANALYZING)
    except Exception:
        logger.debug("append local pass failed", exc_info=True)


def _finish_append_processing(owner, items: list[GalleryItem]) -> None:
    """Retire the append processing indicator: ``done`` fade + spinner off."""
    batch = list(items or [])
    if not batch:
        return
    try:
        owner._mark_local_pass(batch, ActivityPhase.DONE)
    except Exception:
        logger.debug("append local done failed", exc_info=True)
    try:
        done = getattr(owner.widget, "set_triage_done", None)
        if callable(done):
            done()
    except Exception:
        logger.debug("append processing indicator hide failed", exc_info=True)
    # The append proxy pass settled too: on the AI domain, rank the ready
    # series from the (now complete) measured vector. Gate-deduped.
    try:
        _run_jev_on_settle(owner)
    except Exception:
        logger.debug("append jev on settle failed", exc_info=True)
