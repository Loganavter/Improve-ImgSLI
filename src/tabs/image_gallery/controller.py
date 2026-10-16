"""Presenter for the Image Gallery tab: folder scan, thumbnails, Stage 3 VLM (tie-break + briefs).
Audit-Meta: pattern=state-machine size=exempt reason="one controller lifecycle — folder scan/thumbnail/triage/VLM sharing GenericWorker state"

Pass 2 VLM is optional, targeted, always via GenericWorker (never UI-blocking).
Unresolved tie-breaks degrade silent-but-visible: pending badge cleared,
local ranking kept.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QThreadPool, QTimer, Signal
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.use_cases import pipeline_stages as _pipeline_stages

from tabs.image_gallery.models import (
    ActivityPhase,
    AnalysisStatus,
    GalleryItem,
    GalleryState,
    Mode,
    Series,
    ThumbnailStatus,
    TriageState,
)
from tabs.image_gallery.services.activity import clear_activity, set_activity
from tabs.image_gallery.services.ai_cache import load_cached_analysis, save_analysis
from tabs.image_gallery.services.ai_client import (
    _ai_debug,
    AiAuthError,
    AiClientError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    analyze_image_sync,
)
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import (
    gallery_artifacts_disabled as _artifacts_disabled,
)
from tabs.image_gallery.debug import (
    gallery_camera_disabled as _camera_disabled,
)
from tabs.image_gallery.debug import (
    gallery_fidelity_disabled as _fidelity_disabled,
)
from tabs.image_gallery.debug import (
    gallery_thumbs_disabled as _thumbs_disabled,
)
from tabs.image_gallery.services.filtering import filter_items
from tabs.image_gallery.services.thumbnail_cache import render_and_cache_thumbnail

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

# Proxy decode-cache bound: owned by services/proxy.py (PROXY_CACHE_LIMIT);
# batch delivery trims oldest-inserted entries down to that bound (96 x
# <= ~3 MB ~= <= 288 MB while covering a typical folder's working set;
# insertion order is a cheap LRU stand-in — warm hits are not reordered,
# folder churn evicts). Never restate the literal here.


def _scheduler_thread_count() -> int:
    """Dedicated pool size: os.cpu_count() clamped to [4, 8]."""
    try:
        n = int(os.cpu_count() or _GALLERY_SCHED_MIN_THREADS)
    except Exception:
        n = _GALLERY_SCHED_MIN_THREADS
    return max(_GALLERY_SCHED_MIN_THREADS, min(_GALLERY_SCHED_MAX_THREADS, n))


def _new_gallery_pool() -> QThreadPool:
    """Dedicated gallery pool (never QThreadPool.globalInstance())."""
    pool = QThreadPool()
    try:
        pool.setMaxThreadCount(_scheduler_thread_count())
    except Exception:
        pass
    return pool


class _GalleryVisibilityPauseFilter(QObject):
    """Hide/Show watcher: pause the background thumb queue while hidden.

    Mirrors the tab's modal-lifetime Hide filter: only an explicit page
    hide (``watched.isHidden()``) pauses — ancestor-driven hides (window
    minimize, ``isHidden()`` False) are ignored. Show resumes the drain.
    Installed by the controller so no tab.py change is needed; every
    delivery path keeps its ``_folder_gen`` check regardless.
    """

    def __init__(self, controller: GalleryController, watched: QObject | None) -> None:
        super().__init__(watched)
        self._controller = controller

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        try:
            kind = event.type()
            if kind == QEvent.Type.Hide and watched.isHidden():
                try:
                    self._controller.pause_background()
                except Exception:
                    pass
            elif kind == QEvent.Type.Show:
                try:
                    self._controller.resume_background()
                except Exception:
                    pass
        except Exception:
            pass
        return False

_ERROR_KEYS = {
    AiAuthError: ("image_gallery.errors.auth", "Authentication failed — check your API key."),
    AiRateLimitError: ("image_gallery.errors.rate_limit", "Rate limited — try again later."),
    AiNetworkError: ("image_gallery.errors.network", "Network error while contacting the AI API."),
    AiResponseError: ("image_gallery.errors.parse", "Could not parse the AI response."),
}


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
        """Single scheduler entry for gallery concurrency (frozen seam).

        ``items`` is a list of GalleryItem; ``priority`` is a Qt pool
        priority (``VISIBLE_THUMB_PRIORITY`` / ``PROXY_BATCH_PRIORITY`` /
        ``BACKGROUND_THUMB_PRIORITY``). ``op`` selects the lane: ``"thumb"``
        (one worker per item) or ``"proxy"`` (chunked single-pass
        Stage-2 batches, ``source`` = triage source path, ``wanted`` =
        stage subset to apply, ``include_camera`` = run camera scalars).
        ``on_done`` (proxy only) fires once on the GUI thread after the LAST
        chunk of this batch has applied (result or error) — used by the
        append path to retire its processing indicator.
        Returns workers started (background-paused items queue instead and
        return 0 until resumed). No Store/EventBus writes; every delivery
        keeps its generation check — queued entries from an old gen are
        dropped, never delivered.
        """
        batch = list(items or [])
        if gen is None:
            try:
                gen = self._folder_gen
            except Exception:
                gen = 0
        if op == "proxy":
            return self._schedule_proxy(batch, int(priority), source, gen, wanted=wanted, include_camera=include_camera, full_res_artifacts=full_res_artifacts, on_done=on_done)
        return self._schedule_thumbs(batch, int(priority), gen)

    def sched_stats(self) -> dict:
        """Scheduler introspection (tests / debugging)."""
        try:
            with self._sched_lock:
                pending = int(self._sched_pending)
                active = int(self._sched_active)
                peak = int(self._sched_peak)
        except Exception:
            pending, active, peak = (0, 0, 0)
        try:
            queued = len(self._bg_queue)
        except Exception:
            queued = 0
        return {"pending": pending, "active": active, "peak": peak, "queued": queued}

    def _tracked(self, fn):
        """Wrap a worker body with active/peak accounting (pool depth)."""
        def _run(*args, **kwargs):
            try:
                with self._sched_lock:
                    self._sched_active += 1
                    if self._sched_active > self._sched_peak:
                        self._sched_peak = self._sched_active
            except Exception:
                pass
            try:
                return fn(*args, **kwargs)
            finally:
                try:
                    with self._sched_lock:
                        self._sched_active -= 1
                except Exception:
                    pass
        return _run

    def _pool_start(self, worker, priority: int | None) -> None:
        """Start one worker with pending accounting (all pool traffic)."""
        try:
            with self._sched_lock:
                self._sched_pending += 1
        except Exception:
            pass
        try:
            finished = getattr(getattr(worker, "signals", None), "finished", None)
            if finished is not None and hasattr(finished, "connect"):
                try:
                    finished.connect(self._on_sched_finished)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if priority is None:
                self._thread_pool.start(worker)
            else:
                self._thread_pool.start(worker, priority)
        except TypeError:
            self._thread_pool.start(worker)

    def _on_sched_finished(self) -> None:
        try:
            with self._sched_lock:
                self._sched_pending = max(0, self._sched_pending - 1)
        except Exception:
            pass

    def _schedule_thumbs(self, items: list, priority: int, gen: int) -> int:
        """One thumbnail worker per item (visible-first caller partitions)."""
        if _thumbs_disabled():
            _dbg("scheduler: thumbnails skipped (IMGSLI_GALLERY_NO_THUMBS)")
            return 0
        started = 0
        for item in items:
            try:
                key = str(item.path)
            except Exception:
                continue
            try:
                if key in self._thumb_inflight:
                    continue
                if getattr(item, "thumbnail_status", None) == ThumbnailStatus.LOADED:
                    continue
            except Exception:
                pass
            # Paused background lane queues instead of starting.
            try:
                paused = bool(self._bg_paused)
            except Exception:
                paused = False
            if paused and priority <= BACKGROUND_THUMB_PRIORITY:
                try:
                    self._bg_queue.append((item, gen))
                except Exception:
                    pass
                continue
            try:
                item.thumbnail_status = ThumbnailStatus.LOADING
            except Exception:
                pass
            try:
                self._thumb_inflight.add(key)
            except Exception:
                pass
            worker = GenericWorker(
                self._tracked(render_and_cache_thumbnail), item.path, item.mtime_ns
            )
            worker.signals.result.connect(
                lambda cache_path, path=item.path, g=gen: self._on_thumbnail_ready(path, cache_path, g)
            )
            worker.signals.error.connect(
                lambda err, path=item.path, g=gen: self._on_thumbnail_error(path, g)
            )
            self._pool_start(worker, priority)
            started += 1
        return started

    def _begin_folder_schedule(self, items: list, gen: int) -> None:
        """Visible-first partition for a fresh folder (open_folder only).

        Cards intersecting the viewport (+ overscan) decode first at
        ``VISIBLE_THUMB_PRIORITY``; the rest drain from the background
        lane. ``visible_paths()`` fails open to everything when the grid
        is not laid out yet — identical to the old flood, never a
        starvation. Widgets without the Phase-2a API (older doubles)
        take the same fail-open path.
        """
        try:
            visible = getattr(self.widget, "visible_paths", None)
            paths = visible() if callable(visible) else None
        except Exception:
            paths = None
        try:
            if paths:
                visible_keys = {str(p) for p in paths}
            else:
                visible_keys = set()
        except Exception:
            visible_keys = set()
        if not visible_keys:
            try:
                visible_keys = {str(it.path) for it in items}
            except Exception:
                visible_keys = set()
        first: list = []
        rest: list = []
        for it in items:
            try:
                (first if str(it.path) in visible_keys else rest).append(it)
            except Exception:
                continue
        self.schedule(first, VISIBLE_THUMB_PRIORITY, gen=gen)
        self.schedule(rest, BACKGROUND_THUMB_PRIORITY, gen=gen)

    def _subscribe_visible_range(self) -> None:
        """Reprioritize on scroll (grid debounces 120 ms upstream)."""
        try:
            sig = getattr(self.widget, "visible_range_changed", None)
            connect = getattr(sig, "connect", None)
            if callable(connect):
                connect(self._on_visible_range_changed)
        except Exception:
            logger.debug("visible_range_changed subscription failed", exc_info=True)

    def _on_visible_range_changed(self, paths: object) -> None:
        """Scroll delivery: newly visible items jump the thumb queue."""
        try:
            keys = {str(p) for p in (paths or [])}
        except Exception:
            return
        if not keys:
            return
        try:
            gen = self._folder_gen
        except Exception:
            gen = 0
        for item in list(getattr(self.state, "items", None) or []):
            try:
                if str(item.path) not in keys:
                    continue
                if getattr(item, "thumbnail_status", None) == ThumbnailStatus.LOADED:
                    continue
                if str(item.path) in self._thumb_inflight:
                    continue
            except Exception:
                continue
            try:
                self.schedule([item], VISIBLE_THUMB_PRIORITY, gen=gen)
            except Exception:
                pass

    def _install_visibility_pause(self) -> None:
        """Pause the background lane while the tab page is hidden."""
        try:
            widget = self.widget
            install = getattr(widget, "installEventFilter", None)
            if not callable(install):
                return
            try:
                parent = widget if isinstance(widget, QObject) else None
            except Exception:
                parent = None
            filt = _GalleryVisibilityPauseFilter(self, parent)
            install(filt)
            self._visibility_pause_filter = filt
        except Exception:
            logger.debug("visibility pause filter install failed", exc_info=True)

    def pause_background(self) -> None:
        """Pause the background thumb lane (tab hidden)."""
        try:
            self._bg_paused = True
        except Exception:
            pass

    def resume_background(self) -> None:
        """Resume the background lane; stale entries drop, fresh drain."""
        try:
            self._bg_paused = False
        except Exception:
            return
        try:
            queued = list(self._bg_queue)
            self._bg_queue.clear()
        except Exception:
            return
        try:
            current = self._folder_gen
        except Exception:
            current = 0
        fresh = [it for (it, g) in queued if g == current]
        if fresh:
            try:
                self.schedule(fresh, BACKGROUND_THUMB_PRIORITY, gen=current)
            except Exception:
                logger.debug("background resume schedule failed", exc_info=True)

    def _trim_proxy_cache(self) -> int:
        """Bound the shared proxy decode cache (insertion-order eviction)."""
        try:
            from tabs.image_gallery.services import proxy as _proxy

            cache = _proxy._PROXY_CACHE
            excess = len(cache) - _proxy.PROXY_CACHE_LIMIT
            if excess <= 0:
                return 0
            for key in list(cache)[:excess]:
                try:
                    del cache[key]
                except Exception:
                    pass
            return max(0, excess)
        except Exception:
            return 0

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
                ranks = _rank(members, mode=mode)
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

    def analyze_item_by_path(self, path: Path) -> None:
        item = self._find_item(path)
        if item is None:
            return
        self.analyze_item(item)

    def hydrate_cached_analysis(self, item: GalleryItem) -> bool:
        """Fill ``item`` from the disk cache only (Quick Look pre-read).

        No worker, no settings check — lets the overlay show a cached
        analysis the moment it opens instead of waiting for an Analyze
        click. Refreshes the card when something was hydrated. Never raises.
        """
        try:
            from tabs.image_gallery.services.ai_cache import hydrate_item
        except Exception:
            return False
        try:
            if not hydrate_item(item):
                return False
        except Exception:
            return False
        try:
            self.widget.refresh_card(item)
        except Exception:
            pass
        return True

    def _hydrate_ai_cache(self, items) -> int:
        """Fill pool items from the AI disk cache on a pool (re)build.

        Closed-tab / re-loaded-folder recovery: the live ``analyze_item``
        path is cache-first, but a pool rebuild (session restore, folder
        open, append) had no such pass, so previously analyzed images came
        back "not analyzed" until some other trigger ran — even though the
        results sat in the disk cache. This pass fills them at rebuild so the
        read is present the moment the pool appears; the metrics-pass settle
        then re-derives only the still-missing scorecards (AI domain only,
        ``_run_ai_on_settle``). Cache-only: no worker, no settings check, no
        API call. Never raises; returns how many items were filled.
        """
        try:
            from tabs.image_gallery.services.ai_cache import hydrate_item
        except Exception:
            return 0
        filled = 0
        for it in list(items or []):
            try:
                if getattr(it, "analysis", None) is not None:
                    continue
                if hydrate_item(it):
                    filled += 1
            except Exception:
                continue
        return filled

    def analyze_item(self, item: GalleryItem) -> None:
        cached = load_cached_analysis(item.path, item.mtime_ns)
        if cached is not None:
            try:
                from tabs.image_gallery.services.ai_client import _ai_debug

                _ai_debug("analyze cache HIT path=%s (no API call)", item.path)
            except Exception:
                pass
            item.analysis = cached
            item.analysis_status = AnalysisStatus.DONE
            item.analysis_error = None
            self.widget.refresh_card(item)
            return

        self._begin_analysis(item)

    def reanalyze_item_by_path(self, path: Path) -> None:
        item = self._find_item(path)
        if item is None:
            return
        self.reanalyze_item(item)

    def reanalyze_item(self, item: GalleryItem) -> None:
        """Force a fresh analysis, bypassing the disk cache (Re-analyze).

        Same worker pipeline as :meth:`analyze_item` minus the cache
        short-circuit; completion overwrites the cache entry. Never raises.
        """
        try:
            self._begin_analysis(item)
        except Exception:
            pass

    #: Lazy-AI cap: the domain switch analyzes only the VISIBLE items, bounded
    #: so flipping to AI never turns into a whole-folder API flood.
    _AI_VISIBLE_CAP = 12

    def _set_judgment_domain(self, domain: str) -> str:
        """The ONLY writer of the judgment domain (Algorithms vs AI).

        ``self._judgment_domain`` is the single authority and survives the
        ``GalleryState`` rebuilds done by open_folder / append / clear_to_empty;
        ``state.judgment_domain``/``state.rank_domain`` are read-only projections
        kept for rendering. Returns the normalized value.
        """
        dom = str(domain or "").strip().lower()
        dom = dom if dom in ("algorithms", "ai") else "algorithms"
        self._judgment_domain = dom
        try:
            self.state.judgment_domain = dom
            self.state.rank_domain = dom
        except Exception:
            pass
        return dom

    def activate_judgment_domain(self, domain: str) -> None:
        """Apply the toolbar domain switch (plan-gallery-two-domain-axes).

        Switching to ``ai`` is the switch's actual effect: it lazily analyzes
        the **visible** items (cache-first, in-flight skipped, capped). Not
        configured / no key degrades to the existing per-item error on the cards
        — the control always does something visible, never a silent no-op.
        Switching back to ``algorithms`` only flips the report domain; it never
        cancels in-flight work.
        """
        try:
            from tabs.image_gallery.models import JUDGMENT_DOMAINS

            if str(domain or "").strip().lower() not in tuple(JUDGMENT_DOMAINS):
                domain = "algorithms"
        except Exception:
            domain = "algorithms"
        # Single authoritative setter; state/widget mirror it for rendering.
        dom = GalleryController._set_judgment_domain(self, domain)
        # An EXPLICIT domain switch re-opens the rank stage: switching back to AI
        # must re-apply the pinned Jev rank (cache-first, no second HTTP) even
        # though the same fingerprint already completed for this folder
        # generation (the Algorithms switch re-derived the ranks to fusion in
        # between). The settled-pass trigger does NOT invalidate, so a second
        # settle over unchanged inputs stays a no-op.
        try:
            gate = getattr(self, "_stage_gate", None)
            if gate is not None:
                gate.invalidate()
        except Exception:
            logger.debug("domain switch stage-gate invalidate failed", exc_info=True)
        # WHY Jev did / did not run: the domain switch is the only trigger for
        # the AI ranker (algorithms ⇒ no Jev call at all). Same IMGSLI_AI_DEBUG key.
        _ai_debug("judgment domain -> %s (%s)", dom, "Jev on" if dom == "ai" else "Jev off")
        # The open quick-look report/dots are domain-scoped: re-render them for
        # the new domain (VLM read ↔ detectors) without a reopen. (getattr keeps
        # this safe on the fake controllers the domain-switch tests drive.)
        refresh_ql = getattr(self, "_refresh_open_quick_look", None)
        if callable(refresh_ql):
            refresh_ql()
        # Card dots are domain-scoped too — repaint every card for the new read.
        try:
            items = list(getattr(self.state, "items", None) or [])
            refresh_cards = getattr(self.widget, "refresh_cards", None)
            if callable(refresh_cards) and items:
                refresh_cards(items)
            else:
                refresh_card = getattr(self.widget, "refresh_card", None)
                if callable(refresh_card):
                    for it in items:
                        refresh_card(it)
        except Exception:
            logger.debug("domain switch card refresh failed", exc_info=True)
        if dom != "ai":
            # Back to Algorithms: re-derive the deterministic fusion rank (a
            # Jev rank is only in effect while the AI domain owns the rank).
            try:
                self._apply_fusion_ranks(getattr(self.state, "series", None))
            except Exception:
                logger.debug("domain switch rank re-derive failed", exc_info=True)
            self._clear_series_priority()
            return
        self._run_ai_for_visible()
        self._run_jev_ranks()
        self._run_series_priority()

    def _run_ai_for_visible(self) -> None:
        """Analyze the currently-visible, not-yet-analyzed items (bounded)."""
        try:
            vis = getattr(self.widget, "visible_paths", None)
            paths = vis() if callable(vis) else None
        except Exception:
            paths = None
        try:
            keys = {str(p) for p in (paths or [])}
        except Exception:
            keys = set()
        picked: list = []
        try:
            items = list(getattr(self.state, "items", None) or [])
        except Exception:
            items = []
        for it in items:
            try:
                if keys and str(it.path) not in keys:
                    continue
                status = getattr(it, "analysis_status", None)
                if status in (AnalysisStatus.DONE, AnalysisStatus.PENDING):
                    continue
            except Exception:
                continue
            picked.append(it)
        if not keys:
            # Viewport not laid out yet — bound instead of flooding.
            picked = picked[: self._AI_VISIBLE_CAP]
        for it in picked[: self._AI_VISIBLE_CAP]:
            try:
                self.analyze_item(it)
            except Exception:
                continue

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
                members, mode, str(getattr(self, "_judgment_domain", "algorithms"))
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
    def _jev_measured_vector(members, mode, domain: str = "algorithms") -> dict:
        """Applicable scoring vector for *members* (per-mode axes only).

        *domain* picks the read: the AI domain's VLM scorecard or the Algorithms
        domain's local detectors (plan-gallery-ai-backend-owns-quality).
        """
        try:
            from tabs.image_gallery.services.jev_client import build_measured_vector

            return build_measured_vector(members, mode=mode, domain=domain)
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
            # The AI domain ranks from the VLM scorecard (durable authority).
            return rank_series_jev_detailed(
                snapshot,
                mode=mode,
                client=client,
                domain=str(getattr(self, "_judgment_domain", "algorithms")),
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

    def _begin_analysis(self, item: GalleryItem) -> None:
        settings = self._ai_settings_store.load()
        if not settings.enabled or not settings.api_key or not settings.model:
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = self._tr(
                "image_gallery.errors.not_configured",
                "Configure the AI API key in Settings first.",
            )
            self.widget.refresh_card(item)
            return

        item.analysis_status = AnalysisStatus.PENDING
        item.analysis_error = None
        set_activity(item, ActivityPhase.QUEUED, "ai")
        self.widget.refresh_card(item)

        try:
            from tabs.image_gallery.services.ai_client import _ai_debug

            _ai_debug(
                "analyze MISS -> API call path=%s model=%s base_url=%s",
                item.path,
                settings.model,
                settings.base_url,
            )
        except Exception:
            pass

        # Local (Algorithms-domain) numbers ride along as CONTEXT; the AI
        # returns its own per-axis scorecard (the AI-domain read).
        try:
            _metrics = dict(getattr(item, "metrics", None) or {})
        except Exception:
            _metrics = {}
        bridge = _ActivityPhaseBridge(lambda phase, it=item: self._apply_ai_phase(it, phase))
        worker = GenericWorker(
            self._tracked(analyze_image_sync),
            item.path,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            mode=getattr(self.state, "mode", None),
            metrics=_metrics,
            on_phase=bridge.phase.emit,
        )
        gen = self._folder_gen
        # ``bridge=bridge`` keeps the phase relay alive until the worker reports.
        worker.signals.result.connect(
            lambda result, path=item.path, mtime_ns=item.mtime_ns, g=gen, bridge=bridge: self._on_analysis_ready(
                path, mtime_ns, result, g
            )
        )
        worker.signals.error.connect(
            lambda err, path=item.path, g=gen, bridge=bridge: self._on_analysis_error(path, err, g)
        )
        set_activity(item, ActivityPhase.CLAIMED, "ai")
        self.widget.refresh_card(item)
        self._pool_start(worker, None)

    def _apply_ai_phase(self, item: GalleryItem, phase: str) -> None:
        """UI-thread sink for worker phase emits; drops phases of stale items."""
        if self._find_item(item.path) is not item:
            return
        set_activity(item, phase, "ai")
        self.widget.refresh_card(item)

    def _on_analysis_ready(self, path: Path, mtime_ns: int, result, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late analysis dropped
        item = self._find_item(path)
        if item is None:
            return
        # The VLM's result IS the AI-domain read (plan-gallery-ai-backend-owns-
        # quality): no detector merge here — the Algorithms domain keeps reading
        # ``item.metrics`` through ``services.quality_read``.
        save_analysis(path, mtime_ns, result)
        item.analysis = result
        item.analysis_status = AnalysisStatus.DONE
        item.analysis_error = None
        set_activity(item, ActivityPhase.DONE, "ai")
        self.widget.refresh_card(item)
        # The AI scorecard IS the AI-domain read — rebuild the open overlay's
        # rows/dots in place so they switch to the VLM numbers without a reopen.
        self._refresh_open_quick_look()
        # A new scorecard changes the Jev ranking vector: coalesce the batch of
        # arrivals into one AI-rank pass (no-op off the AI domain).
        self._queue_ai_rank_on_settle()

    def _refresh_open_quick_look(self) -> None:
        """Rebuild the open quick-look report rows + dots for the current domain.

        The report is domain-scoped (``services.quality_read``); a domain switch
        or a fresh analysis must re-render it in place, not on reopen.
        """
        try:
            ql = getattr(self.widget, "_quick_look_overlay", None)
            if ql is None:
                return
            item = getattr(ql, "_current_item", None)
            if item is None:
                return
            if hasattr(ql, "refresh_metrics"):
                ql.refresh_metrics(item)
            if hasattr(ql, "refresh_artifacts"):
                ql.refresh_artifacts(item)
        except Exception:
            logger.debug("quick-look domain refresh failed", exc_info=True)

    def _on_analysis_error(self, path: Path, error_info, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        item = self._find_item(path)
        if item is None:
            return
        exctype, value, _tb = error_info
        message = None
        for error_cls, (key, default) in _ERROR_KEYS.items():
            if isinstance(value, error_cls) or (
                isinstance(exctype, type) and issubclass(exctype, error_cls)
            ):
                message = self._tr(key, default)
                break
        if message is None and isinstance(value, AiClientError):
            message = str(value)
        item.analysis_status = AnalysisStatus.ERROR
        item.analysis_error = message or str(value)
        set_activity(item, ActivityPhase.ERROR, "ai")
        self.widget.refresh_card(item)

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
        """Local-metric epsilon check for top-2 tie-break eligibility."""
        try:
            da = a.metrics.get("embedding_dist_to_centroid")
            db = b.metrics.get("embedding_dist_to_centroid")
            if da is not None and db is not None:
                return abs(float(da) - float(db)) < epsilon
            # Fallback: sharpness / ssim deltas
            for key in ("sharpness", "ssim", "artifact_score"):
                va = a.metrics.get(key)
                vb = b.metrics.get(key)
                if va is not None and vb is not None:
                    try:
                        av, bv = float(va), float(vb)
                        denom = max(abs(av), abs(bv), 1e-6)
                        if abs(av - bv) / denom < epsilon * 2:
                            return True
                    except Exception:
                        continue
            # No metrics → conservative: treat rank-1 vs rank-2 as tie candidate if phash close?
            # Use hamming of phash if available
            pa = a.metrics.get("phash")
            pb = b.metrics.get("phash")
            if isinstance(pa, int) and isinstance(pb, int):
                ham = bin(int(pa) ^ int(pb)).count("1")
                if ham <= 4:
                    return True
            return False
        except Exception:
            return False

    def run_tie_break_if_needed(self, series) -> None:
        """Stage 3: selective VLM tie-break for top-2 when local metrics within epsilon.

        *series* may be a ``Series`` dataclass (has .members) or plain list[GalleryItem].
        Sets badge ``AI tie-break…`` pending on both candidates until resolved;
        degrades silent-but-visible if unresolved (badge cleared, local ranking kept).
        Uses ``GenericWorker`` (never UI-blocking), cached via ``vlm_cache`` (hash paths+mtime).
        """
        try:
            members = list(getattr(series, "members", series) or [])
        except Exception:
            return
        if len(members) < 2:
            return
        # Candidates come from the MEASURED FUSION order (not the old centroid
        # distance/rank): the VLM tie-break is additive on top of the
        # Algorithms rank, so its top-2 must be the fusion top-2.
        try:
            from tabs.image_gallery.services.rank_fusion import rank_series as _rank

            fusion = _rank(members, mode=getattr(self.state, "mode", None))
        except Exception:
            fusion = {}

        def _sort_key(it: GalleryItem):
            try:
                r = fusion.get(str(getattr(it, "path", "")))
            except Exception:
                r = None
            try:
                rk = int(r) if r is not None else 1 << 30
            except Exception:
                rk = 1 << 30
            try:
                return (rk, str(getattr(it, "path", "")))
            except Exception:
                return (rk, "")

        sorted_members = sorted(members, key=_sort_key)
        top2 = sorted_members[:2]
        if len(top2) < 2:
            return
        a, b = top2[0], top2[1]
        if not self._is_tie(a, b):
            return

        # Use existing analyze_image_sync only via VLM targeted path — tie-break needs 2 images.
        settings = self._ai_settings_store.load()
        from tabs.image_gallery.services.vlm import set_vlm_max_edge

        set_vlm_max_edge(settings.vlm_max_edge_px)
        # Degrade silent-but-visible if AI not configured: keep local ranking, no badge
        if not settings.enabled or not settings.api_key or not settings.model:
            logger.debug("tie-break skipped: AI not configured (silent degrade)")
            return

        # Resolve source path for fidelity mode (if available) — needed early for cache key source_mtime
        source = getattr(self.state, "source_path", None)
        try:
            source = Path(source) if source is not None else None
        except Exception:
            source = None
        # source_mtime for vlm_cache key (design parity: hash(paths+mtime+source_mtime))
        source_mtime: int | None = None
        if source is not None:
            try:
                si = self._find_item(source)
                if si is not None:
                    source_mtime = int(getattr(si, "mtime_ns", 0) or 0) or None
                else:
                    source_mtime = int(Path(source).stat().st_mtime_ns)
            except Exception:
                source_mtime = None

        # Check cache first (key = hash(paths+mtime+source_mtime))
        try:
            from tabs.image_gallery.services.vlm_cache import load_cached_tie_break, save_tie_break
        except Exception:
            load_cached_tie_break = None  # type: ignore
            save_tie_break = None  # type: ignore

        if load_cached_tie_break is not None:
            try:
                cached = load_cached_tie_break(a.path, a.mtime_ns, b.path, b.mtime_ns, source_mtime)
                if cached is not None:
                    self._apply_tie_break_result(a, b, cached)
                    return
            except Exception:
                logger.debug("tie-break cache load failed", exc_info=True)

        # Badge pending on both candidates
        for it in top2:
            it.vlm_tie_pending = True
            it.vlm_tie_error = None
            try:
                self.widget.refresh_card(it)
            except Exception:
                pass

        from tabs.image_gallery.services.vlm import tie_break_sync

        worker = GenericWorker(
            tie_break_sync,
            a.path,
            b.path,
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            source=source,
        )

        def _on_result(result, a_path=a.path, b_path=b.path, a_mtime=a.mtime_ns, b_mtime=b.mtime_ns, _src_mtime=source_mtime, gen=self._folder_gen):
            if not self._is_current_folder_gen(gen):
                return  # folder switched mid-VLM — late tie-break dropped
            try:
                if save_tie_break is not None:
                    save_tie_break(a_path, a_mtime, b_path, b_mtime, result, _src_mtime)
            except Exception:
                logger.debug("tie-break cache save failed", exc_info=True)
            # Find current items (may have been refreshed)
            item_a = self._find_item(a_path)
            item_b = self._find_item(b_path)
            if item_a is None or item_b is None:
                return
            self._apply_tie_break_result(item_a, item_b, result)

        def _on_error(error_info, top2_paths=(a.path, b.path), gen=self._folder_gen):
            if not self._is_current_folder_gen(gen):
                return
            logger.debug("tie-break worker error: %r", error_info, exc_info=True)
            # Silent-but-visible degrade: clear pending badge, keep local ranking
            for p in top2_paths:
                it = self._find_item(p)
                if it is not None:
                    it.vlm_tie_pending = False
                    # keep vlm_tie_error visible as tooltip but not badge
                    try:
                        exctype, value, _tb = error_info
                        it.vlm_tie_error = str(value)[:200] if value is not None else "tie-break unresolved"
                    except Exception:
                        it.vlm_tie_error = "tie-break unresolved"
                    try:
                        self.widget.refresh_card(it)
                    except Exception:
                        pass

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._pool_start(worker, None)

    def _apply_tie_break_result(self, a: GalleryItem, b: GalleryItem, result) -> None:
        """Apply VLM winner: mark winner is_best/crown_rank, clear pending badges."""
        try:
            winner_str = str(getattr(result, "winner_path", ""))
            loser_str = str(getattr(result, "loser_path", ""))
            # Resolve which of a,b is winner by path equality (resolve-aware)
            def _matches(item: GalleryItem, s: str) -> bool:
                try:
                    return str(item.path.resolve()) == s or str(item.path) == s
                except Exception:
                    return str(item.path) == s

            winner = a if _matches(a, winner_str) else (b if _matches(b, winner_str) else a)
            loser = b if winner is a else a
            # Additive crown: the VLM verdict overlays ``crown_rank``/``is_best``
            # on top of the fusion rank (#N is crown_rank ?? rank in
            # ``rank_badge``). ``rank`` stays the measured-fusion number — the
            # AI hint never fabricates a measured rank.
            try:
                winner.is_best = True
                winner.crown_rank = 1
                winner.vlm_tie_result = result
            except Exception:
                pass
            try:
                loser.is_best = False
                loser.crown_rank = 2
                loser.vlm_tie_result = result
            except Exception:
                pass
            for it in (a, b):
                it.vlm_tie_pending = False
                it.vlm_tie_error = None
                try:
                    self.widget.refresh_card(it)
                except Exception:
                    pass
            # Persist in state
            try:
                key = getattr(a, "series_id", None) or getattr(b, "series_id", None) or f"{a.path}:{b.path}"
                self.state.tie_breaks[str(key)] = result
            except Exception:
                pass
        except Exception:
            logger.debug("apply tie-break failed", exc_info=True)
            for it in (a, b):
                try:
                    it.vlm_tie_pending = False
                    self.widget.refresh_card(it)
                except Exception:
                    pass

    def _apply_brief_result(self, pa: Path, pb: Path, result, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late brief dropped
        try:
            # Persist in state (one per pair)
            try:
                key = f"{Path(pa).resolve()}:{Path(pb).resolve()}"
                if str(Path(pa).resolve()) > str(Path(pb).resolve()):
                    key = f"{Path(pb).resolve()}:{Path(pa).resolve()}"
                self.state.briefs[key] = result
            except Exception:
                pass
            for p in (pa, pb):
                it = self._find_item(p)
                if it is not None:
                    it.vlm_brief = result
                    it.vlm_brief_status = "done"
                    it.vlm_brief_error = None
                    try:
                        self.widget.refresh_card(it)
                    except Exception:
                        pass
        except Exception:
            logger.debug("apply brief failed", exc_info=True)

    # -- Stage 2 crown/reject/S3 (thin wrappers → use_cases/triage) --------

    def _mark_triage_picks_manual(self) -> int:
        """Freeze explicit triage winners (``triage_best``) as manual ranks.

        Keep best / Make best mark their winners ``triage_best``; those are the
        user's explicit decisions. The gallery UI reaches the triage helpers
        directly (not through ``make_best``/``keep_best_of_series``), so this is
        the seam that keeps the badge provenance truthful in production: it is
        invoked right before a rank snapshot is mirrored. Returns items flagged.
        """
        try:
            items = list(getattr(self.state, "items", None) or ())
        except Exception:
            items = []
        picked = [it for it in items if bool(getattr(it, "triage_best", False))]
        return self._mark_rank_manual(picked)

    def _mark_rank_manual(self, items) -> int:
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

    def _item_for_path(self, path):
        try:
            target = path if isinstance(path, Path) else Path(path)
        except Exception:
            return None
        try:
            items = list(getattr(self.state, "items", None) or ())
        except Exception:
            items = []
        for it in items:
            try:
                if Path(getattr(it, "path", None)) == target:
                    return it
            except Exception:
                continue
        return None

    def make_best(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases.triage import make_best as _make_best

        ok = bool(_make_best(self, path))
        if ok:
            # The explicit pick is manual; the remaining members are re-derived
            # from the fusion around the anchored manual rank.
            self._mark_rank_manual([self._item_for_path(path)])
            self._apply_fusion_ranks(getattr(self.state, "series", None))
            try:
                from tabs.image_gallery.use_cases.triage import (
                    _refresh_owner_grid as _refresh,
                )

                _refresh(self)
            except Exception:
                pass
        return ok

    def toggle_reject(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases.triage import toggle_reject as _toggle

        return bool(_toggle(self, path))

    def remove_from_grid(self, path: Path) -> bool:
        from tabs.image_gallery.use_cases.triage import remove_from_grid as _remove

        return bool(_remove(self, path))

    def remove_paths_from_grid(self, paths) -> int:
        from tabs.image_gallery.use_cases.triage import remove_paths_from_grid as _remove_many

        return int(_remove_many(self, paths))

    def keep_best_of_series(self) -> dict:
        from tabs.image_gallery.use_cases.triage import keep_best_of_series as _keep

        result = _keep(self)
        # Every keeper (explicit per-series user decision) is manual; the rest
        # is re-derived from the fusion around the anchored winners.
        try:
            items = list(getattr(self.state, "items", None) or ())
        except Exception:
            items = []
        keepers = [it for it in items if bool(getattr(it, "is_best", False))]
        self._mark_rank_manual(keepers)
        self._apply_fusion_ranks(getattr(self.state, "series", None))
        try:
            from tabs.image_gallery.use_cases.triage import (
                _refresh_owner_grid as _refresh,
            )

            _refresh(self)
        except Exception:
            pass
        return result

    def show_all(self) -> int:
        from tabs.image_gallery.use_cases.triage import show_all as _show

        return int(_show(self))

    # -- manual series overrides (Wave B drop targets) ---------------------

    def move_paths_to_series(self, paths, series_id: str | None) -> int:
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
            pool = {str(it.path) for it in self.state.items}
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
            for it in self.state.items:
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
        moved = int(_override.set_override(self._series_overrides, [str(p) for p in in_pool], sid))
        try:
            live = list(self.state.items)
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
            last_series = list(self.state.series or [])
            regrouped = _override.apply_overrides(live, self._series_overrides, last_series)
            regrouped = self._restore_singletons(
                live, self._series_overrides, pre_ids, last_series, regrouped
            )
            # Newer than any in-flight triage: its delivery drops (sgen).
            self._next_series_gen()
            self._apply_series_view(regrouped)
        except Exception:
            logger.debug("move_paths_to_series regroup failed", exc_info=True)
        return moved

    def group_paths_as_new_series(self, paths) -> str | None:
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
            with self._series_id_lock:
                used: set[str] = set()
                try:
                    for v in (self._series_overrides or {}).values():
                        if v is not None:
                            used.add(str(v))
                except Exception:
                    pass
                try:
                    for entry in (self.state.series or []):
                        eid = GalleryController._section_id(
                            entry, GalleryController._section_members(entry)
                        )
                        if eid is not None:
                            used.add(str(eid))
                except Exception:
                    pass
                # Same convention as translate_computed_to_stable: the
                # counter holds the LAST issued number, candidates start
                # past it (monotonic, never reused, gaps allowed).
                try:
                    n = int(self._series_next_id or 1)
                except Exception:
                    n = 1
                while True:
                    n += 1
                    if f"series_{n}" not in used:
                        break
                new_id = f"series_{n}"
                try:
                    self._series_next_id = int(n)
                except Exception:
                    pass
        except Exception:
            return None
        try:
            moved = int(self.move_paths_to_series(targets, new_id))
        except Exception:
            return None
        return new_id if moved > 0 else None

    def _attach_append_items(self, new_items) -> dict:
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
        members_of = GalleryController._section_members
        id_of = GalleryController._section_id
        try:
            groups = list(self.state.series or [])
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
                    has_pin = key in (self._series_overrides or {})
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
                has_pin = key in (self._series_overrides or {})
                pin = (self._series_overrides or {}).get(key) if has_pin else "auto"
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
            self.state.series = groups  # type: ignore[assignment]
        except Exception:
            pass
        return attached

    def _cluster_tail_into_series(self) -> list:
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
        try:
            items = list(getattr(self.state, "items", None) or [])
            groups = list(getattr(self.state, "series", None) or [])
        except Exception:
            return []
        try:
            member_paths: set[str] = set()
            for entry in groups:
                for m in GalleryController._section_members(entry):
                    try:
                        member_paths.add(str(getattr(m, "path", None)))
                    except Exception:
                        continue
        except Exception:
            member_paths = set()
        try:
            pinned = {str(k) for k in (getattr(self, "_series_overrides", None) or {})}
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
            fresh_groups, _ = self._assign_fresh_stable_ids(fresh_groups)
        except Exception:
            pass
        try:
            self.state.series = list(groups) + list(fresh_groups)
        except Exception:
            return []
        return list(fresh_groups)

    def recluster_series(self) -> None:
        """Fresh cluster+apply world with pins re-applied + rebuild.

        Header/grid menu entry next to Reset. Unlike ``reset`` (which
        clears pins), pins are KEPT: the existing ``_start_triage``
        pipeline snapshots + re-applies overrides, assigns fresh stable
        ids to auto groups, and rebuilds on delivery (``cover_grid=False``
        — live groups stay visible until the fresh world lands).
        """
        try:
            items = list(self.state.items)
        except Exception:
            items = []
        try:
            self._start_triage(items, cover_grid=False)
        except Exception:
            logger.debug("recluster_series start failed", exc_info=True)

    def reset_series_overrides(self) -> int:
        """Clear every manual series override + regroup automatically.

        Reset affordance behind the series-header context menu
        (``ui/drag_drop`` installs it at runtime — ``grid_view.py`` stays
        untouched). Reuses the existing ``_start_triage`` rebuild path.
        Returns entries cleared (0 = no rebuild).
        """
        try:
            cleared = len(self._series_overrides)
        except Exception:
            cleared = 0
        try:
            self._series_overrides.clear()
        except Exception:
            pass
        if not cleared:
            return 0
        try:
            self._start_triage(list(self.state.items), cover_grid=False)
        except Exception:
            logger.debug("reset_series_overrides retriage failed", exc_info=True)
        return cleared

    def clean_rejected(self) -> list[dict]:
        from tabs.image_gallery.use_cases.triage import clean_rejected as _clean

        return _clean(self)

    def show_clean_review(self) -> None:
        # Delegate to widget's S3 overlay (TopLevelInWindowOverlay).
        try:
            if hasattr(self.widget, "show_clean_review"):
                self.widget.show_clean_review(self)
        except Exception:
            pass

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
