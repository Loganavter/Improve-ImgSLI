"""Presenter for the Image Gallery tab: folder scan, thumbnails, Stage 3 VLM (tie-break + briefs).
Audit-Meta: pattern=state-machine size=exempt reason="one controller lifecycle — folder scan/thumbnail/triage/VLM sharing GenericWorker state"

Pass 2 VLM is optional, targeted, always via GenericWorker (never UI-blocking).
Unresolved tie-breaks degrade silent-but-visible: pending badge cleared,
local ranking kept.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, QThreadPool, QTimer, Signal
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.use_cases import pipeline_stages as _pipeline_stages

from tabs.image_gallery.models import (
    ActivityPhase,
    AnalysisStatus,
    GalleryItem,
    GalleryState,
    Mode,
    Series,
    TriageState,
)
from tabs.image_gallery.services.activity import clear_activity, set_activity
from tabs.image_gallery.services.ai_cache import save_analysis  # noqa: F401
from tabs.image_gallery.services.ai_client import _ai_debug
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
from tabs.image_gallery.debug import (
    gallery_artifacts_disabled as _artifacts_disabled,
)
from tabs.image_gallery.debug import (
    gallery_camera_disabled as _camera_disabled,
)
from tabs.image_gallery.debug import (
    gallery_fidelity_disabled as _fidelity_disabled,
)
from tabs.image_gallery.services.filtering import filter_items

# Re-exported monkeypatch seam: the scheduler reads this from the controller
# module at call time (``test_pipeline_scheduler`` patches it here).
from tabs.image_gallery.services.thumbnail_cache import (  # noqa: F401
    render_and_cache_thumbnail,
)

logger = logging.getLogger("ImproveImgSLI")


class _ActivityPhaseBridge(QObject):
    """Worker-thread phase emits → UI-thread callback (queued connection).

    Created on the UI thread, so the ``_relay`` slot runs there even though
    ``phase`` is emitted from the analysis worker.
    """

    phase = Signal(str)

    def __init__(self, on_phase) -> None:
        super().__init__()
        self._on_phase = on_phase
        self.phase.connect(self._relay)

    def _relay(self, value: str) -> None:
        self._on_phase(value)


# Stage 3: epsilon for local metric tie — when top-2 within this delta, VLM tie-break applies.
# Mirrors design.md Pass 2 "when local metrics are within epsilon".
TIE_EPSILON = 0.025  # embedding distance normalized; tuned for 8×8 HSV vectors

# S2 append-attach threshold for joining the nearest EXISTING series.
# Consumed by S1 centroid ``attach_items`` (embedding-distance gate with
# the same threshold rule as ``cluster_items``); the attach path never
# clusters, it only measures against live series.
_ATTACH_THRESHOLD = 10

# S2 tail-cluster bound: regrouping the UNGROUPED tail after an append
# runs inline on the GUI thread. Signatures come from the perceptual cache
# (only genuinely new files decode), but the pairwise pass itself is
# O(n^2) arithmetic — past this many tail candidates the drop would jank,
# so huge tails stay manual ("Re-cluster series" from the header menu).
_TAIL_CLUSTER_LIMIT = 1000

# -- Bounded gallery scheduler (Phase 2b+3) --------------------------------
# Measured Phase-0 waste: open_folder queued N thumbnail workers + the
# triage tail fanned out three whole-pool batch workers, all on
# QThreadPool.globalInstance() — 500 files ≈ 40x oversubscription,
# off-screen items decoded first, each stage re-decoding every file.
# One scheduler owns gallery concurrency: a DEDICATED QThreadPool (never
# the process-wide globalInstance) plus the single frozen entry
# ``GalleryController.schedule(items, priority)``. Lane reservation is by
# priority only: visible thumbs > batch (triage + proxy chunks) >
# background thumbs — finite lanes, so neither lane starves the other.
VISIBLE_THUMB_PRIORITY = 4
TRIAGE_PRIORITY = 2
PROXY_BATCH_PRIORITY = 2
BACKGROUND_THUMB_PRIORITY = 0

# Dedicated pool sizing over os.cpu_count(): floor 4 so a small folder
# still overlaps thumb decode + triage + proxy batch + one VLM call
# without serializing single-item latency; cap 8 because PIL decodes are
# CPU-bound (no gain past cores) and each in-flight proxy holds <= ~3 MB
# plus thumb decode buffers — more threads only grow peak RSS against
# the pool budget shared with the rest of the app.
_GALLERY_SCHED_MIN_THREADS = 4
_GALLERY_SCHED_MAX_THREADS = 8

# Batch analysis chunking: one proxy worker per 50 items (500 files = 10
# workers, not 500). Progress surfaces through the existing
# toolbar/background-scanning hooks only when multi-chunk.
_GALLERY_PROXY_CHUNK = 50

# -- AI-domain ranker lifecycle (S2/J1, plan-gallery-jev-pipeline) -----------
#: Declared gallery stage for the AI-domain series ranker. Its declared input is
#: the settled measured-metrics pass; the controller drives Jev ONLY from that
#: settle (and the explicit domain switch), and the single-flight gate dedups.
#: Declared here as data (never a scheduling framework — see
#: ``use_cases/pipeline_stages``); Jev is never triggered at triage commit nor
#: per metrics chunk.
_JEV_STAGE = "jev_rank"
_pipeline_stages.register_stage(_JEV_STAGE, requires=("metrics_ready",))

# -- Metric-profile stage (P2, plan-adaptive-metric-profiles-2026-10-17) -----
#: Declared gallery stage for the VLM metric-profile selector. Its declared
#: input is the settled measured-metrics pass (the salience/probe input); the
#: controller drives it ONLY from that settle, and the single-flight gate
#: dedups. The heuristic profile ``refresh_metric_profile`` stores FIRST stays
#: the fail-open fallback (plan §Fallback); the selector may only REPLACE it
#: with a ``source="vlm"`` profile once it answers.
_PROFILE_STAGE = "metric_profile"
_pipeline_stages.register_stage(_PROFILE_STAGE, requires=("metrics_ready",))


def _profile_selector():
    """Indirection to the P2 VLM profile selector (never imported at load time).

    Returns ``use_cases.profile_ai.choose_profile_sync``. A module-level
    function (not a method) so the controller module never imports the
    selector lane at import time — the selector module may be absent — and so
    tests monkeypatch this ONE seam instead of importing that lane's module.
    Raises when the selector is unavailable; the kick treats that as fail-open.
    """
    from tabs.image_gallery.use_cases.profile_ai import choose_profile_sync

    return choose_profile_sync


# Proxy decode-cache bound: owned by services/proxy.py (PROXY_CACHE_LIMIT);
# batch delivery trims oldest-inserted entries down to that bound (96 x
# <= ~3 MB ~= <= 288 MB while covering a typical folder's working set;
# insertion order is a cheap LRU stand-in — warm hits are not reordered,
# folder churn evicts). Never restate the literal here.


# -- Bounded gallery scheduler (Phase 2b+3): bodies in use_cases/scheduler.py.
# The dedicated pool factory + the scheduler helpers are re-exported here so
# existing imports (``from tabs.image_gallery.controller import
# _scheduler_thread_count``) keep resolving; the method names below stay on
# the class as thin delegators (frozen ``schedule`` seam).
from tabs.image_gallery.use_cases.scheduler import (  # noqa: E402,F401
    _new_gallery_pool,
    _scheduler_thread_count,
)


class GalleryController:
    def __init__(self, widget, *, thread_pool: QThreadPool | None = None, context=None):
        self.widget = widget
        self.state = GalleryState()
        # Single authoritative judgment domain (Algorithms vs AI). ``state`` is
        # REPLACED by open_folder/append/clear_to_empty, so the domain must NOT
        # live there; ``state``/widget are read-only projections (see
        # plan-gallery-jev-pipeline-2026-10-15 S1).
        self._judgment_domain = "algorithms"
        # Folder generation whose METRICS pass has settled. The winner (★ BEST)
        # is only marked after settle — before that the fusion rank is
        # provisional and marking it put BEST on a random leader too early.
        self._metrics_settled_gen = -1
        # S2/J1: single-flight + completed ledger for the declared stages,
        # scoped by folder generation. Per controller, so two live copies (or
        # two tests) never share a key; the AI-domain Jev batch is the only
        # registrant today.
        self._stage_gate = _pipeline_stages.StageGate()
        # Manual series overrides (Wave B): controller-local
        # ``dict[str(path), series_id | None]`` — None = forced UNGROUPED.
        # In-memory only (no cross-restart persistence, explicitly out of
        # scope). Applied as a post-pass after every cluster_items result
        # (see _run_triage_sync / _on_triage_ready); override wins over the
        # computed series_id. Read by the triage worker via an explicit
        # snapshot argument (never by implied lookup).
        self._series_overrides: dict[str, str | None] = {}
        # S2 stable-id counter: every seed cluster run assigns fresh
        # ``series_<n>`` ids from here IN ORDER (see
        # ``_assign_fresh_stable_ids`` — the S1 swap point). Never reused,
        # never reset except on folder replace (fresh world: ``open_folder``
        # / ``open_paths(replace=True)``). Moves keep target ids verbatim
        # and never touch the counter.
        self._series_next_id = 1
        self._series_id_lock = threading.Lock()
        # Series-view generation: bumped by every sync view rewrite (move,
        # append-attach) so a triage worker that started earlier drops its
        # delivery in ``_on_triage_ready`` instead of clobbering the newer
        # manual arrangement (mirrors ``_folder_gen`` for folder switches).
        self._series_gen = 0
        self._thread_pool = thread_pool or _new_gallery_pool()
        self._context = context
        self._ai_settings_store = AiSettingsStore()
        # Ask AI (A4): in-session answer cache keyed by
        # scope-identity + question + backend + model (re-open serves cache).
        self._ask_cache: dict[str, object] = {}
        # Generation tokens against async races: bumped on every folder switch
        # (open_folder/open_paths). Late triage/artifact/thumbnail/VLM results
        # carrying a stale generation are dropped, never applied to the new
        # folder's items. Filter keystrokes get their own token so a slow
        # brief-disk worker cannot resurrect an outdated query.
        self._folder_gen = 0
        self._filter_gen = 0
        self._pending_filter_text = ""
        self._filter_timer = None
        # Wave-2 (plan-gallery-redux): slot-backed pool mirror. Rich local
        # state (QPixmap caches, LOADING flags, workers, VLM streams) stays
        # on self.state / self.widget; pool membership, selection, filter and
        # triage-finish additionally dispatch GALLERY_* actions with scope
        # 'gallery' whenever a store/dispatcher is available. Storeless unit
        # contexts (context=None) keep pure-local behavior, verbatim.
        self._pending_thumb_ready: list[tuple[str, str]] = []
        self._thumb_flush_scheduled = False
        # Card-repaint coalescing: thumbnail deliveries used to call
        # widget.refresh_card per item, each re-sweeping selection over the
        # whole grid (O(N) repaints per delivery → stalled UI thread while
        # quick look is open). Repaints accumulate here (path → item) and
        # flush once per tick via refresh_cards (single selection sweep).
        self._pending_card_items: dict[str, object] = {}
        self._card_flush_scheduled = False
        #: Coalesces AI-domain Jev re-ranks triggered by arriving analyses.
        self._ai_rank_flush_scheduled = False
        self._subscribed_gallery_store = None
        # Session isolation (Wave ISO): this live copy addresses its OWN
        # session id for every slot read — never the active session per
        # read. The tab binds authoritatively via bind_gallery_session
        # (create_page / on_active_session_changed / on_activated); the
        # constructor capture below is a best-effort fallback only.
        self._gallery_session_id: str | None = None
        try:
            self._gallery_session_id = self._capture_initial_gallery_session_id()
        except Exception:
            self._gallery_session_id = None
        # Own-dispatch accounting: dispatch → emit is synchronous, so each
        # successful _emit/_transact arms one light (no-op) reconcile; any
        # other 'gallery' emit (undo, widget gestures, external replace)
        # takes the authoritative branch. This keeps newer local scalars
        # (triage RUNNING, VLM crowns) safe from stale-slot clobbering.
        self._own_gallery_emits = 0
        # Stage-2 analysis fingerprint: artifact/fidelity/camera analyses
        # are keyed by content — re-running them over an unchanged pool
        # (e.g. regroup after tab return) recomputes identical results.
        # The triage tail skips analysis starts when the fingerprint
        # (paths + mtimes + metrics presence) matches the last run.
        self._last_analysis_fingerprint: object = None
        self._ensure_gallery_subscription()
        # -- bounded scheduler (Phase 2b+3): counters, background queue --
        self._sched_lock = threading.Lock()
        self._sched_pending = 0  # accepted-but-unfinished pool workers
        self._sched_active = 0  # actually executing (tracked wrapper)
        self._sched_peak = 0  # max _sched_active observed (tests)
        self._bg_queue: list[tuple[object, int]] = []  # paused (item, gen)
        self._bg_paused = False
        self._thumb_inflight: set[str] = set()  # str(path) with a live worker
        self._proxy_done = 0
        self._proxy_total = 0
        self._visibility_pause_filter = None
        self._subscribe_visible_range()
        self._install_visibility_pause()

        widget.folder_pick_requested.connect(self._on_pick_folder)
        widget.analyze_requested.connect(self.analyze_item_by_path)
        widget.filter_text_changed.connect(self.set_filter_text)
        # Explicit owner: the widget attaches this controller via
        # ImageGalleryWidget.attach_controller (G2); the controller keeps
        # self.widget from its constructor only — no back-pokes here.

    def _next_folder_gen(self) -> int:
        """Bump the folder generation: all in-flight workers go stale."""
        self._folder_gen += 1
        # Fresh world: the winner marker is not settled for the new folder.
        self._metrics_settled_gen = -1
        # Fresh world: the declared-stage ledger is invalidated — a completed
        # ``jev_rank`` fingerprint from the previous folder must never block the
        # new folder's pass (S2/J1).
        try:
            gate = getattr(self, "_stage_gate", None)
            if gate is not None:
                gate.invalidate()
        except Exception:
            logger.debug("stage gate invalidate failed", exc_info=True)
        # Fresh world: drop paused background entries — even if one were
        # started it could never be delivered (gen check is the backstop).
        try:
            queue = getattr(self, "_bg_queue", None)
            if isinstance(queue, list):
                queue.clear()
        except Exception:
            pass
        return self._folder_gen

    def clear_to_empty(self) -> None:
        """Reset the local mirror + view for a session with no pool data.

        Slot-authoritative clear (session-isolation contract): the slot is
        already empty, so no dispatch — nothing to persist. Bumps the folder
        generation so in-flight thumbnail/triage/artifact/VLM workers for
        the previous pool go stale and are dropped instead of repopulating
        the fresh session's view.
        """
        self._next_folder_gen()
        self.state = GalleryState()
        try:
            self.widget.reset_session_view()
        except Exception:
            logger.debug("gallery clear_to_empty view reset failed", exc_info=True)

    def _is_current_folder_gen(self, gen: int) -> bool:
        return gen == self._folder_gen

    # -- bounded scheduler (Phase 2b+3; frozen seam: schedule) --------------

    def schedule(self, items, priority: int, *, op: str = "thumb", source=None, gen: int | None = None, wanted=None, include_camera: bool | None = None, full_res_artifacts: bool = False, on_done=None) -> int:
        """Thin delegator to ``use_cases.scheduler.schedule`` (frozen seam)."""
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler.schedule(self, items, priority, op=op, source=source, gen=gen, wanted=wanted, include_camera=include_camera, full_res_artifacts=full_res_artifacts, on_done=on_done)

    def sched_stats(self) -> dict:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler.sched_stats(self)

    def _tracked(self, fn):
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._tracked(self, fn)

    def _pool_start(self, worker, priority: int | None) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._pool_start(self, worker, priority)

    def _on_sched_finished(self) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._on_sched_finished(self)

    def _schedule_thumbs(self, items: list, priority: int, gen: int) -> int:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._schedule_thumbs(self, items, priority, gen)

    def _begin_folder_schedule(self, items: list, gen: int) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._begin_folder_schedule(self, items, gen)

    def _subscribe_visible_range(self) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._subscribe_visible_range(self)

    def _on_visible_range_changed(self, paths: object) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._on_visible_range_changed(self, paths)

    def _install_visibility_pause(self) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._install_visibility_pause(self)

    def pause_background(self) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler.pause_background(self)

    def resume_background(self) -> None:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler.resume_background(self)

    def _trim_proxy_cache(self) -> int:
        from tabs.image_gallery.use_cases import scheduler as _scheduler

        return _scheduler._trim_proxy_cache(self)

    # -- gallery slot (Wave-2 Redux; scope 'gallery') -------------------------

    def _gallery_store(self):
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._gallery_store(self)

    def _ensure_gallery_subscription(self) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._ensure_gallery_subscription(self)

    def bind_gallery_session(self, session_id: str | None) -> None:
        """Thin delegator to ``use_cases.gallery_slot.bind_gallery_session``."""
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot.bind_gallery_session(self, session_id)

    def _capture_initial_gallery_session_id(self) -> str | None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._capture_initial_gallery_session_id(self)

    def _is_active_gallery_tab(self) -> bool:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._is_active_gallery_tab(self)

    def _gallery_slot(self):
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._gallery_slot(self)

    def _emit_gallery(self, action) -> bool:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._emit_gallery(self, action)

    def _transact_gallery(self, actions) -> bool:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        return _gallery_slot._transact_gallery(self, actions)

    def _on_store_changed(self, scope: str) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._on_store_changed(self, scope)

    def _sync_from_slot(self) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._sync_from_slot(self)

    def refresh_metric_profile(self) -> object:
        """Derive the metric profile from the live state and store it (plan P1).

        The **producer** half of the profile seam: derived from ``self.state``
        (mode + the folder's measured metrics) via the pure
        ``use_cases.profile_select.derive_for_state``, then stored on the state
        so the rank fusion and the Jev measured vector read ONE axis set. Called
        at every site where ``state.mode`` is (re)decided and at the
        metrics-settled boundary — the metrics are the salience input, so the
        content-aware axes cannot be derived before they exist. Returns the
        stored profile. Never raises: a derivation failure keeps the previous
        value (or ``None``), so consumers fall back to the mode mapping
        (fail-open, plan §Fallback).
        """
        try:
            from tabs.image_gallery.use_cases.profile_select import (
                derive_for_state,
                describe,
            )

            profile = derive_for_state(self.state)
            try:
                previous = getattr(self.state, "metric_profile", None)
            except Exception:
                previous = None
            # Store the raw derived profile verbatim (a successful derivation
            # is always a usable ``MetricProfile``, even with no salience).
            self.state.metric_profile = profile
            if profile != previous:
                logger.debug("[gallery] metric profile: %s", describe(self.state))
            return profile
        except Exception:
            logger.debug("metric profile refresh failed", exc_info=True)
            try:
                return getattr(self.state, "metric_profile", None)
            except Exception:
                return None

    def clear_metric_profile(self) -> None:
        """Invalidate the stored metric profile (folder changed — plan P1).

        Consumers fall back to the mode mapping (``profile_select.active_profile``)
        until the next ``refresh_metric_profile`` derivation. Never raises.
        """
        try:
            from tabs.image_gallery.use_cases.profile_select import describe

            try:
                previous = getattr(self.state, "metric_profile", None)
            except Exception:
                previous = None
            self.state.metric_profile = None
            if previous is not None:
                logger.debug("[gallery] metric profile: %s", describe(self.state))
        except Exception:
            logger.debug("metric profile clear failed", exc_info=True)

    # -- VLM metric-profile selector (P2, plan-adaptive-metric-profiles) -----

    def _run_profile_select_on_settle(self) -> None:
        """Kick the VLM metric-profile selector from the metrics-settled boundary.

        Declared stage ``_PROFILE_STAGE``, gated on the settled measured-metrics
        pass (the same metrics_ready input ``_JEV_STAGE`` declares): the
        salience/probe input is the measured-metrics pass that just settled, so
        this is the only place the selector is driven from. The heuristic
        profile ``refresh_metric_profile`` already stored is the fail-open
        fallback (plan §Fallback) — this kick may only REPLACE it with a
        ``source="vlm"`` profile once the selector answers. Never raises and
        never blocks the UI thread: unavailable selector / AI not usable / <2
        items → a no-op; the single-flight gate dedups a second settle for the
        same ``(stage, folder_gen)``.
        """
        try:
            factory = getattr(self, "_profile_selector", None)
            if not callable(factory):
                factory = _profile_selector  # module-level default seam
            selector = factory() if callable(factory) else None
        except Exception:
            logger.debug("metric profile selector unavailable", exc_info=True)
            selector = None
        if not callable(selector):
            return
        try:
            items = [it for it in list(getattr(self.state, "items", None) or [])]
        except Exception:
            items = []
        if len(items) < 2:
            _ai_debug("metric profile skip: %d item(s) (<2) — nothing to select", len(items))
            return
        try:
            settings = self._ai_settings_store.load()
        except Exception:
            settings = None
        if (
            settings is None
            or not getattr(settings, "enabled", False)
            or not getattr(settings, "base_url", "")
            or not getattr(settings, "api_key", "")
        ):
            _ai_debug("metric profile skip: AI not configured (items=%d)", len(items))
            return
        mode = getattr(self.state, "mode", None)
        gen = self._folder_gen
        # Content key: the folder generation + member count is enough to make
        # two settles over the same folder one single-flight pass (the selector
        # lane pins the full content fingerprint in its own cache).
        fingerprint = f"{gen}:{len(items)}"
        gate = getattr(self, "_stage_gate", None)
        claimed = True
        if gate is not None:
            try:
                claimed = bool(gate.begin(_PROFILE_STAGE, gen, fingerprint))
            except Exception:
                claimed = True
        if not claimed:
            _ai_debug("metric profile: gate skip (selected/in flight) gen=%s", gen)
            return
        snapshot = list(items)
        released = {"done": False}

        def _release(ok: bool) -> None:
            """Release the stage gate exactly once (idempotent, never raises)."""
            if released["done"]:
                return
            released["done"] = True
            try:
                if gate is not None:
                    gate.finished(_PROFILE_STAGE, gen, ok=bool(ok))
            except Exception:
                logger.debug("metric profile gate finished failed", exc_info=True)

        def _job():
            # The selector lane owns probe + one pinned VLM call + cache; the
            # wiring passes only the settled items, the mode and the settings.
            return selector(snapshot, mode=mode, settings=settings)

        worker = GenericWorker(_job)

        def _on_result(profile, gen=gen):
            if not self._is_current_folder_gen(gen):
                _release(True)  # stale scope: release the gate, apply nothing
                return
            self._apply_profile_outcome(profile, gen)
            _release(True)

        def _on_error(error_info, gen=gen):
            if not self._is_current_folder_gen(gen):
                _release(True)
                return
            logger.debug("metric profile selector error: %r", error_info, exc_info=True)
            # A fault keeps the fingerprint retryable (ok=False).
            _release(False)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        # A None reply emits no ``result``: the job's benign non-answer still
        # completes the stage so a re-settle over the same folder is a no-op.
        worker.signals.finished.connect(lambda: _release(True))
        try:
            self._pool_start(worker, None)
        except Exception:
            logger.debug("metric profile worker launch failed", exc_info=True)
            _release(False)  # never strand the gate in flight
            return
        _ai_debug("metric profile: select scheduled (items=%d gen=%s)", len(items), gen)

    def _apply_profile_outcome(self, profile, gen: int) -> None:
        """Apply a VLM-selected metric profile (P2) or keep the heuristic.

        Drops a stale result (the folder changed). A usable profile — any
        object with a non-empty ``axis_ids``, canonically a ``MetricProfile``
        with ``source="vlm"`` — is stored on the SAME ``state.metric_profile``
        slot the P1 producer writes, the existing ``[gallery]``/``[ai]``
        profile line is emitted (naming ``source=vlm`` and the salient axes),
        and the cards are refreshed like the neighbouring apply-tails. A
        missing/hollow profile is a no-op: the heuristic profile
        ``refresh_metric_profile`` stored FIRST remains (fail-open).
        """
        if not self._is_current_folder_gen(gen):
            return
        try:
            axis_ids = tuple(getattr(profile, "axis_ids", None) or ())
        except Exception:
            axis_ids = ()
        if not axis_ids:
            return
        try:
            self.state.metric_profile = profile
        except Exception:
            logger.debug("metric profile store failed", exc_info=True)
            return
        try:
            from tabs.image_gallery.use_cases.profile_select import describe

            line = describe(self.state)
            logger.debug("[gallery] metric profile: %s", line)
            _ai_debug("metric profile: %s", line)
        except Exception:
            logger.debug("metric profile describe failed", exc_info=True)
        try:
            items = [it for it in list(getattr(self.state, "items", None) or [])]
        except Exception:
            items = []
        try:
            self.widget.refresh_cards(items)
        except Exception:
            for it in items:
                try:
                    self.widget.refresh_card(it)
                except Exception:
                    pass

    def _apply_fusion_ranks(self, series, *, mode=None) -> None:
        """(Re)derive every series rank from the measured metric fusion.

        Single rank-assignment primitive for the Algorithms domain
        (plan-gallery-rank-backends-2026-10-15): a series is ranked by
        ``rank_fusion.rank_series`` over its members — a pure function of the
        measured quality axes, never of the HSV centroid, arrival order or
        mtime. Called on every automatic regroup/reconcile path.

        Items whose rank is an explicit user decision — ``rank_source ==
        "manual"`` or a live ``triage_best`` winner from Keep/Make best — keep
        their stored rank and are never silently re-derived; so does a
        ``rank_source == "jev"`` item while ``state.rank_domain == "ai"`` (the
        AI domain owns that rank; flipping back to Algorithms clears it). The
        other members fill the free slots in fusion order. Ungrouped items are
        unranked (``rank``/``rank_source`` cleared) unless explicitly fixed.
        Never raises.
        """
        try:
            from tabs.image_gallery.services.rank_fusion import rank_series as _rank
        except Exception:
            return
        if mode is None:
            mode = getattr(self.state, "mode", None)
        try:
            groups = list(series or ())
        except Exception:
            groups = []

        def _locked(m) -> bool:
            """True when the item's rank is an explicit user decision, or a Jev
            rank the active AI domain owns (plan R3)."""
            try:
                if getattr(m, "rank", None) is None:
                    return False
                if (
                    getattr(m, "rank_source", None) == "manual"
                    or bool(getattr(m, "triage_best", False))
                ):
                    return True
                # AI domain: a Jev rank is the domain's ranker — a fusion
                # regroup must not silently re-derive it. Flipping back to the
                # Algorithms domain clears this and fusion re-derives.
                return (
                    getattr(m, "rank_source", None) == "jev"
                    and str(getattr(self, "_judgment_domain", "algorithms") or "")
                    == "ai"
                )
            except Exception:
                return False

        members_of = GalleryController._section_members
        ranked_ids: set[int] = set()
        for entry in groups:
            members = members_of(entry)
            if not members:
                continue
            for m in members:
                ranked_ids.add(id(m))
            try:
                # The STORED metric profile (plan P1) selects the axes — the
                # same set the dots, the prompt and the Jev vector read. Without
                # one this is the mode mapping (fail-open).
                ranks = _rank(
                    members,
                    mode=mode,
                    profile=getattr(self.state, "metric_profile", None),
                )
            except Exception:
                ranks = {}

            def _fusion_rank(m, _ranks=ranks):
                try:
                    r = _ranks.get(str(getattr(m, "path", "")))
                except Exception:
                    r = None
                try:
                    return int(r) if r is not None else 1 << 30
                except Exception:
                    return 1 << 30

            def _path_of(m):
                try:
                    return str(getattr(m, "path", ""))
                except Exception:
                    return ""

            ordered = sorted(members, key=lambda m: (_fusion_rank(m), _path_of(m)))
            taken: set[int] = set()
            for m in members:
                if _locked(m):
                    try:
                        taken.add(int(m.rank))
                        # Preserve the owning source: a Jev rank stays "jev"
                        # on the AI domain; a user pick is "manual".
                        src = getattr(m, "rank_source", None)
                        m.rank_source = src if src in ("manual", "jev") else "manual"  # type: ignore[attr-defined]
                    except Exception:
                        pass
            nxt = 1
            for m in ordered:
                if _locked(m):
                    continue
                while nxt in taken:
                    nxt += 1
                try:
                    m.rank = nxt
                    m.rank_source = "fusion"
                    # The ★ BEST winner is marked ONLY when the ranking is FINAL:
                    # after the metrics pass settled, by the ACTIVE ranker —
                    # Algorithms' fusion rank 1 here; the AI domain leaves it to
                    # Jev. Before settle, no winner is marked (a provisional
                    # fusion leader must never show BEST).
                    _settled = False
                    try:
                        _settled = int(getattr(self, "_metrics_settled_gen", -1)) == int(
                            getattr(self, "_folder_gen", 0)
                        )
                    except Exception:
                        _settled = False
                    _ai = (
                        str(getattr(self, "_judgment_domain", "algorithms") or "")
                        .strip()
                        .lower()
                        == "ai"
                    )
                    m.is_best = bool(_settled and not _ai and nxt == 1)
                except Exception:
                    pass
                taken.add(nxt)
                nxt += 1
        # Ungrouped items are unranked — a missing measurement never becomes
        # a fabricated number.
        try:
            live = list(getattr(self.state, "items", []) or ())
        except Exception:
            live = []
        for it in live:
            if id(it) in ranked_ids:
                continue
            if _locked(it):
                continue
            try:
                it.rank = None
                it.rank_source = None
                it.is_best = False
            except Exception:
                pass
        GalleryController._refresh_ranks_visible(self)

    def _refresh_ranks_visible(self) -> None:
        """Ranks/BEST render only once the ranking is FINAL for this folder.

        Final = the metrics pass settled for the current folder generation AND
        no analysis is in flight (no ``analysis_status == PENDING`` item). Until
        then ``widget.set_ranks_visible(False)`` blanks the rank/BEST pill on
        every surface (card/strip/list) at the single badge-stamp point — a
        provisional ``#N`` or a premature ``★ BEST`` is never shown. Never raises.
        """
        try:
            settled = int(getattr(self, "_metrics_settled_gen", -1)) == int(
                getattr(self, "_folder_gen", 0)
            )
        except Exception:
            settled = False
        pending = False
        try:
            for it in list(getattr(self.state, "items", None) or []):
                if getattr(it, "analysis_status", None) == AnalysisStatus.PENDING:
                    pending = True
                    break
        except Exception:
            pending = False
        setter = getattr(getattr(self, "widget", None), "set_ranks_visible", None)
        if callable(setter):
            try:
                setter(bool(settled and not pending))
            except Exception:
                pass

    def _apply_slot_ranks(self, slot) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._apply_slot_ranks(self, slot)

    def _apply_slot_selection_filter(self, slot) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._apply_slot_selection_filter(self, slot)

    def _apply_slot_triage_scalars(self, slot) -> None:
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot._apply_slot_triage_scalars(self, slot)

    def set_selection(self, paths) -> None:
        """Thin delegator to ``use_cases.gallery_slot.set_selection``."""
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot.set_selection(self, paths)

    def set_source(self, path: Path) -> None:
        """Thin delegator to ``use_cases.gallery_slot.set_source``."""
        from tabs.image_gallery.use_cases import gallery_slot as _gallery_slot

        _gallery_slot.set_source(self, path)

    # -- coalesced thumbnail completions (ONE action per event-loop turn) -----

    def _queue_thumb_ready(self, path: Path, status: str) -> None:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        _cc._queue_thumb_ready(self, path, status)

    def _flush_pending_thumbnails(self) -> None:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        _cc._flush_pending_thumbnails(self)

    def flush_pending_thumbnails(self) -> None:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        _cc.flush_pending_thumbnails(self)

    def _queue_card_refresh(self, item) -> None:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        _cc._queue_card_refresh(self, item)

    def _flush_pending_card_refresh(self) -> None:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        _cc._flush_pending_card_refresh(self)

    def _emit_triage_finished(self, triage_state: str, source_path=None) -> bool:
        from tabs.image_gallery.use_cases import completion_coalescing as _cc

        return _cc._emit_triage_finished(self, triage_state, source_path)

    # -- folder loading ----------------------------------------------------

    def open_folder(self, folder: Path) -> None:
        """Thin delegator to ``use_cases.folder_loading.open_folder``."""
        from tabs.image_gallery.use_cases import folder_loading as _folder_loading

        _folder_loading.open_folder(self, folder)

    def open_paths(self, paths: list[Path], *, replace: bool = False) -> None:
        """Thin delegator to ``use_cases.folder_loading.open_paths``."""
        from tabs.image_gallery.use_cases import folder_loading as _folder_loading

        _folder_loading.open_paths(self, paths, replace=replace)

    def _on_pick_folder(self) -> None:
        """Thin delegator to ``use_cases.folder_loading._on_pick_folder``."""
        from tabs.image_gallery.use_cases import folder_loading as _folder_loading

        _folder_loading._on_pick_folder(self)

    def _find_item(self, path: Path) -> GalleryItem | None:
        for item in self.state.items:
            if item.path == path:
                return item
        return None

    # -- thumbnails ----------------------------------------------------------

    def _load_thumbnail(self, item: GalleryItem, *, priority: int | None = None) -> None:
        from tabs.image_gallery.use_cases import thumbnails as _thumbnails

        _thumbnails._load_thumbnail(self, item, priority=priority)

    def _on_thumbnail_ready(self, path: Path, cache_path: Path | None, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import thumbnails as _thumbnails

        _thumbnails._on_thumbnail_ready(self, path, cache_path, gen)

    def _on_thumbnail_error(self, path: Path, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import thumbnails as _thumbnails

        _thumbnails._on_thumbnail_error(self, path, gen)

    # -- AI analyze -----------------------------------------------------------

    def _tr(self, key: str, default: str) -> str:
        context = self._context
        if context is not None:
            return context._tr(key, default)
        return default

    def analyze(self, ctx):
        """Analyze every ``ctx.targets`` card on ``ctx.backend`` (ONE entry)."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.analyze(self, ctx)

    def reanalyze(self, ctx):
        """Force a fresh analysis of ``ctx.targets`` (cache bypass)."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.reanalyze(self, ctx)

    def analyze_item_by_path(self, path: Path):
        """Deprecated point adapter — builds ``targets=(path,)`` and analyzes."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.analyze_item_by_path(self, path)

    def hydrate_cached_analysis(self, item: GalleryItem, *, ctx=None) -> bool:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.hydrate_cached_analysis(self, item, ctx=ctx)

    def _hydrate_ai_cache(self, items, *, ctx=None) -> int:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._hydrate_ai_cache(self, items, ctx=ctx)

    def analyze_item(self, item: GalleryItem):
        """Deprecated point adapter — builds ``targets=(item.path,)``."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.analyze_item(self, item)

    def reanalyze_item_by_path(self, path: Path):
        """Deprecated point adapter — builds ``targets=(path,)``."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.reanalyze_item_by_path(self, path)

    def reanalyze_item(self, item: GalleryItem):
        """Deprecated point adapter — builds ``targets=(item.path,)``."""
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.reanalyze_item(self, item)

    #: Lazy-AI cap: the domain switch analyzes only the VISIBLE items, bounded
    #: so flipping to AI never turns into a whole-folder API flood.
    _AI_VISIBLE_CAP = 12

    def _set_judgment_domain(self, domain: str) -> str:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._set_judgment_domain(self, domain)

    def activate_judgment_domain(self, domain: str) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis.activate_judgment_domain(self, domain)

    def _run_ai_for_visible(self) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._run_ai_for_visible(self)

    # -- AI domain ranker: Jev (TypeSafe System One) -----------------------

    def _run_jev_ranks(self) -> None:
        """Schedule ONE Jev rank batch on the AI domain (declared-readiness gate).

        The AI domain is a durable view setting: after the measured-metrics pass
        for a folder settles, each series with **≥2 members carrying an applicable
        MEASURED vector** is ranked once from its complete vector. Driven from the
        pass settle (``_settle_metrics_pass``) and the explicit domain switch —
        the single-flight gate dedups, so a second trigger over unchanged inputs
        is a no-op. The domain is read from the DURABLE authority
        (``_judgment_domain``), never ``state`` (replaced by open_folder/append/
        clear_to_empty), so a restored ``ai`` domain ranks too.

        Bounded lazy-AI rule (unchanged): only series with a currently-visible
        member are picked and the count is capped, so an AI-domain switch never
        floods the API. ``services.jev_cache`` pins each series, so a re-run over
        unchanged paths+mtimes+payload costs no second request.
        """
        if str(getattr(self, "_judgment_domain", "algorithms") or "").strip().lower() != "ai":
            return
        try:
            groups = list(getattr(self.state, "series", None) or [])
        except Exception:
            groups = []
        if not groups:
            _ai_debug("jev ranks: no series — nothing to rank")
            return
        mode = getattr(self.state, "mode", None)
        try:
            vis = getattr(self.widget, "visible_paths", None)
            visible = vis() if callable(vis) else None
        except Exception:
            visible = None
        try:
            vkeys = {str(p) for p in (visible or [])}
        except Exception:
            vkeys = set()
        small = hidden = no_metrics = 0
        ready: list = []
        for entry in groups:
            members = GalleryController._section_members(entry)
            if len(members) < 2:
                small += 1
                continue
            if vkeys and not any(str(getattr(m, "path", "")) in vkeys for m in members):
                hidden += 1
                continue
            # Readiness is the APPLICABLE MEASURED VECTOR, not "any metrics":
            # an axis Jev cannot score (or a non-applicable axis for this mode)
            # must not earn a call, and a <2-scored series would only abstain.
            vector = GalleryController._jev_measured_vector(
                members,
                mode,
                str(getattr(self, "_judgment_domain", "algorithms")),
                profile=getattr(self.state, "metric_profile", None),
            )
            if GalleryController._jev_scored_count(vector) < 2:
                no_metrics += 1
                continue
            if len(ready) >= self._AI_VISIBLE_CAP:
                break
            ready.append((members, vector))
        if not ready:
            _ai_debug(
                "jev ranks: series=%d scheduled=0 (too-small=%d not-visible=%d no-metrics=%d)",
                len(groups), small, hidden, no_metrics,
            )
            return
        scope = self._folder_gen
        fingerprint = GalleryController._jev_series_fingerprint(ready, mode)
        gate = getattr(self, "_stage_gate", None)
        claimed = True
        if gate is not None:
            try:
                claimed = bool(gate.begin(_JEV_STAGE, scope, fingerprint))
            except Exception:
                claimed = True
        if not claimed:
            _ai_debug("jev ranks: gate skip (already ranked/in flight) series=%d", len(ready))
            return
        _ai_debug(
            "jev ranks: series=%d scheduled=%d (too-small=%d not-visible=%d no-metrics=%d)",
            len(groups), len(ready), small, hidden, no_metrics,
        )
        GalleryController._launch_jev_batch(self, ready, scope)

    # -- Jev batch plumbing (S2/J1) -----------------------------------------

    @staticmethod
    def _jev_measured_vector(members, mode, domain: str = "algorithms", *, profile=None) -> dict:
        """Applicable scoring vector for *members* (profile's axes).

        *domain* picks the read: the AI domain's VLM scorecard or the Algorithms
        domain's local detectors (plan-gallery-ai-backend-owns-quality).
        *profile* (plan P1) selects the axes; ``None`` keeps the mode mapping.
        """
        try:
            from tabs.image_gallery.services.jev_client import build_measured_vector

            return build_measured_vector(
                members, mode=mode, domain=domain, profile=profile
            )
        except Exception:
            logger.debug("jev measured vector build failed", exc_info=True)
            return {"mode": "", "items": []}

    @staticmethod
    def _jev_scored_count(vector) -> int:
        """Members carrying at least one applicable MEASURED score."""
        try:
            return sum(1 for e in (vector or {}).get("items", ()) if e.get("scores"))
        except Exception:
            return 0

    @staticmethod
    def _jev_series_fingerprint(ready, mode) -> str:
        """Content key for one Jev batch: ready-series identities + vectors.

        Stable for unchanged inputs, so the single-flight gate blocks a second
        settle over the same series/vectors (plan §Risks: two triggers over
        unchanged inputs must not spawn two workers).
        """
        import hashlib
        import json

        entries = []
        for members, vector in ready or ():
            try:
                ident = sorted(
                    (str(getattr(m, "path", "")), int(getattr(m, "mtime_ns", 0) or 0))
                    for m in members
                )
            except Exception:
                ident = []
            entries.append({"members": ident, "vector": vector})
        entries.sort(key=lambda e: json.dumps(e, sort_keys=True, default=str))
        try:
            raw = json.dumps(
                {"mode": str(getattr(mode, "value", mode) or ""), "series": entries},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        except Exception:
            raw = repr(entries)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def _launch_jev_batch(self, ready, scope) -> None:
        """Run one Jev rank worker per ready series; release the gate at the end.

        The gate is released once, after the LAST attempt reports (result or
        error): a decisive or benign non-answer records completion; a fault
        passes ``ok=False`` so the same fingerprint stays retryable.
        """
        gate = getattr(self, "_stage_gate", None)
        progress = {"remaining": len(ready), "fault": False}

        def _complete(ok: bool) -> None:
            try:
                if not ok:
                    progress["fault"] = True
                progress["remaining"] = max(0, int(progress["remaining"]) - 1)
                if progress["remaining"] <= 0 and gate is not None:
                    gate.finished(_JEV_STAGE, scope, ok=not progress["fault"])
            except Exception:
                logger.debug("jev gate finished failed", exc_info=True)

        for members, _vector in ready:
            try:
                self._run_jev_rank_for_series(members, on_complete=_complete)
            except Exception:
                logger.debug("jev rank series launch failed", exc_info=True)
                _complete(False)

    def _run_series_priority(self) -> None:
        """Schedule ONE cross-series routing pass (additive "needs a human first").

        ``services.series_priority`` asks Jev, over per-series aggregate signals,
        which series deserves attention first. Bounded to series with a visible
        member and capped like the Jev rank pass; cache-first, so a re-run over
        unchanged series+signals costs no request. It writes ONLY the hint
        (``state.series_priority`` + the series-header marker) — never a rank,
        a selection or the store.
        """
        try:
            groups = list(getattr(self.state, "series", None) or [])
        except Exception:
            groups = []
        if len(groups) < 2:
            self._clear_series_priority()
            return
        try:
            vis = getattr(self.widget, "visible_paths", None)
            visible = vis() if callable(vis) else None
        except Exception:
            visible = None
        try:
            vkeys = {str(p) for p in (visible or [])}
        except Exception:
            vkeys = set()
        chosen: list = []
        for entry in groups:
            members = GalleryController._section_members(entry)
            if len(members) < 2:
                continue
            if vkeys and not any(str(getattr(m, "path", "")) in vkeys for m in members):
                continue
            chosen.append(entry)
            if len(chosen) >= self._AI_VISIBLE_CAP:
                break
        if len(chosen) < 2:
            self._clear_series_priority()
            return
        try:
            settings = self._ai_settings_store.load()
        except Exception:
            settings = None
        if (
            settings is None
            or not getattr(settings, "enabled", False)
            or not getattr(settings, "base_url", "")
            or not getattr(settings, "api_key", "")
        ):
            self._clear_series_priority()
            return

        mode = getattr(self.state, "mode", None)
        gen = self._folder_gen
        snapshot = list(chosen)
        base_url = str(getattr(settings, "base_url", ""))
        api_key = str(getattr(settings, "api_key", ""))

        def _job():
            from tabs.image_gallery.services.series_priority import (
                make_client,
                route_series_priority_detailed,
            )

            client = make_client(base_url, api_key)
            return route_series_priority_detailed(snapshot, mode=mode, client=client)

        worker = GenericWorker(_job)

        def _on_result(outcome, gen=gen):
            if not self._is_current_folder_gen(gen):
                return
            priorities = dict(getattr(outcome, "priorities", None) or {})
            try:
                self.state.series_priority = priorities
            except Exception:
                pass
            try:
                self.widget.set_series_attention(set(priorities))
            except Exception:
                pass

        def _on_error(error_info, gen=gen):
            if not self._is_current_folder_gen(gen):
                return
            logger.debug("series priority worker error: %r", error_info, exc_info=True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._pool_start(worker, None)

    def _clear_series_priority(self) -> None:
        """Drop the cross-series hint (domain switch / not configured / <2 series)."""
        try:
            self.state.series_priority = {}
        except Exception:
            pass
        try:
            self.widget.set_series_attention(set())
        except Exception:
            pass

    def _run_jev_rank_for_series(self, members, *, on_complete=None) -> None:
        """Run one Jev rank worker for one series (cache-first, visible degrade).

        Pending is visible via the item activity phase; on a decisive answer the
        ranks are applied (``rank_source="jev"``), otherwise the Algorithms rank
        is kept and the reason surfaced with the benign-vs-fault rule. Calls
        ``on_complete(ok)`` exactly once when this series' attempt ends (used by
        the batch gate: a fault passes ``ok=False`` so it stays retryable).
        Never blocks the UI thread.
        """
        members = list(members or ())

        def _done(ok: bool) -> None:
            if callable(on_complete):
                try:
                    on_complete(bool(ok))
                except Exception:
                    logger.debug("jev series completion hook failed", exc_info=True)

        if len(members) < 2:
            _done(True)
            return
        try:
            settings = self._ai_settings_store.load()
        except Exception:
            settings = None
        if (
            settings is None
            or not getattr(settings, "enabled", False)
            or not getattr(settings, "base_url", "")
            or not getattr(settings, "api_key", "")
        ):
            from tabs.image_gallery.services.jev_client import JEV_REASON_NOT_CONFIGURED

            _ai_debug("jev rank skip: AI not configured (series items=%d)", len(members))
            self._degrade_jev(members, JEV_REASON_NOT_CONFIGURED, as_error=True)
            _done(False)
            return

        mode = getattr(self.state, "mode", None)
        # Snapshot the stored metric profile (plan P1) on the UI thread — the
        # worker closure must read the axis set that was live when the rank was
        # queued, not whatever a later state replacement left behind.
        profile = getattr(self.state, "metric_profile", None)
        _ai_debug(
            "jev rank scheduled: series items=%d mode=%s",
            len(members), getattr(mode, "value", mode),
        )
        gen = self._folder_gen
        snapshot = list(members)
        for m in snapshot:
            try:
                set_activity(m, ActivityPhase.QUEUED, "ai")
                self.widget.refresh_card(m)
            except Exception:
                pass

        base_url = str(getattr(settings, "base_url", ""))
        api_key = str(getattr(settings, "api_key", ""))

        def _job():
            from tabs.image_gallery.services.jev_client import (
                make_client,
                rank_series_jev_detailed,
            )

            client = make_client(base_url, api_key)
            # The AI domain ranks from the VLM scorecard (durable authority);
            # the stored metric profile (P1) selects the axes it scores on.
            return rank_series_jev_detailed(
                snapshot,
                mode=mode,
                client=client,
                domain=str(getattr(self, "_judgment_domain", "algorithms")),
                profile=profile,
            )

        worker = GenericWorker(_job)

        def _on_result(outcome, gen=gen):
            if not self._is_current_folder_gen(gen):
                _done(True)  # stale scope: release the gate, apply nothing
                return
            self._apply_jev_outcome(snapshot, outcome)
            _done(GalleryController._jev_outcome_ok(outcome))

        def _on_error(error_info, gen=gen):
            if not self._is_current_folder_gen(gen):
                _done(True)
                return
            logger.debug("jev rank worker error: %r", error_info, exc_info=True)
            from tabs.image_gallery.services.jev_client import JEV_REASON_ERROR

            self._degrade_jev(snapshot, JEV_REASON_ERROR, as_error=True)
            _done(False)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._pool_start(worker, None)

    @staticmethod
    def _jev_outcome_ok(outcome) -> bool:
        """Gate completion: a decisive or benign non-answer is done; a fault is
        a handled failure (``ok=False``) so the same fingerprint stays retryable."""
        try:
            if bool(getattr(outcome, "decided", False)):
                return True
            from tabs.image_gallery.services.jev_client import reason_is_fault

            return not reason_is_fault(getattr(outcome, "reason", None))
        except Exception:
            return True

    def _apply_jev_outcome(self, members, outcome) -> None:
        """Apply one Jev result: ranks + ``rank_source="jev"`` or a visible degrade."""
        ranks = getattr(outcome, "ranks", None)
        current: list = []
        for m in list(members or ()):
            it = self._find_item(getattr(m, "path", None))
            current.append(it if it is not None else m)
        if ranks:
            for it in current:
                path = str(getattr(it, "path", ""))
                _rank = ranks.get(path)
                if _rank is None:
                    # Jev owns the AI-domain ordering: a member Jev did not rank
                    # is not the winner — never leave a stale BEST from fusion.
                    try:
                        it.is_best = False
                    except Exception:
                        pass
                    continue
                try:
                    it.rank = int(_rank)
                    it.rank_source = "jev"  # type: ignore[attr-defined]
                    # Jev owns the WHOLE ordering on the AI domain: drop any stale
                    # crown and mark ONLY rank 1 as the series winner (the ★ BEST
                    # preset) so no two cards ever show the same number again.
                    it.crown_rank = None
                    it.is_best = (it.rank == 1)
                except Exception:
                    pass
            try:
                self.state.rank_domain = "ai"
            except Exception:
                pass
            for it in current:
                try:
                    # Complete the badge UX: queued -> done (lingers ~1s -> fades),
                    # never an abrupt clear that kills the chip mid-ux.
                    set_activity(it, ActivityPhase.DONE, "ai")
                except Exception:
                    pass
            # One atomic repaint of every member: a per-card loop let a snapshot
            # mix a Jev rank with a stale fusion rank -> two #1s ("Jev chose all
            # at once"). Apply all ranks/activity, THEN refresh.
            GalleryController._refresh_ranks_visible(self)
            try:
                self.widget.refresh_cards(current)
            except Exception:
                for it in current:
                    try:
                        self.widget.refresh_card(it)
                    except Exception:
                        pass
            _ai_debug("jev rank applied: items=%d source=jev", len(current))
            GalleryController._refresh_rank_provenance(self)
            return
        reason = getattr(outcome, "reason", None) or "AI (Jev) rank unavailable"
        try:
            from tabs.image_gallery.services.jev_client import reason_is_fault

            as_error = bool(reason_is_fault(reason))
        except Exception:
            as_error = False
        GalleryController._degrade_jev(self, current, reason, as_error=as_error)
        GalleryController._refresh_rank_provenance(self)

    def _degrade_jev(self, members, reason: str, *, as_error: bool = False) -> None:
        """Keep the Algorithms (fusion) rank and surface a visible reason.

        The stored rank is never touched here — a failed Jev rank must not
        fabricate a number or re-rank a subset (no silent fallback). A BENIGN
        non-answer (abstain / low confidence / nothing to rank / unusable reply)
        CLEARS the AI activity so the card shows the Algorithms rank instead of a
        false "error" chip that later flips to "done"; only a real fault
        (``as_error``: transport error / not configured) paints the error chip.
        The reason is always logged.
        """
        logger.debug("jev rank degraded: %s", reason)
        _ai_debug("jev rank degraded: %s", reason)
        touched: list = []
        for m in list(members or ()):
            it = self._find_item(getattr(m, "path", None)) or m
            try:
                if as_error:
                    set_activity(it, ActivityPhase.ERROR, "ai")
                else:
                    # Benign non-answer: the Jev work FINISHED — let the chip
                    # complete its ux (done lingers, then fades) instead of an
                    # abrupt clear mid-flight.
                    set_activity(it, ActivityPhase.DONE, "ai")
                touched.append(it)
            except Exception:
                pass
        # Atomic repaint (see _apply_jev_outcome): never a mixed-rank snapshot.
        try:
            self.widget.refresh_cards(touched)
        except Exception:
            for it in touched:
                try:
                    self.widget.refresh_card(it)
                except Exception:
                    pass

    def _refresh_rank_provenance(self) -> None:
        """State which ranker produced the series ranks (stats-strip chip).

        Reads the ACTUAL ``rank_source`` of the ranked members — never the
        intended domain: an AI domain that degraded to the Algorithms rank must
        say "Algorithms", not "AI (Jev)". Falls back to the judgment domain when
        nothing is ranked yet. Never raises.
        """
        src = ""
        try:
            for entry in (getattr(self.state, "series", None) or ()):
                for m in GalleryController._section_members(entry):
                    s = str(getattr(m, "rank_source", "") or "")
                    if getattr(m, "rank", None) is not None and s in ("fusion", "jev", "manual"):
                        src = s
                        break
                if src:
                    break
        except Exception:
            src = ""
        try:
            self.widget.set_rank_provenance(
                src or None, domain=str(getattr(self, "_judgment_domain", "algorithms"))
            )
        except Exception:
            logger.debug("rank provenance refresh failed", exc_info=True)

    def _begin_analysis(self, ctx, item: GalleryItem) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._begin_analysis(self, ctx, item)

    def _apply_ai_phase(self, item: GalleryItem, phase: str) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._apply_ai_phase(self, item, phase)

    def _on_analysis_ready(self, path: Path, mtime_ns: int, result, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._on_analysis_ready(self, path, mtime_ns, result, gen)

    def _refresh_open_quick_look(self) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._refresh_open_quick_look(self)

    def _on_analysis_error(self, path: Path, error_info, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import ai_analysis as _ai_analysis

        return _ai_analysis._on_analysis_error(self, path, error_info, gen)

    # -- Ask AI (A3 entry points + A4 async/cache/generation guard) ------------

    def open_ask_ai(self, scope_kind: str, card, path) -> None:
        """Entry from the card / selection context menu (scope = selection/card)."""
        from tabs.image_gallery.services.ask_context import AskScope

        path = Path(path)
        if scope_kind == "card":
            scope = AskScope(kind="selection", paths=(path,), label=path.name)
        else:
            try:
                paths = tuple(getattr(self.state, "selected_paths", None) or ())
            except Exception:
                paths = ()
            if not paths:
                paths = (path,)
            # No scope line in the flyout for a multi/selection ask (the
            # generic "Selection" is noise; the ask context still labels it
            # "Selection" via ask_context._resolve_items when the label is
            # empty). Card asks keep the filename as their scope line.
            scope = AskScope(kind="selection", paths=paths, label="")
        self._open_ask_ai(card, scope)

    def open_ask_ai_for_series(self, index, anchor, member_paths, label) -> None:
        """Entry from the series header menu (scope = whole series)."""
        from tabs.image_gallery.services.ask_context import AskScope

        # No series name in the surface/context: the anchor already labels it.
        scope = AskScope(
            kind="series",
            paths=tuple(member_paths or ()),
            label="",
        )
        self._open_ask_ai(anchor, scope)

    def _open_ask_ai(self, anchor, scope, *, grow_up: bool = False, default_prompt: str | None = None, show_images_toggle: bool = True) -> None:
        opener = getattr(self.widget, "open_ask_ai", None)
        if not callable(opener):
            return
        try:
            default = default_prompt or self._tr("image_gallery.ask_ai.default_prompt", "What matters here?")
            _settings = self._ai_settings_store.load()
            texts = {
                "title": self._tr("image_gallery.ask_ai.title", "Ask AI"),
                "busy": self._tr("image_gallery.ask_ai.busy", "Thinking…"),
                "read_badge": self._tr(
                    "image_gallery.ask_ai.read_badge", "AI read, unverified"
                ),
                "error": self._tr(
                    "image_gallery.ask_ai.error", "AI could not answer."
                ),
                "images_hint": self._tr(
                    "image_gallery.ask_ai.images_toggle_hint",
                    "Send images with the question",
                ),
                "images_downsample": self._images_downsample_text(
                    _settings.vlm_max_edge_px
                ),
                # Status badge shows the selected LLM, not the backend token.
                "model": _settings.model,
                "cached": self._tr("image_gallery.ask_ai.cached", " · cached"),
            }
        except Exception:
            default = "What matters here?"
            texts = None
        try:
            opener(anchor, scope, default_prompt=default, texts=texts, grow_up=grow_up, show_images_toggle=show_images_toggle)
        except TypeError:
            try:
                opener(anchor, scope, default_prompt=default, texts=texts, grow_up=grow_up)
            except TypeError:
                opener(anchor, scope, default_prompt=default, texts=texts)

    def open_ask_ai_region(self, path, box, anchor=None, *, question: str = "") -> None:
        """Open the Ask AI flyout ABOVE the anchor for a selected image region.

        ``box`` is ``(left, top, right, bottom)`` as fractions of the image.
        The flyout grows upward; the region + full image + metrics are sent to
        the VLM with the region system prompt on submit. Region asks always
        carry the images, so the include-images toggle is hidden.
        """
        from tabs.image_gallery.services.ask_context import ASK_REGION, AskScope

        try:
            box_t = tuple(float(v) for v in (box or ()))
        except Exception:
            box_t = ()
        if len(box_t) != 4:
            return
        scope = AskScope(kind=ASK_REGION, paths=(Path(path),), label="", box=box_t)
        target = anchor if anchor is not None else self.widget
        prompt = question or self._tr(
            "image_gallery.ask_ai.region_prompt", "What is wrong in this region?"
        )
        self._open_ask_ai(target, scope, grow_up=True, default_prompt=prompt, show_images_toggle=False)
        # The selection band stays visible under the flyout; dismiss it only
        # when the flyout closes (not when the drag ends). The slot is armed
        # for THIS selection generation: a newer marquee started afterwards
        # (one-gesture dismiss + reselect) supersedes it — the close ending
        # the old flyout session must not wipe the new selection.
        try:
            dismiss = getattr(target, "dismiss_selection", None)
            if callable(dismiss):
                flyout = self.widget._ensure_ask_ai_flyout()
                try:
                    armed_gen = getattr(target, "selection_id", None)
                    armed_gen = None if armed_gen is None else int(armed_gen)
                except Exception:
                    armed_gen = None
                prev = getattr(self, "_region_dismiss_slot", None)
                if prev is not None:
                    try:
                        flyout.hidden.disconnect(prev)
                    except Exception:
                        pass
                def _dismiss(_dismiss_fn=dismiss, _flyout=flyout, _band=target, _gen=armed_gen):
                    try:
                        if _gen is not None:
                            try:
                                current = getattr(_band, "selection_id", None)
                                current = None if current is None else int(current)
                            except Exception:
                                current = None
                            if current is not None and current != _gen:
                                return
                    finally:
                        try:
                            _flyout.hidden.disconnect(_dismiss)
                        except Exception:
                            pass
                        try:
                            if getattr(self, "_region_dismiss_slot", None) is _dismiss:
                                self._region_dismiss_slot = None
                        except Exception:
                            pass
                    try:
                        _dismiss_fn()
                    except Exception:
                        pass
                flyout.hidden.connect(_dismiss)
                self._region_dismiss_slot = _dismiss
        except Exception:
            pass

    def _images_downsample_text(self, px: int) -> str:
        """Tooltip line 2 for the Ask AI images toggle: the current downscale."""
        if int(px or 0) <= 0:
            return self._tr("image_gallery.settings.downscale_original", "Original")
        template = self._tr(
            "image_gallery.ask_ai.images_toggle_downsample", "Downscale: ≤ {px} px"
        )
        return template.replace("{px}", str(int(px)))

    def _ask_cache_key(self, scope, context, question: str, backend: str, model: str) -> str:
        import hashlib
        import json

        try:
            paths = sorted(
                str(it.get("path", "")) for it in (context.get("items") or [])
            )
        except Exception:
            paths = []
        ident = {
            "kind": getattr(scope, "kind", ""),
            "series": getattr(scope, "series_id", None),
            "label": getattr(scope, "label", ""),
            "paths": paths,
            "mode": (context or {}).get("mode", ""),
            "question": str(question or "").strip(),
            "backend": backend,
            "model": model,
            # Region asks must not collide with whole-image asks.
            "region": (context or {}).get("region", {}).get("box")
            if isinstance((context or {}).get("region"), dict)
            else None,
        }
        blob = json.dumps(ident, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()

    def ask_ai_question(self, scope, question: str, *, include_images: bool = False) -> None:
        """Build context, route, and run the backend on a GenericWorker.

        Advisory only: never mutates rank/selection/store. Late answers are
        dropped by the folder generation guard. Fail-open: a backend error is
        shown visibly, never replaced by fabricated text.
        """
        from tabs.image_gallery.services.ask_context import (
            answer_image_links,
            build_ask_context,
            deanonymize_answer,
        )
        from tabs.image_gallery.services.ask_router import answer, resolve_backend

        logger.debug(
            "[ask-ai] submit scope=%s q=%.80s",
            getattr(scope, "kind", None),
            str(question or ""),
        )
        try:
            context = build_ask_context(scope, controller=self)
            backend = resolve_backend(question, context, include_images=include_images)
        except Exception:
            logger.debug("ask-ai context build failed", exc_info=True)
            self._show_ask_ai_error(
                self._tr(
                    "image_gallery.ask_ai.error_context",
                    "Could not assemble the ask context.",
                )
            )
            return
        is_region = str(getattr(scope, "kind", "") or "") == "region"
        if is_region:
            # Region inspection is always visual: the crop + full image go out.
            backend = "vlm"
        system_prompt = None
        if is_region:
            try:
                from tabs.image_gallery.services.ask_prompt import ASK_REGION_SYSTEM_PROMPT

                system_prompt = ASK_REGION_SYSTEM_PROMPT
            except Exception:
                system_prompt = None
        logger.debug(
            "[ask-ai] route backend=%s items=%d", backend, len(context.get("items") or [])
        )
        # name → path, so a surface can turn the de-anonymized filenames in the
        # answer into clickable links that open that image.
        links = answer_image_links(context)

        settings = self._ai_settings_store.load()
        from tabs.image_gallery.services.vlm import set_vlm_max_edge

        set_vlm_max_edge(settings.vlm_max_edge_px)
        if not settings.enabled or not settings.api_key or not settings.model:
            logger.debug("[ask-ai] not configured (enabled=%s key=%s model=%s)",
                         settings.enabled, bool(settings.api_key), bool(settings.model))
            self._show_ask_ai_error(
                self._tr(
                    "image_gallery.errors.not_configured",
                    "Configure the AI API key in Settings first.",
                )
            )
            return

        key = self._ask_cache_key(scope, context, question, backend, settings.model)
        cached = self._ask_cache.get(key)
        if cached is not None:
            logger.debug("[ask-ai] cache hit backend=%s", backend)
            try:
                from dataclasses import replace

                cached = replace(cached, cached=True)  # type: ignore[arg-type]
            except Exception:
                pass
            self._show_ask_ai_result(cached, links)
            return

        logger.debug(
            "[ask-ai] worker start backend=%s model=%s", backend, settings.model
        )
        self._show_ask_ai_busy()
        # The model only ever sees opaque img_N labels (see ask_context); map
        # them back to the real filenames on the way out, off the UI thread.
        names = context.get("names")

        def _run():
            result = answer(
                question,
                context,
                backend=backend,
                base_url=settings.base_url,
                api_key=settings.api_key,
                model=settings.model,
                max_tokens=getattr(settings, "ask_max_tokens", 0),
                reasoning_effort=getattr(settings, "reasoning_effort", "auto"),
                system_prompt=system_prompt,
            )
            if not getattr(result, "error", None) and names:
                try:
                    from dataclasses import replace as _replace

                    result = _replace(
                        result, text=deanonymize_answer(result.text, names)
                    )
                except Exception:
                    pass
            return result

        worker = GenericWorker(self._tracked(_run))
        gen = self._folder_gen
        worker.signals.result.connect(
            lambda result, k=key, g=gen, lnk=links: self._on_ask_ai_ready(result, k, g, lnk)
        )
        worker.signals.error.connect(
            lambda err, g=gen: self._on_ask_ai_error(err, g)
        )
        self._pool_start(worker, None)

    def _on_ask_ai_ready(self, result, key: str, gen: int | None = None, links: dict | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            logger.debug("[ask-ai] result dropped (stale folder gen)")
            return  # folder switched — late ask answer dropped
        error = getattr(result, "error", None)
        logger.debug(
            "[ask-ai] ready backend=%s err=%s text_chars=%d",
            getattr(result, "backend", None),
            error,
            len(getattr(result, "text", "") or ""),
        )
        if error:
            self._show_ask_ai_error(self._ask_error_text(error))
            return
        try:
            self._ask_cache[key] = result
        except Exception:
            pass
        self._show_ask_ai_result(result, links)

    def _on_ask_ai_error(self, error_info, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        logger.debug("[ask-ai] worker error: %r", error_info, exc_info=True)
        message = None
        try:
            _exctype, value, _tb = error_info
            message = str(value) if value is not None else None
        except Exception:
            message = str(error_info)
        self._show_ask_ai_error(self._ask_error_text(message))

    def _ask_error_text(self, error) -> str:
        text = str(error) if error else ""
        if "routing backend" in text:
            return self._tr(
                "image_gallery.ask_ai.routing_unavailable",
                "Routing is not enabled yet.",
            )
        return text or self._tr(
            "image_gallery.ask_ai.error", "AI could not answer."
        )

    def _show_ask_ai_busy(self) -> None:
        try:
            self.widget.show_ask_ai_busy()
        except Exception:
            pass

    def _show_ask_ai_result(self, result, links: dict | None = None) -> None:
        try:
            try:
                model = self._ai_settings_store.load().model
            except Exception:
                model = ""
            self.widget.show_ask_ai_result(result, model=model, links=links)
        except Exception:
            pass

    def _show_ask_ai_error(self, message: str) -> None:
        try:
            self.widget.show_ask_ai_error(message)
        except Exception:
            pass

    # -- triage (Stage 2 Pass 1) -----------------------------------------------

    def _next_series_gen(self) -> int:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._next_series_gen(self)

    def _assign_fresh_stable_ids(self, computed) -> tuple:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._assign_fresh_stable_ids(self, computed)

    @staticmethod
    def _section_members(entry) -> list:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._section_members(entry)

    @staticmethod
    def _section_id(entry, members) -> str | None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._section_id(entry, members)

    def _restore_singletons(self, items, overrides, pre_ids, last_series, regrouped) -> list:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._restore_singletons(self, items, overrides, pre_ids, last_series, regrouped)

    def _apply_series_view(self, series) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._apply_series_view(self, series)

    def _run_triage_sync(
        self, items: list[GalleryItem], overrides: dict | None = None
    ) -> tuple[list[Series], Path | None, Mode]:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._run_triage_sync(self, items, overrides)

    def retriage_quiet(self) -> bool:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run.retriage_quiet(self)

    def _start_triage(self, items: list[GalleryItem], *, cover_grid: bool = True) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._start_triage(self, items, cover_grid=cover_grid)

    def _mark_local_pass(self, items, phase) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._mark_local_pass(self, items, phase)

    def _settle_metrics_pass(self, items) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._settle_metrics_pass(self, items)

    def _run_ai_on_settle(self) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._run_ai_on_settle(self)

    def _run_jev_on_settle(self) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._run_jev_on_settle(self)

    def _queue_ai_rank_on_settle(self) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._queue_ai_rank_on_settle(self)

    def _flush_ai_rank_on_settle(self) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._flush_ai_rank_on_settle(self)

    def _begin_append_processing(self, items: list[GalleryItem]) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._begin_append_processing(self, items)

    def _finish_append_processing(self, items: list[GalleryItem]) -> None:
        from tabs.image_gallery.use_cases import triage_run as _triage_run

        return _triage_run._finish_append_processing(self, items)

    def _run_artifacts_sync(self, items: list[GalleryItem], source_path: Path | None) -> dict[str, dict]:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._run_artifacts_sync(self, items, source_path)

    def _start_artifact_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._start_artifact_analysis(self, items, source_path)

    def _on_artifacts_ready(self, result: object, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._on_artifacts_ready(self, result, gen)

    def _apply_artifact_map(self, result: dict, maps: dict | None = None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._apply_artifact_map(self, result, maps)

    def _on_artifacts_error(self, error_info: object) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._on_artifacts_error(self, error_info)

    # -- fidelity metrics (Stage 2 Pass 1b, wave B producer) --------------------

    def _start_fidelity_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._start_fidelity_analysis(self, items, source_path)

    def _on_fidelity_ready(self, result: object, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._on_fidelity_ready(self, result, gen)

    def _apply_fidelity_map(self, result: dict) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._apply_fidelity_map(self, result)

    def _start_camera_metrics_analysis(self, items: list[GalleryItem]) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._start_camera_metrics_analysis(self, items)

    def _refresh_changed_metrics(self, changed: list, tag: str) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._refresh_changed_metrics(self, changed, tag)

    def _on_camera_metrics_ready(self, result: object, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._on_camera_metrics_ready(self, result, gen)

    def _apply_camera_map(self, result: dict) -> None:
        from tabs.image_gallery.use_cases import metrics_stage2 as _metrics_stage2

        return _metrics_stage2._apply_camera_map(self, result)

    # -- unified Stage-2 proxy step (Phase 2b+3; single-pass) ------------------

    @staticmethod
    def _run_proxy_chunk_sync(chunk: list, source_path, include_camera: bool, full_res_artifacts: bool = False) -> dict:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._run_proxy_chunk_sync(chunk, source_path, include_camera, full_res_artifacts)

    def _schedule_proxy(self, items: list, priority: int, source, gen: int, wanted=None, include_camera: bool | None = None, full_res_artifacts: bool = False, on_done=None) -> int:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._schedule_proxy(self, items, priority, source, gen, wanted=wanted, include_camera=include_camera, full_res_artifacts=full_res_artifacts, on_done=on_done)

    def _start_proxy_analysis(self, items: list[GalleryItem], source_path: Path | None, mode, *, on_done=None) -> None:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._start_proxy_analysis(self, items, source_path, mode, on_done=on_done)

    def _on_proxy_batch_ready(self, result: object, gen: int | None, wanted: object = None) -> None:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._on_proxy_batch_ready(self, result, gen, wanted)

    def _on_triage_ready(self, result: object, gen: int | None = None, sgen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._on_triage_ready(self, result, gen, sgen)

    def _commit_triage_series(self, series, source, mode):
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._commit_triage_series(self, series, source, mode)

    @staticmethod
    def _analysis_fingerprint(items, source) -> tuple:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._analysis_fingerprint(items, source)

    def _apply_triage_result(self, series, source, mode) -> None:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._apply_triage_result(self, series, source, mode)

    def _on_triage_error(self, error_info: object, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import proxy_pass as _proxy_pass

        return _proxy_pass._on_triage_error(self, error_info, gen)

    # -- Stage 3 VLM: tie-break + compare briefs (GenericWorker, badge pending, silent degrade) --

    def _is_tie(self, a: GalleryItem, b: GalleryItem, epsilon: float = TIE_EPSILON) -> bool:
        from tabs.image_gallery.use_cases import tie_break as _tie_break

        return _tie_break._is_tie(self, a, b, epsilon)

    def run_tie_break_if_needed(self, series) -> None:
        from tabs.image_gallery.use_cases import tie_break as _tie_break

        return _tie_break.run_tie_break_if_needed(self, series)

    def _apply_tie_break_result(self, a: GalleryItem, b: GalleryItem, result) -> None:
        from tabs.image_gallery.use_cases import tie_break as _tie_break

        return _tie_break._apply_tie_break_result(self, a, b, result)

    def _apply_brief_result(self, pa: Path, pb: Path, result, gen: int | None = None) -> None:
        from tabs.image_gallery.use_cases import tie_break as _tie_break

        return _tie_break._apply_brief_result(self, pa, pb, result, gen)

    # -- Stage 2 crown/reject/S3 (thin wrappers → use_cases/triage_actions) --

    def _mark_triage_picks_manual(self) -> int:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions._mark_triage_picks_manual(self)

    def _mark_rank_manual(self, items) -> int:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions._mark_rank_manual(self, items)

    def _item_for_path(self, path):
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions._item_for_path(self, path)

    def make_best(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.make_best(self, path)

    def toggle_reject(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.toggle_reject(self, path)

    def remove_from_grid(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.remove_from_grid(self, path)

    def remove_paths_from_grid(self, paths) -> int:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.remove_paths_from_grid(self, paths)

    def keep_best_of_series(self) -> dict:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.keep_best_of_series(self)

    def show_all(self) -> int:
        from tabs.image_gallery.use_cases import triage_actions as _triage_actions

        return _triage_actions.show_all(self)

    # -- manual series overrides (Wave B drop targets) ---------------------

    def move_paths_to_series(self, paths, series_id: str | None) -> int:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.move_paths_to_series(self, paths, series_id)

    def group_paths_as_new_series(self, paths) -> str | None:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.group_paths_as_new_series(self, paths)

    def _attach_append_items(self, new_items) -> dict:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides._attach_append_items(self, new_items)

    def _cluster_tail_into_series(self) -> list:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides._cluster_tail_into_series(self)

    def recluster_series(self) -> None:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.recluster_series(self)

    def reset_series_overrides(self) -> int:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.reset_series_overrides(self)

    def clean_rejected(self) -> list[dict]:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.clean_rejected(self)

    def show_clean_review(self) -> None:
        from tabs.image_gallery.use_cases import series_overrides as _series_overrides

        return _series_overrides.show_clean_review(self)

    # -- filtering (debounced; brief-disk match off UI thread) --------

    #: Keystroke coalescing window — rapid typing applies once, not per char.
    FILTER_DEBOUNCE_MS = 120

    def set_filter_text(self, text: str) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering.set_filter_text(self, text)

    def apply_pending_filter(self) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering.apply_pending_filter(self)

    def _apply_pending_filter(self) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering._apply_pending_filter(self)

    def _apply_filter_fast(self, text: str) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering._apply_filter_fast(self, text)

    def _apply_filter(self, text: str, filter_gen: int) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering._apply_filter(self, text, filter_gen)

    def _on_brief_filter_ready(self, extra_paths: set, filter_gen: int, folder_gen: int) -> None:
        from tabs.image_gallery.use_cases import filtering as _filtering

        _filtering._on_brief_filter_ready(self, extra_paths, filter_gen, folder_gen)
