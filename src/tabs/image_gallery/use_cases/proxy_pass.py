"""Unified Stage-2 proxy pass for the Image Gallery controller (Wave 3).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
One chunked single-pass ``GenericWorker`` per 50 items decodes each file once
and fans the result out by path into the metrics apply tails
(``use_cases/metrics_stage2``); the triage worker delivery and the manual
series commit converge on the same sync tail. The owner keeps the frozen
``schedule`` seam, the shared primitives (``_tracked`` / ``_pool_start`` /
``_is_current_folder_gen`` / ``_folder_gen``) and ``_apply_fusion_ranks``;
thin delegators keep the method names verbatim.

The ``state.*`` mirror writes go through ``setattr``: a bare ``.state.X =``
outside ``controller.py`` is rejected by the gallery ownership guard
(``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.debug import gallery_artifacts_disabled as _artifacts_disabled
from tabs.image_gallery.debug import gallery_camera_disabled as _camera_disabled
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_fidelity_disabled as _fidelity_disabled
from tabs.image_gallery.models import GalleryItem, Mode, TriageState
from tabs.image_gallery.use_cases import local_metrics as _local_metrics

logger = logging.getLogger("ImproveImgSLI")


def _run_proxy_chunk_sync(chunk: list, source_path, include_camera: bool, full_res_artifacts: bool = False) -> dict:
    """One chunk worker body: shared-proxy single pass (wave A1 API)."""
    from tabs.image_gallery.services.proxy import run_proxy_stages_sync

    try:
        return dict(
            run_proxy_stages_sync(
                list(chunk),
                source_path,
                include_camera=include_camera,
                full_res_artifacts=full_res_artifacts,
            )
        )
    except Exception:
        logger.debug("proxy chunk failed", exc_info=True)
        return {}


def _schedule_proxy(owner, items: list, priority: int, source, gen: int, wanted=None, include_camera: bool | None = None, full_res_artifacts: bool = False, on_done=None) -> int:
    """Chunked proxy batches: one worker per 50 items (never N)."""
    from tabs.image_gallery.controller import _GALLERY_PROXY_CHUNK

    chunks = [items[i:i + _GALLERY_PROXY_CHUNK] for i in range(0, len(items), _GALLERY_PROXY_CHUNK)]
    if not chunks:
        if on_done is not None:
            try:
                on_done()
            except Exception:
                logger.debug("proxy on_done hook failed", exc_info=True)
        return 0
    if include_camera is None:
        try:
            include_camera = bool(getattr(owner.state, "mode", None) == Mode.CAMERA)
        except Exception:
            include_camera = False
    try:
        wanted_set = frozenset(wanted) if wanted else frozenset(("artifacts", "fidelity", "camera"))
    except Exception:
        wanted_set = frozenset(("artifacts", "fidelity", "camera"))
    owner._proxy_done = 0
    owner._proxy_total = len(chunks)
    # Per-batch settle counter (independent of the global _proxy_* progress):
    # fires ``on_done`` once after every chunk of THIS batch has delivered.
    remaining = [len(chunks)]

    def _settle(_payload=None) -> None:
        remaining[0] -= 1
        if remaining[0] > 0:
            return
        if on_done is not None:
            try:
                on_done()
            except Exception:
                logger.debug("proxy on_done hook failed", exc_info=True)

    started = 0
    for chunk in chunks:
        worker = GenericWorker(
            owner._tracked(_run_proxy_chunk_sync),
            list(chunk), source, include_camera, full_res_artifacts,
        )
        worker.signals.result.connect(
            lambda res, g=gen, w=wanted_set: owner._on_proxy_batch_ready(
                res, g, w, source=source,
                include_camera=include_camera, full_res_artifacts=full_res_artifacts,
            )
        )
        worker.signals.error.connect(
            lambda err: logger.debug("proxy batch worker error: %r", err, exc_info=True)
        )
        if on_done is not None:
            # Completion hook (append processing UX): counts each chunk
            # exactly once — result OR error. Connected AFTER the apply
            # handler so the last chunk is applied before on_done runs.
            worker.signals.result.connect(_settle)
            worker.signals.error.connect(_settle)
        owner._pool_start(worker, priority)
        started += 1
    # Chunk fan-out for tests (50-item batching assertion).
    try:
        owner._sched_chunk_workers = int(getattr(owner, "_sched_chunk_workers", 0)) + started
    except Exception:
        pass
    return started


def _start_proxy_analysis(owner, items: list[GalleryItem], source_path: Path | None, mode, *, on_done=None) -> None:
    """Triage-tail Stage 2: ONE single-pass background step (proxy).

    Replaces the old three whole-pool batch workers (artifact +
    fidelity + camera) with chunked ``run_proxy_stages_sync`` workers
    sharing one bounded decode per file. Fail-closed per item,
    path-keyed delivery into the existing apply tails; the
    ``_analysis_fingerprint`` skip above stays the gate.

    ``on_done`` (optional) fires once after the whole batch settles —
    including the no-work early returns — so the append path can retire
    its processing indicator without dangling.
    """
    from tabs.image_gallery.controller import PROXY_BATCH_PRIORITY

    def _finish() -> None:
        if on_done is None:
            return
        try:
            on_done()
        except Exception:
            logger.debug("proxy on_done hook failed", exc_info=True)

    if not items:
        _finish()
        return
    want_artifacts = not _artifacts_disabled()
    want_fidelity = not _fidelity_disabled() and source_path is not None
    try:
        want_camera = not _camera_disabled() and mode == Mode.CAMERA
    except Exception:
        want_camera = False
    if not (want_artifacts or want_fidelity or want_camera):
        _dbg("proxy analysis skipped: all Stage-2 lanes kill-switched")
        _finish()
        return
    wanted = frozenset(
        [s for s, w in (
            ("artifacts", want_artifacts),
            ("fidelity", want_fidelity),
            ("camera", want_camera),
        ) if w]
    )
    try:
        owner.schedule(
            list(items), PROXY_BATCH_PRIORITY, op="proxy",
            source=source_path, gen=owner._folder_gen, wanted=wanted,
            include_camera=want_camera, full_res_artifacts=want_artifacts,
            on_done=on_done,
        )
    except Exception:
        logger.debug("proxy analysis start failed", exc_info=True)
        _finish()


def _attach_analysis_records(owner, result: dict) -> None:
    """Copy engine records onto the matching items (W9).

    ``services/proxy.py`` adds the ``"analysis"`` key to a batch entry ONLY when
    the engine ran — the default since P9a — and the plan produced records. With
    the engine could not produce records (P9b: no kill-switch) the key is absent, every item
    keeps ``analysis_records == ()``, and the read path stays byte-identical to
    the legacy domain read (plan-gallery-analysis-engine-2026-10-20 W9).
    """
    try:
        items = list(getattr(owner.state, "items", ()) or ())
    except Exception:
        return
    for item in items:
        try:
            entry = result.get(str(item.path))
        except Exception:
            continue
        if not isinstance(entry, dict) or "analysis" not in entry:
            continue
        try:
            item.analysis_records = tuple(entry.get("analysis") or ())
        except Exception:
            logger.debug(
                "analysis records attach failed for %s", item.path, exc_info=True
            )


def _on_proxy_batch_ready(owner, result: object, gen: int | None, wanted: object = None, *, source=None, include_camera: bool | None = None, full_res_artifacts: bool = False) -> None:
    """One chunk delivery: persist it, then fan out by path into the apply tails."""
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched — late proxy chunk dropped
    if not isinstance(result, dict):
        return
    try:
        wanted_set = set(wanted or ("artifacts", "fidelity", "camera"))
    except Exception:
        wanted_set = {"artifacts", "fidelity", "camera"}
    # Persist the FULL entry (severities + maps + fidelity/camera + engine
    # records) under the identity this pass ran with, BEFORE the apply tails
    # replace the raw entry with the item's mirror.
    _local_metrics.persist(owner, result, wanted_set, source=source, include_camera=include_camera, full_res_artifacts=full_res_artifacts)
    # Engine records ride every chunk (the hook is not lane-gated) and are
    # attached before the apply tails so a repaint triggered below already sees
    # them through ``analysis/read.py``.
    _attach_analysis_records(owner, result)
    try:
        if "artifacts" in wanted_set:
            arts = {
                k: (v.get("artifacts") if isinstance(v, dict) else None)
                for k, v in result.items()
            }
            maps = {
                k: (v.get("artifact_maps") if isinstance(v, dict) else None)
                for k, v in result.items()
            }
            owner._apply_artifact_map(arts, maps)
        if "fidelity" in wanted_set:
            fid = {
                k: (v.get("fidelity") if isinstance(v, dict) else None)
                for k, v in result.items()
            }
            owner._apply_fidelity_map(fid)
        if "camera" in wanted_set:
            cam = {
                k: (v.get("camera") if isinstance(v, dict) else None)
                for k, v in result.items()
            }
            owner._apply_camera_map(cam)
    finally:
        try:
            owner._proxy_done += 1
            total = int(owner._proxy_total)
            done = int(owner._proxy_done)
        except Exception:
            total, done = (0, 0)
        # Multi-chunk progress only: single-chunk (small-folder) runs
        # stay silent so small-folder latency/behavior cannot regress.
        if total > 1:
            background = getattr(owner.widget, "set_background_scanning", None)
            if callable(background):
                try:
                    background(done, total)
                except Exception:
                    logger.debug("proxy progress hook failed", exc_info=True)
        try:
            owner._trim_proxy_cache()
        except Exception:
            pass


def _on_triage_ready(owner, result: object, gen: int | None = None, sgen: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        logger.debug("triage result dropped: stale folder generation")
        return
    if sgen is not None and sgen != owner._series_gen:
        # A sync view rewrite (move / append-attach) landed while this
        # worker was in flight — its groups predate the manual
        # arrangement. Drop instead of clobbering it.
        logger.debug("triage result dropped: stale series generation")
        return
    try:
        series, source, mode = result  # type: ignore[misc]
    except Exception:
        logger.debug("triage result unpack failed: %r", result, exc_info=True)
        setattr(owner.state, "triage_state", TriageState.ERROR)
        owner._emit_triage_finished("error")
        return
    # Wave B: re-apply overrides on the GUI thread — the worker snapshot
    # may predate drops that landed while it was in flight. Idempotent.
    try:
        from tabs.image_gallery.use_cases import series_override as _override

        series = _override.apply_overrides(
            list(owner.state.items), owner._series_overrides, series
        )
    except Exception:
        logger.debug("series override re-apply failed", exc_info=True)
    series = owner._commit_triage_series(series, source, mode)
    owner._apply_triage_result(series, source, mode)


def _commit_triage_series(owner, series, source, mode):
    """Commit a triage outcome to state (shared sync/async tail).

    Pinned-singleton restore + state assignment + DONE emit. The async
    worker path and the synchronous fast path converge here so pins
    survive delivery identically on both.
    """
    # S2: pinned singletons survive delivery — a fresh cluster world
    # dissolves <2 groups, so without this a delivery would ungroup
    # cards the user manually placed (e.g. onto fresh ids). Pinned
    # only here (``pre_ids=None``): a fresh world has no leftovers.
    try:
        series = owner._restore_singletons(
            list(owner.state.items),
            owner._series_overrides,
            None,
            series,
            series,
        )
    except Exception:
        logger.debug("pinned singleton restore failed", exc_info=True)
    setattr(owner.state, "series", series)
    setattr(owner.state, "source_path", source)
    setattr(owner.state, "mode", mode)
    setattr(owner.state, "triage_state", TriageState.DONE)
    # P1: the mode was just (re)decided — refresh the metric profile so the
    # fusion rank below reads the same axis set. At triage time the metrics are
    # usually not there yet; the metrics-settled boundary picks up the salience.
    refresh = getattr(owner, "refresh_metric_profile", None)
    if callable(refresh):
        try:
            refresh()
        except Exception:
            logger.debug("metric profile refresh failed", exc_info=True)
    # Cache-first, before the local Stage-2 pass: the mode and the heuristic
    # profile are known HERE, which is the identity a scorecard was written
    # under — so a known image's AI read paints immediately instead of waiting
    # for the detector pass (measured 2026-10-22: 6 large images took ~30 s
    # before the cache appeared; owner: "анализ крутится несколько секунд
    # перед тем как выдать кэш"). The settle hydrate stays as a backstop for
    # the modes/profiles that change after triage.
    hydrate = getattr(owner, "_hydrate_ai_cache", None)
    if callable(hydrate):
        try:
            hydrate(list(owner.state.items))
        except Exception:
            logger.debug("triage-commit AI-cache hydrate failed", exc_info=True)
    # Algorithms rank: measured metric fusion over each series (never the
    # old centroid order). Single choke point for both the worker and the
    # inline fast path.
    owner._apply_fusion_ranks(series, mode=mode)
    owner._emit_triage_finished("done")
    # The applied rank_source just changed (fresh fusion ranks): refresh the
    # stats-strip provenance chip. Jev is NOT triggered here — the declared
    # ``jev_rank`` gate owns ordering (the metrics-pass settle / switch).
    from tabs.image_gallery.controller import GalleryController

    GalleryController._refresh_rank_provenance(owner)
    return series


def _analysis_fingerprint(items, source) -> tuple:
    """In-RUN memo of the last Stage-2 input set (paths + mtimes + result presence).

    Deliberately NOT a durable identity: two fields are presence flags of the
    in-memory result, so it self-invalidates as soon as items are rebuilt. It
    only spares a second tail inside one run — the cross-restart decision is
    ``services/metrics_cache``'s fail-closed identity (``_local_metrics.hydrate``).
    """
    try:
        parts = []
        for it in list(items or []):
            try:
                parts.append((
                    str(getattr(it, "path", "")),
                    int(getattr(it, "mtime_ns", 0) or 0),
                    bool(getattr(it, "artifacts", None)),
                    bool(getattr(it, "metrics", None)),
                ))
            except Exception:
                continue
        parts.sort()
        return (tuple(parts), str(source) if source is not None else None)
    except Exception:
        return ((), None)


def _apply_triage_result(owner, series, source, mode) -> None:
    """Paint a triage outcome: view update + spinner off + analyses.

    Shared tail of the async worker delivery and the synchronous
    fast path — Stage-2 analyses start only when the content
    fingerprint changed since the last run.
    """
    from tabs.image_gallery.use_cases import triage_run as _triage_run

    try:
        owner.widget.set_triage(series, mode, source)
    except Exception:
        logger.debug("widget.set_triage failed", exc_info=True)
    # A1: hide toolbar scanning spinner
    try:
        # Prefer widget helper, fallback to toolbar directly
        if hasattr(owner.widget, "set_triage_done"):
            owner.widget.set_triage_done()  # type: ignore[attr-defined]
        elif hasattr(owner.widget, "toolbar") and hasattr(owner.widget.toolbar, "set_triage_done"):
            owner.widget.toolbar.set_triage_done()  # type: ignore[attr-defined]
    except Exception:
        logger.debug("toolbar.set_triage_done failed", exc_info=True)
    try:
        fingerprint = _analysis_fingerprint(
            list(owner.state.items), source
        )
    except Exception:
        fingerprint = None
    try:
        analyses_current = (
            fingerprint is not None
            and fingerprint == owner._last_analysis_fingerprint
        )
    except Exception:
        analyses_current = False
    if analyses_current:
        logger.debug("triage tail: analyses unchanged, skipping restarts")
        # Nothing to compute — retire the local "analyzing" badge now, or it
        # would stick forever (no proxy settle will fire to stamp done). The
        # metrics are already current, so this also IS the pass settle: on a
        # restored AI domain the gate ranks here (domain authority read).
        _triage_run._settle_metrics_pass(owner, list(owner.state.items))
    else:
        try:
            owner._last_analysis_fingerprint = fingerprint
        except Exception:
            pass
        # Durable identity FIRST (the fingerprint above is only an in-run memo):
        # a known folder answers every image from ``services/metrics_cache`` with
        # zero detector runs; only the misses enter the Stage-2 pass.
        try:
            missing = _local_metrics.hydrate(owner, list(owner.state.items), source, mode)
        except Exception:
            logger.debug("local metrics hydrate failed", exc_info=True)
            missing = list(owner.state.items)
        if not missing:
            logger.debug("triage tail: every item came from the local-metrics cache")
            # Nothing to compute — retire the local "analyzing" badge now (no
            # proxy settle will fire). The numbers are current, so this also IS
            # the pass settle: the rank fusion re-marks here.
            _triage_run._settle_metrics_pass(owner, list(owner.state.items))
        else:
            # Single-pass Stage 2 (Phase 2b+3): ONE shared-proxy background
            # step replaces the three whole-pool batch workers (artifact +
            # fidelity + camera). Delivered strictly by path into the
            # existing apply tails (batched repaint + quick-look hooks);
            # the per-stage entry points above stay working but the tail no
            # longer fans out through them.
            #
            # The local "done" badge is gated on this pass settling: the card's
            # quality dots (artifact severities) are produced here, so stamping
            # done earlier (on the triage result) showed "done" 1-2 s before the
            # dots recolored. Same contract as the append path
            # (``_finish_append_processing`` via ``on_done``).
            try:
                owner._start_proxy_analysis(
                    missing,
                    source,
                    mode,
                    on_done=lambda: _triage_run._settle_metrics_pass(
                        owner, list(owner.state.items)
                    ),
                )
            except Exception:
                logger.debug("proxy analysis start failed", exc_info=True)
                # Fail-open: never leave the badge stuck in "analyzing".
                _triage_run._settle_metrics_pass(owner, list(owner.state.items))
    # Stage 3: targeted tie-break for top-2 when local metrics within epsilon (badge pending)
    try:
        for ser in series or []:
            owner.run_tie_break_if_needed(ser)
    except Exception:
        logger.debug("tie-break auto-run failed", exc_info=True)


def _on_triage_error(owner, error_info: object, gen: int | None = None) -> None:
    if gen is not None and not owner._is_current_folder_gen(gen):
        return
    logger.debug("triage worker error: %r", error_info, exc_info=True)
    setattr(owner.state, "triage_state", TriageState.ERROR)
    owner._emit_triage_finished("error")
    try:
        owner.widget.set_triage([], None, None)
    except Exception:
        pass
