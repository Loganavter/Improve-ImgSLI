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
from PySide6.QtGui import QPixmap
from sli_ui_toolkit.workers import GenericWorker

from core.state_management.gallery_actions import (
    GalleryFilterSet,
    GalleryPathsAppended,
    GalleryPoolOpened,
    GalleryPoolReplaced,
    GallerySelectionSet,
    GalleryThumbnailsReady,
    GalleryTriageFinished,
)
from tabs.image_gallery.bootstrap_reducers import GALLERY_SLOT_NAME
from tabs.image_gallery.state import selectors as _gallery_selectors

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
    AiAuthError,
    AiClientError,
    AiNetworkError,
    AiRateLimitError,
    AiResponseError,
    analyze_image_sync,
)
from tabs.image_gallery.services.ai_settings_store import AiSettingsStore
from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_dnd_debug as _dnd_log
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
from tabs.image_gallery.services.folder_scanner import scan_folder
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
        """Store behind ``context.store`` (None in storeless unit contexts)."""
        store = getattr(self._context, "store", None)
        if store is None or not hasattr(store, "get_dispatcher"):
            return None
        return store

    def _ensure_gallery_subscription(self) -> None:
        """Learn of slot changes via store.on_change (session_init precedent).

        Subscriber filters on scope == 'gallery' in _on_store_changed and
        reconciles the local mirror (thumbnail loads for new metas + grid
        rebuild reading the slot via selectors). No-op without a store.
        """
        store = self._gallery_store()
        if store is None or self._subscribed_gallery_store is store:
            return
        try:
            if hasattr(store, "on_change"):
                store.on_change(self._on_store_changed)
                self._subscribed_gallery_store = store
        except Exception:
            logger.debug("gallery slot subscription failed", exc_info=True)

    def bind_gallery_session(self, session_id: str | None) -> None:
        """(Re)bind this live copy to its OWN session id.

        Called by ``ImageGalleryTab`` when the tab session is known
        (create_page, on_active_session_changed, activation refresh). The
        ONLY place the binding changes — slot reads never re-resolve.
        """
        self._gallery_session_id = session_id

    def _capture_initial_gallery_session_id(self) -> str | None:
        """Best-effort own-id capture at construction (tab bind wins later).

        Only a gallery-typed active session is adopted — capturing a
        foreign tab's session id would invert the is-active gate.
        """
        try:
            store = self._gallery_store()
            if store is None:
                return None
            sess = store.get_active_workspace_session()
            if sess is None:
                return None
            if getattr(sess, "session_type", None) not in (None, "image_gallery"):
                return None
            return getattr(sess, "id", None)
        except Exception:
            return None

    def _is_active_gallery_tab(self) -> bool:
        """THE sanctioned active read: own id vs active session METADATA.

        True when this copy serves the active session (or when no binding
        is known yet — unbound/storeless copies fail open to legacy
        behavior). Emit handlers skip when False; slot DATA is never read
        here.
        """
        try:
            store = self._gallery_store()
            if store is None:
                return True
            own = self._gallery_session_id
            if own is None:
                return True
            active = store.get_active_workspace_session()
            if active is None:
                return True
            active_id = getattr(active, "id", None)
            if active_id is None:
                return True
            return active_id == own
        except Exception:
            return True

    def _gallery_slot(self):
        """Read path: store.get_session_state_slot('gallery', session_id=<own>)."""
        store = self._gallery_store()
        if store is None or not hasattr(store, "get_session_state_slot"):
            return None
        try:
            return store.get_session_state_slot(GALLERY_SLOT_NAME, session_id=self._gallery_session_id)
        except Exception:
            return None

    def _emit_gallery(self, action) -> bool:
        """Write path: dispatcher.dispatch(..., scope='gallery', session_id=<own>).

        Session-targeted (Wave CORE): a background copy's late worker
        completion lands in its OWN session's slots even while another tab
        is active. None-safe: unbound (None) falls back to the default
        active path, fail-open as before.
        Never mutates slot values directly. Returns False (local-only) when
        no dispatcher is wired — callers always mirror locally first.
        """
        # A triage rank snapshot is the moment the local ranks were just
        # (re)written; freeze any explicit Keep/Make best winner as a manual
        # rank first so the mirrored provenance is truthful (the UI reaches the
        # triage helpers directly, not through the wrappers below).
        if isinstance(action, GalleryTriageFinished):
            try:
                self._mark_triage_picks_manual()
            except Exception:
                pass
        store = self._gallery_store()
        if store is None:
            return False
        try:
            self._ensure_gallery_subscription()
            dispatcher = store.get_dispatcher()
            if dispatcher is None:
                return False
            self._own_gallery_emits += 1
            try:
                dispatcher.dispatch(action, scope=GALLERY_SLOT_NAME, session_id=self._gallery_session_id)
            except Exception:
                self._own_gallery_emits -= 1
                raise
            return True
        except Exception:
            logger.debug("_emit_gallery dispatch failed", exc_info=True)
            return False

    def _transact_gallery(self, actions) -> bool:
        """Batch path: Store.transact([...], scope='gallery') — one emit."""
        store = self._gallery_store()
        batch = [a for a in actions or []]
        if store is None or not batch:
            return False
        try:
            self._ensure_gallery_subscription()
            if store.get_dispatcher() is None:
                return False
            self._own_gallery_emits += 1
            try:
                store.transact(list(batch), scope=GALLERY_SLOT_NAME, session_id=self._gallery_session_id)
            except Exception:
                self._own_gallery_emits -= 1
                raise
            return True
        except Exception:
            logger.debug("_transact_gallery failed", exc_info=True)
            return False

    def _on_store_changed(self, scope: str) -> None:
        if scope != GALLERY_SLOT_NAME:
            return
        if not self._is_active_gallery_tab():
            # A foreign session's emit (e.g. tab B opening on an
            # empty/loading slot) must never reconcile THIS copy's mirror.
            return
        if self._own_gallery_emits > 0:
            # Own dispatch: the local mirror was updated before emitting, so
            # reconcile selection/filter only (cheap no-op). Scalars/ranks
            # stay local — the slot cannot be newer than what we just sent.
            self._own_gallery_emits -= 1
            slot = self._gallery_slot()
            if slot is None:
                return
            try:
                before_filter = self.state.filter_text
                self._apply_slot_selection_filter(slot)
                if self.state.filter_text != before_filter:
                    self._apply_filter_fast(self.state.filter_text)
            except Exception:
                pass
            return
        # Undo / widget-gesture / external dispatch: the slot is authoritative.
        self._sync_from_slot()

    def _sync_from_slot(self) -> None:
        """Authoritative reconcile from the slot (undo / external changes).

        Thumbnail LOADING flags, pixmaps and workers are never reset here
        beyond starting loads for genuinely new metas; series objects (not
        in the slot) are left untouched and triage is never restarted.
        """
        slot = self._gallery_slot()
        if slot is None:
            return
        try:
            slot_paths = _gallery_selectors.get_item_paths(slot)
        except Exception:
            return
        try:
            local_paths = [str(it.path) for it in self.state.items]
        except Exception:
            return
        if slot_paths == local_paths:
            try:
                before_filter = self.state.filter_text
                self._apply_slot_selection_filter(slot)
                if self.state.filter_text != before_filter:
                    self._apply_filter_fast(self.state.filter_text)
            except Exception:
                pass
            self._apply_slot_ranks(slot)
            self._apply_slot_triage_scalars(slot)
            return
        # Membership differs (undo / external replace): rebuild the mirror,
        # preserving rich local objects (pixmaps, analysis) by path.
        by_path: dict[str, GalleryItem] = {}
        for it in self.state.items:
            try:
                by_path[str(it.path)] = it
            except Exception:
                continue
        new_items: list[GalleryItem] = []
        fresh: list[GalleryItem] = []
        try:
            metas = _gallery_selectors.get_items(slot)
        except Exception:
            return
        for meta in metas:
            old = by_path.get(meta.path)
            if old is not None:
                try:
                    if meta.mtime_ns != old.mtime_ns:
                        old.mtime_ns = meta.mtime_ns
                except Exception:
                    pass
                new_items.append(old)
            else:
                try:
                    item = GalleryItem(path=Path(meta.path), mtime_ns=meta.mtime_ns)
                except Exception:
                    continue
                new_items.append(item)
                fresh.append(item)
        self.state.items = new_items
        try:
            folder = _gallery_selectors.get_folder(slot)
            self.state.folder = Path(folder) if folder else None
        except Exception:
            pass
        self._apply_slot_selection_filter(slot)
        self._apply_slot_triage_scalars(slot)
        try:
            if self.state.folder is not None:
                self.widget.set_folder_label(self.state.folder)
        except Exception:
            pass
        # Restore cached AI analyses (no network) so a reopened tab shows the
        # previous results instead of "not analyzed".
        self._hydrate_ai_cache(new_items)
        try:
            self.widget.rebuild_grid(new_items)
        except Exception:
            logger.debug("gallery slot sync rebuild_grid failed", exc_info=True)
        for item in fresh:
            try:
                self._load_thumbnail(item)
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
                    and str(getattr(self.state, "rank_domain", "algorithms") or "")
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
            except Exception:
                pass

    def _apply_slot_ranks(self, slot) -> None:
        """Re-derive series ranks from the measured fusion (undo / external replace).

        The slot no longer owns ranks: the Algorithms rank is a pure function
        of the item's measured metrics, so an authoritative reconcile
        re-derives it from the live series instead of copying a stored number.
        """
        self._apply_fusion_ranks(getattr(self.state, "series", None))

    def _apply_slot_selection_filter(self, slot) -> None:
        try:
            slot_sel = _gallery_selectors.get_selection(slot)
            local_sel = [str(p) for p in self.state.selected_order]
            if slot_sel != local_sel:
                self.state.selected_paths = {Path(s) for s in slot_sel}
                self.state.selected_order = [Path(s) for s in slot_sel]
                try:
                    grid = getattr(self.widget, "_grid_view", None)
                    if grid is not None and hasattr(grid, "apply_selection"):
                        grid.apply_selection(set(self.state.selected_paths))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            slot_filter = _gallery_selectors.get_filter_text(slot)
            if slot_filter != self.state.filter_text:
                self.state.filter_text = slot_filter
        except Exception:
            pass

    def _apply_slot_triage_scalars(self, slot) -> None:
        try:
            summary = _gallery_selectors.get_triage_summary(slot)
        except Exception:
            return
        try:
            self.state.triage_state = TriageState(summary.get("triage_state", "idle"))
        except Exception:
            pass
        try:
            mode = summary.get("mode")
            self.state.mode = Mode(mode) if mode else None
        except Exception:
            pass
        try:
            src = summary.get("source_path")
            self.state.source_path = Path(src) if src else None
        except Exception:
            pass

    def set_selection(self, paths) -> None:
        """Wholesale selection: dispatch GallerySelectionSet + mirror locally.

        Triage UI (keyboard/arrows/Esc) routes through here so selection is
        tracer-visible; storeless owners fall back to direct writes in
        use_cases/triage_ui. Re-selection of the current slot value skips
        the dispatch (reducer identity would no-op without an emit, which
        would leak one unit of own-emit accounting).
        """
        try:
            strs: list[str] = []
            seen: set[str] = set()
            for p in paths or []:
                s = str(p)
                if s not in seen:
                    seen.add(s)
                    strs.append(s)
        except Exception:
            strs = []
        try:
            slot = self._gallery_slot()
            if slot is not None and _gallery_selectors.get_selection(slot) == strs:
                pass
            else:
                self._emit_gallery(GallerySelectionSet(selected_ids=strs))
        except Exception:
            self._emit_gallery(GallerySelectionSet(selected_ids=strs))
        try:
            self.state.selected_paths = {Path(s) for s in strs}
            self.state.selected_order = [Path(s) for s in strs]
        except Exception:
            pass
        try:
            grid = getattr(self.widget, "_grid_view", None)
            if grid is not None and hasattr(grid, "apply_selection"):
                grid.apply_selection(set(self.state.selected_paths))
        except Exception:
            pass

    def set_source(self, path: Path) -> None:
        """Set the triage source image: mirror locally + dispatch.

        Fail-open no-op when ``path`` is None or not in the pool. Carries
        the CURRENT triage_state/mode/ranks via GalleryTriageFinished with
        the new source_path — the single source-action shape, no second
        action kind.
        """
        if path is None:
            return
        try:
            want = str(path)
        except Exception:
            return
        try:
            pool = {str(it.path) for it in self.state.items}
        except Exception:
            return
        if want not in pool:
            return
        try:
            current = getattr(self.state, "triage_state", "idle")
            triage_s = getattr(current, "value", current)
            triage_s = str(triage_s or "idle")
        except Exception:
            triage_s = "idle"
        try:
            self.state.source_path = Path(want)
        except Exception:
            return
        try:
            self._emit_triage_finished(triage_s, source_path=Path(want))
        except Exception:
            logger.debug("set_source dispatch failed", exc_info=True)

    # -- coalesced thumbnail completions (ONE action per event-loop turn) -----

    def _queue_thumb_ready(self, path: Path, status: str) -> None:
        try:
            self._pending_thumb_ready.append((str(path), status))
        except Exception:
            return
        if self._thumb_flush_scheduled:
            return
        self._thumb_flush_scheduled = True
        try:
            if QCoreApplication.instance() is None:
                # No event loop (headless unit context) — flush synchronously.
                self._flush_pending_thumbnails()
            else:
                QTimer.singleShot(0, self._flush_pending_thumbnails)
        except Exception:
            try:
                self._flush_pending_thumbnails()
            except Exception:
                pass

    def _flush_pending_thumbnails(self) -> None:
        self._thumb_flush_scheduled = False
        if not self._pending_thumb_ready:
            return
        batch, self._pending_thumb_ready = self._pending_thumb_ready, []
        # Coalesce same path → last status wins, first-seen order kept.
        last: dict[str, str] = {}
        for path, status in batch:
            last[path] = status
        ready = [(p, last[p]) for p in dict.fromkeys(p for p, _ in batch)]
        # Drop entries the slot already has (reducer identity would no-op
        # without an emit, leaking own-emit accounting).
        try:
            slot = self._gallery_slot()
            if slot is not None:
                current = {
                    m.path: m.status for m in _gallery_selectors.get_items(slot)
                }
                ready = [(p, s) for p, s in ready if current.get(p) != s]
        except Exception:
            pass
        if not ready:
            return
        self._emit_gallery(GalleryThumbnailsReady(ready=ready))

    def flush_pending_thumbnails(self) -> None:
        """Flush a coalesced turn synchronously (tests / teardown)."""
        self._flush_pending_thumbnails()
        self._flush_pending_card_refresh()

    def _queue_card_refresh(self, item) -> None:
        """Defer one card repaint into the per-tick batch (see __init__)."""
        try:
            self._pending_card_items[str(getattr(item, "path", item))] = item
        except Exception:
            return
        if self._card_flush_scheduled:
            return
        self._card_flush_scheduled = True
        try:
            if QCoreApplication.instance() is None:
                # No event loop (headless unit context) — flush synchronously.
                self._flush_pending_card_refresh()
            else:
                QTimer.singleShot(0, self._flush_pending_card_refresh)
        except Exception:
            try:
                self._flush_pending_card_refresh()
            except Exception:
                pass

    def _flush_pending_card_refresh(self) -> None:
        self._card_flush_scheduled = False
        if not self._pending_card_items:
            return
        batch, self._pending_card_items = list(self._pending_card_items.values()), {}
        try:
            refresh_cards = getattr(self.widget, "refresh_cards", None)
            if callable(refresh_cards):
                refresh_cards(batch)
                return
        except Exception:
            pass
        for item in batch:
            try:
                self.widget.refresh_card(item)
            except Exception:
                pass

    def _emit_triage_finished(self, triage_state: str, source_path=None) -> bool:
        """Dispatch GalleryTriageFinished from the local summary + ranks.

        ``source_path`` overrides the mirrored state value when given
        (set_source path); otherwise the current state mirror is carried.
        """
        try:
            ranks: dict[str, int] = {}
            for it in self.state.items:
                try:
                    if it.rank is not None:
                        ranks[str(it.path)] = int(it.rank)
                except Exception:
                    continue
            mode = getattr(self.state, "mode", None)
            mode_s = getattr(mode, "value", mode)
            source = source_path if source_path is not None else getattr(self.state, "source_path", None)
            if source is not None and not isinstance(source, (str, Path)):
                source = None
            return self._emit_gallery(
                GalleryTriageFinished(
                    triage_state=triage_state,
                    mode=str(mode_s) if mode_s is not None else None,
                    source_path=str(source) if source is not None else None,
                    ranks=ranks,
                )
            )
        except Exception:
            logger.debug("triage-finished dispatch failed", exc_info=True)
            return False

    # -- folder loading ----------------------------------------------------

    def open_folder(self, folder: Path) -> None:
        import time

        t0 = time.perf_counter()
        folder = Path(folder)
        gen = self._next_folder_gen()
        # Fresh world: stable ids restart (pins are path-keyed and stay
        # inert for the new pool).
        self._series_next_id = 1
        _ = gen  # sync scan below replaces state immediately; gen guards workers
        _dnd_log("open_folder: ENTER %s is_file=%s is_dir=%s", folder, folder.is_file(), folder.is_dir())
        # If a single image file was passed (user dropped one image), don't scan its parent
        # — show just that image. Previously we scanned parent and fed entire folder (1037 items).
        if folder.is_file():
            _dnd_log("open_folder single file branch -> open_paths single %s", folder)
            # Delegate to open_paths so we don't set folder to parent
            try:
                self.open_paths([folder])
                _dnd_log("open_folder: EXIT via open_paths (%.1f ms)", (time.perf_counter() - t0) * 1000)
                return
            except Exception:
                _dnd_log("open_folder single file fallback", exc_info=True)
                try:
                    mtime = folder.stat().st_mtime_ns
                except Exception:
                    mtime = 0
                items = [GalleryItem(path=folder, mtime_ns=mtime)]
                display_folder = folder.parent
                self.state = GalleryState(folder=display_folder, items=items, triage_state=TriageState.RUNNING)
                _dbg("open_folder single file -> parent %s items=%d", display_folder, len(items))
                self.widget.set_folder_label(display_folder)
                self._hydrate_ai_cache(items)
                self.widget.rebuild_grid(items)
                self._emit_gallery(
                    GalleryPoolOpened(
                        folder=str(display_folder),
                        entries=[(str(it.path), it.mtime_ns) for it in items],
                    )
                )
                for item in items:
                    self._load_thumbnail(item)
                self._start_triage(items)
                return
        _dnd_log("open_folder: scan_folder START %s", folder)
        items = scan_folder(folder)
        _dnd_log("open_folder: scan_folder DONE %s -> %d items (%.1f ms)", folder, len(items), (time.perf_counter() - t0) * 1000)
        _dnd_log("open_folder scanned %s -> %d items", folder, len(items))
        self.state = GalleryState(folder=folder, items=items, triage_state=TriageState.RUNNING)
        _dnd_log("open_folder: set state + rebuild_grid START (%d items)", len(items))
        self.widget.set_folder_label(folder)
        self._hydrate_ai_cache(items)
        self.widget.rebuild_grid(items)
        _dnd_log("open_folder: rebuild_grid DONE (%.1f ms total)", (time.perf_counter() - t0) * 1000)
        self._emit_gallery(
            GalleryPoolOpened(
                folder=str(folder),
                entries=[(str(it.path), it.mtime_ns) for it in items],
            )
        )
        self._begin_folder_schedule(items, gen)
        self._start_triage(items)
        _dnd_log("open_folder: EXIT ok (%.1f ms)", (time.perf_counter() - t0) * 1000)

    def open_paths(self, paths: list[Path], *, replace: bool = False) -> None:
        """Open an explicit list of image paths (single/multiple drop).

        Fixes "скормить всю папку когда скинул одно изображение": previously
        a single image drop was converted to its parent folder and the whole
        folder was scanned (40 images). Now we build items only from the
        explicitly dropped paths.

        ``replace=False`` (default, file-drop style) APPENDS to the current
        pool — each FM file drop used to wipe the pool because ``uniq`` was
        built from the new drop only. ``replace=True`` restores the old
        wipe-and-replace (mixed folder+files drops where the dropped folder
        becomes the pool context).
        """
        import time

        t0 = time.perf_counter()
        _dnd_log("open_paths: ENTER %d paths %r replace=%s", len(paths), paths[:3], replace)
        if replace:
            # Folder switch cancels everything in flight from the previous folder.
            self._next_folder_gen()
            old_items: list[GalleryItem] = []
        else:
            # Append: no folder switch — in-flight thumbnail/triage workers for
            # the old pool stay valid, so the generation is left untouched.
            old_items = list(self.state.items)
        # Filter to images that exist
        from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS

        filtered: list[GalleryItem] = []
        for p in paths:
            pp = Path(p)
            if pp.is_file() and pp.suffix.lower() in ACCEPTED_IMAGE_EXTENSIONS:
                try:
                    mtime = pp.stat().st_mtime_ns
                except Exception:
                    mtime = 0
                filtered.append(GalleryItem(path=pp, mtime_ns=mtime))
            elif pp.is_dir():
                # If a directory was dropped among files, scan it
                filtered.extend(scan_folder(pp))
        # Deduplicate by path — seeded from the old pool when appending so
        # re-dropped files don't duplicate and already-loaded items are known.
        def _key(it: GalleryItem) -> str:
            try:
                return str(it.path.resolve()) if it.path.exists() else str(it.path)
            except Exception:
                return str(it.path)

        seen: set[str] = {_key(it) for it in old_items}
        uniq: list[GalleryItem] = []
        for it in filtered:
            s = _key(it)
            if s not in seen:
                seen.add(s)
                uniq.append(it)
        # Append: old pool first, truly-new drops at the end.
        merged: list[GalleryItem] = list(old_items) + uniq
        if not uniq and not replace:
            # Pure no-op (re-drop of known files): pool, label and folder are
            # already current — rebuilding would demolish headers for nothing.
            # Still ensure grouping: flat cards that never got triaged (e.g.
            # materialized by an external sync first) need their first pass;
            # a live series view needs nothing at all.
            try:
                gv = getattr(self.widget, "_grid_view", None)
                grouped = bool(getattr(gv, "_series", None))
            except Exception:
                grouped = False
            if grouped or not merged:
                return
            self._start_triage(merged, cover_grid=False)
            return
        # For explicit file drops, don't set folder to parent — keep it None
        # so we don't imply the whole parent folder was opened (fixes "установил путь на папку"
        # when user dropped a single image). Folder is only set when a directory
        # was explicitly dropped/scanned. For file lists, display_folder stays None
        # and the label shows the dropped files, not their parent.
        display_folder = None
        has_dir_input = any(Path(p).is_dir() for p in paths)
        if has_dir_input and uniq:
            # Directory was among dropped paths — use its path as folder
            for p in paths:
                if Path(p).is_dir():
                    display_folder = Path(p)
                    break
            if display_folder is None:
                try:
                    display_folder = uniq[0].path.parent
                except Exception:
                    display_folder = None
        # else: file-only drop — leave display_folder as None (no folder context),
        # unless appending into a folder-backed pool: then keep the folder so
        # folder actions (run-triage reopen, pick start_dir) keep working.
        if not has_dir_input and not replace and self.state.folder is not None:
            display_folder = self.state.folder
        # else: file-only drop — leave display_folder as None (no folder context)
        # S2: the fresh state wipes series/mode/source — snapshot the live
        # view first so the append-attach branch below can keep it.
        try:
            prev_series = list(self.state.series or [])
        except Exception:
            prev_series = []
        try:
            prev_mode = self.state.mode
        except Exception:
            prev_mode = None
        try:
            prev_source = self.state.source_path
        except Exception:
            prev_source = None
        try:
            prev_triage = self.state.triage_state
        except Exception:
            prev_triage = TriageState.IDLE
        self.state = GalleryState(folder=display_folder, items=merged, triage_state=TriageState.RUNNING)
        _dnd_log(
            "open_paths -> folder %s items=%d (has_dir=%s replace=%s old=%d new=%d) (%.1f ms)",
            display_folder, len(merged), has_dir_input, replace,
            len(old_items), len(uniq), (time.perf_counter() - t0) * 1000,
        )
        if display_folder is not None:
            self.widget.set_folder_label(display_folder)
        else:
            # For single/multi file drop, show what was actually dropped, not parent
            try:
                if len(uniq) == 1:
                    self.widget.set_folder_label(uniq[0].path)
                elif len(uniq) > 1:
                    self.widget.set_folder_label(Path(f"{len(uniq)} images dropped"))
                else:
                    self.widget.set_folder_label(Path(""))
            except Exception:
                pass
        self._hydrate_ai_cache(merged)
        self.widget.rebuild_grid(merged)
        # Mirror pool membership into the slot AFTER the local mirror + grid
        # are current, so the resulting 'gallery' emit reconciles to a no-op.
        if replace:
            self._emit_gallery(
                GalleryPoolReplaced(
                    folder=str(display_folder) if display_folder is not None else None,
                    entries=[(str(it.path), it.mtime_ns) for it in merged],
                )
            )
        elif uniq:
            self._emit_gallery(
                GalleryPathsAppended(
                    entries=[(str(it.path), it.mtime_ns) for it in uniq],
                )
            )
        # Thumbnails only for truly-new items — old ones are already loaded.
        for item in uniq:
            self._load_thumbnail(item)
        # S2 append: NEW files only join the nearest EXISTING series
        # (in-memory attach — existing membership untouched, no retriage)
        # when a grouped view is live and quiet; otherwise the existing
        # seed pipeline runs over the merged pool. A fresh pool (or
        # replace) covers until first groups; appends keep groups visible.
        if replace:
            # Fresh world: stable ids restart.
            self._series_next_id = 1
            self._start_triage(merged, cover_grid=True)
        elif not old_items:
            self._start_triage(merged, cover_grid=True)
        elif prev_series and prev_triage != TriageState.RUNNING:
            self.state.series = prev_series  # type: ignore[assignment]
            self.state.mode = prev_mode  # type: ignore[assignment]
            self.state.source_path = prev_source  # type: ignore[assignment]
            try:
                self._attach_append_items(uniq)
            except Exception:
                logger.debug("append attach failed", exc_info=True)
            # S2 tail regroup: attach never compares new files with each
            # other, so mutually-similar drops would sit UNGROUPED until a
            # manual re-cluster. Regroup the tail (old singletons + fresh
            # misses) into new series; existing membership untouched.
            try:
                self._cluster_tail_into_series()
            except Exception:
                logger.debug("append tail cluster failed", exc_info=True)
            # Stage-2 analyses (artifacts + fidelity + camera) for the NEW
            # items. The attach path deliberately skips re-clustering ("no
            # retriage"), but analysis is per-item and independent of
            # membership — without this the appended card kept "not measured"
            # rows while the first-drop cards were fully analyzed. Mirror
            # _apply_triage_result's fingerprint bookkeeping so a later
            # regroup does not re-run the whole pool.
            try:
                self._last_analysis_fingerprint = GalleryController._analysis_fingerprint(
                    list(self.state.items), prev_source
                )
            except Exception:
                pass
            self.state.triage_state = TriageState.DONE
            # Newer than any in-flight triage: its delivery drops (sgen).
            self._next_series_gen()
            try:
                self._apply_series_view(self.state.series)
            except Exception:
                logger.debug("append attach view failed", exc_info=True)
            # Post-first-load drops get the SAME processing feedback as a
            # first load: per-card activity pill + toolbar spinner/count.
            # Shown AFTER ``_apply_series_view`` — its ``set_triage`` /
            # ``set_triage_done`` retires the S1 spinner and would otherwise
            # clobber this indicator in the same event-loop turn, so it never
            # painted. The proxy ``on_done`` retires it when the batch settles.
            self._begin_append_processing(uniq)
            try:
                self._start_proxy_analysis(
                    list(uniq), prev_source, prev_mode,
                    on_done=lambda its=list(uniq): self._finish_append_processing(its),
                )
            except Exception:
                logger.debug("append analysis start failed", exc_info=True)
                self._finish_append_processing(uniq)
        else:
            self._start_triage(merged, cover_grid=False)

    def _on_pick_folder(self) -> None:
        start_dir = str(self.state.folder) if self.state.folder else ""
        chosen = self.widget.pick_folder_dialog(start_dir=start_dir)
        if not chosen:
            return
        p = Path(chosen)
        _dbg("pick_folder_dialog chosen: %s is_file=%s is_dir=%s", p, p.is_file(), p.is_dir())
        # If dialog returned a file (image picked), open just that file
        # (replace: explicit pick, not an additive drop).
        if p.is_file():
            self.open_paths([p], replace=True)
        elif p.is_dir():
            self.open_folder(p)
        else:
            # Fallback: try as folder
            if Path(chosen).exists():
                if Path(chosen).is_file():
                    self.open_paths([Path(chosen)], replace=True)
                else:
                    self.open_folder(Path(chosen))

    def _find_item(self, path: Path) -> GalleryItem | None:
        for item in self.state.items:
            if item.path == path:
                return item
        return None

    # -- thumbnails ----------------------------------------------------------

    def _load_thumbnail(self, item: GalleryItem, *, priority: int | None = None) -> None:
        """Schedule one thumbnail load (visible-first callers pass priority).

        Default is ``VISIBLE_THUMB_PRIORITY`` (fail-open): single loads are
        user-triggered or already-visible, so latency must not regress. The
        folder-open path partitions explicitly via ``_begin_folder_schedule``.
        """
        if priority is None:
            priority = VISIBLE_THUMB_PRIORITY
        try:
            self.schedule([item], int(priority), gen=self._folder_gen)
        except Exception:
            logger.debug("thumbnail schedule failed for %s", getattr(item, "path", "?"), exc_info=True)

    def _on_thumbnail_ready(self, path: Path, cache_path: Path | None, gen: int | None = None) -> None:
        try:
            self._thumb_inflight.discard(str(path))
        except Exception:
            pass
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched mid-flight — late thumbnail dropped
        item = self._find_item(path)
        if item is None:
            return
        if cache_path is None:
            item.thumbnail_status = ThumbnailStatus.ERROR
        else:
            pixmap = QPixmap(str(cache_path))
            if pixmap.isNull():
                item.thumbnail_status = ThumbnailStatus.ERROR
            else:
                item.thumbnail = pixmap
                item.thumbnail_status = ThumbnailStatus.LOADED
        # Card repaint is coalesced per tick (see _queue_card_refresh) — a
        # per-item refresh_card here re-swept selection over the whole grid.
        self._queue_card_refresh(item)
        # Per-item completion coalesces to ONE GalleryThumbnailsReady per turn.
        try:
            self._queue_thumb_ready(path, item.thumbnail_status.value)
        except Exception:
            pass

    def _on_thumbnail_error(self, path: Path, gen: int | None = None) -> None:
        try:
            self._thumb_inflight.discard(str(path))
        except Exception:
            pass
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        item = self._find_item(path)
        if item is None:
            return
        item.thumbnail_status = ThumbnailStatus.ERROR
        self._queue_card_refresh(item)
        try:
            self._queue_thumb_ready(path, ThumbnailStatus.ERROR.value)
        except Exception:
            pass

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
        open, append) had no such pass — and the AI domain is restored
        quietly (no network on open), while re-selecting the same domain is
        a no-op by contract. So previously analyzed images came back "not
        analyzed" even though the results sat in the disk cache. Cache-only:
        no worker, no settings check, no API call. Never raises; returns how
        many items were filled.
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

            dom = str(domain or "").strip().lower()
            if dom not in tuple(JUDGMENT_DOMAINS):
                dom = "algorithms"
        except Exception:
            dom = "algorithms"
        try:
            self.state.judgment_domain = dom
        except Exception:
            pass
        # The AI domain's ranker is Jev; mirror it so a fusion regroup never
        # silently re-derives a Jev rank while the AI domain is active.
        try:
            self.state.rank_domain = "ai" if dom == "ai" else "algorithms"
        except Exception:
            pass
        if dom != "ai":
            # Back to Algorithms: re-derive the deterministic fusion rank (a
            # Jev rank is only authoritative while the AI domain owns the rank).
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
        """Schedule ONE Jev rank per series on the AI domain (lazy + bounded).

        Mirrors the predecessor epic's lazy-AI rule: only series that have a
        currently-visible member are picked, and the number of series is capped,
        so flipping to AI never turns into a whole-folder API flood. The cache
        (``services.jev_cache``) pins each series, so a re-run over unchanged
        paths+mtimes+payload costs no second request.
        """
        try:
            groups = list(getattr(self.state, "series", None) or [])
        except Exception:
            groups = []
        if not groups:
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
        ran = 0
        for entry in groups:
            members = GalleryController._section_members(entry)
            if len(members) < 2:
                continue
            if vkeys and not any(str(getattr(m, "path", "")) in vkeys for m in members):
                continue
            if ran >= self._AI_VISIBLE_CAP:
                break
            ran += 1
            self._run_jev_rank_for_series(members)

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

    def _run_jev_rank_for_series(self, members) -> None:
        """Run one Jev rank worker for one series (cache-first, visible degrade).

        Pending is visible via the item activity phase; on a decisive answer the
        ranks are applied (``rank_source="jev"``), otherwise the Algorithms rank
        is kept and the reason surfaced. Never blocks the UI thread.
        """
        members = list(members or ())
        if len(members) < 2:
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

            self._degrade_jev(members, JEV_REASON_NOT_CONFIGURED)
            return

        mode = getattr(self.state, "mode", None)
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
            return rank_series_jev_detailed(snapshot, mode=mode, client=client)

        worker = GenericWorker(_job)

        def _on_result(outcome, gen=gen):
            if not self._is_current_folder_gen(gen):
                return  # folder switched mid-rank — late answer dropped
            self._apply_jev_outcome(snapshot, outcome)

        def _on_error(error_info, gen=gen):
            if not self._is_current_folder_gen(gen):
                return
            logger.debug("jev rank worker error: %r", error_info, exc_info=True)
            from tabs.image_gallery.services.jev_client import JEV_REASON_ERROR

            self._degrade_jev(snapshot, JEV_REASON_ERROR)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self._pool_start(worker, None)

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
                if path not in ranks:
                    continue
                try:
                    it.rank = int(ranks[path])
                    it.rank_source = "jev"  # type: ignore[attr-defined]
                except Exception:
                    pass
            try:
                self.state.rank_domain = "ai"
            except Exception:
                pass
            for it in current:
                try:
                    clear_activity(it)
                    self.widget.refresh_card(it)
                except Exception:
                    pass
            return
        reason = getattr(outcome, "reason", None) or "AI (Jev) rank unavailable"
        self._degrade_jev(current, reason)

    def _degrade_jev(self, members, reason: str) -> None:
        """Keep the Algorithms (fusion) rank and surface a visible reason.

        The stored rank is never touched here — a failed Jev rank must not
        fabricate a number or re-rank a subset (no silent fallback). The item
        carries an explicit AI error activity phase so the degrade is visible,
        and the reason is logged.
        """
        logger.debug("jev rank degraded: %s", reason)
        for m in list(members or ()):
            it = self._find_item(getattr(m, "path", None)) or m
            try:
                set_activity(it, ActivityPhase.ERROR, "ai")
                self.widget.refresh_card(it)
            except Exception:
                pass

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

        # Measured metrics ride along as authoritative context for the model.
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

    def _merge_measured_metrics(self, result, item):
        """Overwrite the model's sharpness/noise/exposure with MEASURED
        quality scores (the detectors are authoritative); keep the AI-only
        composition axis. Returns the (possibly) replaced result. Never
        raises — on any failure the original result is returned."""
        try:
            from dataclasses import replace

            from tabs.image_gallery.services import metric_scores as _ms
        except Exception:
            return result
        try:
            metrics = getattr(item, "metrics", None) or {}
            if not isinstance(metrics, dict) or not metrics:
                return result
            axes = {sid: score for sid, _label, _raw, score in _ms.measured_scores(metrics)}
        except Exception:
            return result
        kwargs = {}
        sharp = axes.get("sharpness")
        if sharp is not None:
            kwargs["sharpness"] = sharp
        noise = axes.get("noise")  # already positive "Clean" quality
        if noise is not None:
            kwargs["noise"] = noise
        exposure = axes.get("exposure")
        if exposure is not None:
            kwargs["exposure"] = exposure
        if not kwargs:
            return result
        try:
            return replace(result, **kwargs)
        except Exception:
            return result

    def _on_analysis_ready(self, path: Path, mtime_ns: int, result, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late analysis dropped
        item = self._find_item(path)
        if item is None:
            return
        result = self._merge_measured_metrics(result, item)
        save_analysis(path, mtime_ns, result)
        item.analysis = result
        item.analysis_status = AnalysisStatus.DONE
        item.analysis_error = None
        set_activity(item, ActivityPhase.DONE, "ai")
        self.widget.refresh_card(item)
        # Axis notes ride the metric/artifact row headers — rebuild the open
        # overlay's rows in place so the notes appear without a walk/reopen.
        try:
            ql = getattr(self.widget, "_quick_look_overlay", None)
            if ql is not None and hasattr(ql, "refresh_metrics"):
                ql.refresh_metrics(item)
            if ql is not None and hasattr(ql, "refresh_artifacts"):
                ql.refresh_artifacts(item)
        except Exception:
            pass

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
        """Bump the series-view generation: in-flight triage goes stale."""
        self._series_gen += 1
        return self._series_gen

    def _assign_fresh_stable_ids(self, computed) -> tuple:
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
            return (list(computed or []), self._series_next_id)
        try:
            pinned = {
                str(v)
                for v in (self._series_overrides or {}).values()
                if v is not None
            }
        except Exception:
            pinned = set()
        with self._series_id_lock:
            try:
                start = int(self._series_next_id or 1)
            except Exception:
                start = 1
            try:
                series, nxt = _translate(computed, start, skip_ids=pinned)
            except Exception:
                return (list(computed or []), self._series_next_id)
            try:
                self._series_next_id = int(nxt)
            except Exception:
                pass
            return (series, self._series_next_id)

    @staticmethod
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

    @staticmethod
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

    def _restore_singletons(self, items, overrides, pre_ids, last_series, regrouped) -> list:
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
        members_of = GalleryController._section_members
        id_of = GalleryController._section_id
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

    def _apply_series_view(self, series) -> None:
        """Post-triage view tail for sync paths (move / append-attach).

        Same delivery as ``_on_triage_ready`` minus workers: ``state.series``
        + rank/mode/source emit + ``widget.set_triage`` + spinner off. No
        clustering, no thread hops, no analysis starts.
        """
        self.state.series = series  # type: ignore[assignment]
        # Rank the regrouped view from the measured fusion (move / append
        # attach): same primitive as the triage tail, so a regroup never
        # resurrects the centroid order.
        self._apply_fusion_ranks(series)
        try:
            ts = getattr(self.state, "triage_state", "idle")
            triage_s = getattr(ts, "value", ts)
            triage_s = str(triage_s or "idle")
        except Exception:
            triage_s = "idle"
        try:
            self._emit_triage_finished(triage_s)
        except Exception:
            logger.debug("_apply_series_view emit failed", exc_info=True)
        try:
            self.widget.set_triage(series, self.state.mode, self.state.source_path)
        except Exception:
            logger.debug("_apply_series_view set_triage failed", exc_info=True)
        try:
            if hasattr(self.widget, "set_triage_done"):
                self.widget.set_triage_done()  # type: ignore[attr-defined]
            elif hasattr(self.widget, "toolbar") and hasattr(
                self.widget.toolbar, "set_triage_done"
            ):
                self.widget.toolbar.set_triage_done()  # type: ignore[attr-defined]
        except Exception:
            logger.debug("_apply_series_view set_triage_done failed", exc_info=True)

    def _run_triage_sync(
        self, items: list[GalleryItem], overrides: dict | None = None
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
            series, _ = self._assign_fresh_stable_ids(series)
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

    def retriage_quiet(self) -> bool:
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
            if getattr(self.state, "triage_state", None) not in (
                TriageState.IDLE, TriageState.DONE, TriageState.ERROR,
            ):
                return False
            items = list(getattr(self.state, "items", None) or [])
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
                    overrides = dict(getattr(self, "_series_overrides", None) or {})
                except Exception:
                    overrides = {}
                try:
                    import time as _time

                    _t0 = _time.perf_counter()
                    series, source, mode = self._run_triage_sync(
                        list(items), overrides
                    )
                    _t1 = _time.perf_counter()
                    series = self._commit_triage_series(series, source, mode)
                    _t2 = _time.perf_counter()
                    self._apply_triage_result(series, source, mode)
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
            self._start_triage(items, cover_grid=False)
            return True
        except Exception:
            return False

    def _start_triage(self, items: list[GalleryItem], *, cover_grid: bool = True) -> None:
        """Cluster in a worker, then ``set_triage`` on delivery.

        ``cover_grid=True`` (folder switch / replace) hides the grid behind
        the S1 scanning state until groups are ready. ``False`` (appending
        to a live pool) keeps the current groups visible and only spins the
        toolbar — tearing down a good view for one new image is the jump
        users see on every drop.
        """
        if not items:
            self.state.triage_state = TriageState.DONE
            self.state.series = []
            self.state.mode = None
            self.state.source_path = None
            self._emit_triage_finished("done")
            try:
                self.widget.set_triage([], None, None)
            except Exception:
                logger.debug("widget.set_triage failed for empty folder", exc_info=True)
            return
        self.state.triage_state = TriageState.RUNNING
        # A1: S1 scanning n/N in toolbar + empty state (progressive grid)
        if cover_grid:
            try:
                self.widget.set_scanning(0, len(items))
            except Exception:
                logger.debug("widget.set_scanning failed", exc_info=True)
        else:
            background = getattr(self.widget, "set_background_scanning", None)
            if callable(background):
                try:
                    background(0, len(items))
                except Exception:
                    logger.debug("widget.set_background_scanning failed", exc_info=True)
            else:
                # Legacy doubles predate the background API — same covering
                # behavior as before rather than no progress at all.
                try:
                    self.widget.set_scanning(0, len(items))
                except Exception:
                    logger.debug("widget.set_scanning failed", exc_info=True)
        self._mark_local_pass(items, ActivityPhase.ANALYZING)
        worker = GenericWorker(self._tracked(self._run_triage_sync), list(items), dict(self._series_overrides))
        gen = self._folder_gen
        sgen = self._series_gen
        worker.signals.result.connect(lambda res, g=gen, s=sgen: self._on_triage_ready(res, g, s))
        # NOTE: the local "done" badge is NOT stamped here. Triage only clusters
        # series; the card's quality dots come from the Stage-2 proxy pass
        # (artifacts/fidelity/camera) started in ``_apply_triage_result`` and
        # settling 1-2 s later. Stamping done on the triage result made the
        # badge read "done" while the dots were still stale — the exact
        # inversion the append path avoids. ``_apply_triage_result`` now stamps
        # done on the proxy settle (or immediately when there is nothing to
        # compute). See ``_mark_local_pass`` callers.
        worker.signals.error.connect(lambda err, g=gen: self._on_triage_error(err, g))
        worker.signals.error.connect(lambda _err, its=list(items): self._mark_local_pass(its, None))
        # Triage outranks background thumbnails so the grid labels settle first.
        self._pool_start(worker, TRIAGE_PRIORITY)

    def _mark_local_pass(self, items, phase) -> None:
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
            refresh = getattr(self.widget, "refresh_cards", None)
            if callable(refresh):
                refresh(items)
        except Exception:
            logger.debug("local-pass activity refresh failed", exc_info=True)

    def _begin_append_processing(self, items: list[GalleryItem]) -> None:
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
            background = getattr(self.widget, "set_background_scanning", None)
            if callable(background):
                background(0, len(batch))
        except Exception:
            logger.debug("append background scanning failed", exc_info=True)
        try:
            self._mark_local_pass(batch, ActivityPhase.ANALYZING)
        except Exception:
            logger.debug("append local pass failed", exc_info=True)

    def _finish_append_processing(self, items: list[GalleryItem]) -> None:
        """Retire the append processing indicator: ``done`` fade + spinner off."""
        batch = list(items or [])
        if not batch:
            return
        try:
            self._mark_local_pass(batch, ActivityPhase.DONE)
        except Exception:
            logger.debug("append local done failed", exc_info=True)
        try:
            done = getattr(self.widget, "set_triage_done", None)
            if callable(done):
                done()
        except Exception:
            logger.debug("append processing indicator hide failed", exc_info=True)
    def _run_artifacts_sync(self, items: list[GalleryItem], source_path: Path | None) -> dict[str, dict]:
        """Pure worker for GenericWorker: analyze 7 artifacts per item."""
        from tabs.image_gallery.services.artifacts import analyze_artifacts

        out: dict[str, dict] = {}
        for it in items:
            try:
                res = analyze_artifacts(it.path, source_path)
                # Store as str -> Severity value string for serialization, but keep Enum
                out[str(it.path)] = res
            except Exception:
                logger.debug("artifact analyze failed for %s", it.path, exc_info=True)
                out[str(it.path)] = {}
        return out

    def _start_artifact_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        if not items:
            return
        if _artifacts_disabled():
            _dbg("artifact analysis skipped (IMGSLI_GALLERY_NO_ARTIFACTS)")
            return
        # Run in background via GenericWorker (never UI-blocking).
        try:
            gen = self._folder_gen
            worker = GenericWorker(self._tracked(self._run_artifacts_sync), list(items), source_path)
            worker.signals.result.connect(lambda res, g=gen: self._on_artifacts_ready(res, g))
            worker.signals.error.connect(self._on_artifacts_error)
            self._pool_start(worker, 1)
        except Exception:
            logger.debug("artifact worker start failed", exc_info=True)

    def _on_artifacts_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late artifact catalog dropped
        # result: dict[str(path), dict[Artifact, Severity]]
        if not isinstance(result, dict):
            return
        self._apply_artifact_map(result)

    def _apply_artifact_map(self, result: dict, maps: dict | None = None) -> None:
        """Shared artifact delivery: batched repaint + quick-look refresh."""
        # Batch the card refresh: per-item refresh_card re-sweeps selection
        # over the whole grid (O(N^2) repaints in one delivery → stalled UI
        # thread → compositor busy cursor + dropped quick-look frames at the
        # clean→flagged flip). Items whose severities did not change skip the
        # repaint entirely.
        changed: list = []
        try:
            from tabs.image_gallery.use_cases import quality as _quality
        except Exception:
            _quality = None  # type: ignore[assignment]
        for item in self.state.items:
            key = str(item.path)
            arts = result.get(key)
            if arts is None:
                continue
            # Localization rides the artifact delivery; store it even when the
            # severities are unchanged (a first analysis after a metric-only
            # rebuild still needs the map).
            if maps is not None:
                try:
                    item.artifact_maps = maps.get(key) or {}
                except Exception:
                    pass
            if _quality is None:
                continue
            try:
                # Skip repaints when normalized severities did not change.
                if _quality.severities(item) and _quality.artifacts_equal(item, arts):
                    continue
            except Exception:
                pass
            try:
                if _quality.set_artifacts(item, arts):
                    changed.append(item)
            except Exception:
                logger.debug("artifact apply failed for %s", item.path, exc_info=True)
        if changed:
            try:
                self.widget.refresh_cards(changed)  # type: ignore[attr-defined]
            except Exception:
                for item in changed:
                    try:
                        self.widget.refresh_card(item)
                    except Exception:
                        logger.debug("widget.refresh_card failed for artifact %s", item.path, exc_info=True)
        # Quick look report: if widget has quick look overlay visible, refresh it.
        for item in changed:
                    # Widget owns _quick_look_overlay (QuickLookOverlay).
                    for attr in ("_quick_look_overlay", "_quick_look", "_quicklook", "_quicklook_overlay"):
                        ql = getattr(self.widget, attr, None)
                        if ql is not None and hasattr(ql, "refresh_artifacts"):
                            try:
                                ql.refresh_artifacts(item)
                            except Exception:
                                pass
                    # Also try generic widget helpers.
                    if hasattr(self.widget, "refresh_quick_look"):
                        try:
                            self.widget.refresh_quick_look(item)  # type: ignore[attr-defined]
                        except Exception:
                            pass
                    if hasattr(self.widget, "refresh_artifacts_for"):
                        try:
                            self.widget.refresh_artifacts_for(item)  # type: ignore[attr-defined]
                        except Exception:
                            pass

    def _on_artifacts_error(self, error_info: object) -> None:
        logger.debug("artifact worker error: %r", error_info, exc_info=True)

    # -- fidelity metrics (Stage 2 Pass 1b, wave B producer) --------------------

    def _start_fidelity_analysis(self, items: list[GalleryItem], source_path: Path | None) -> None:
        """Background SSIM/HF/ΔE/upscale metrics vs source (GenericWorker).

        Fail-closed: without a source there is nothing to compare against —
        keys stay absent and quick look renders "not measured" rows.
        """
        if not items or source_path is None:
            return
        if _fidelity_disabled():
            _dbg("fidelity analysis skipped (IMGSLI_GALLERY_NO_FIDELITY)")
            return
        try:
            from tabs.image_gallery.services.fidelity_metrics import run_fidelity_sync

            gen = self._folder_gen
            worker = GenericWorker(self._tracked(run_fidelity_sync), list(items), source_path)
            worker.signals.result.connect(lambda res, g=gen: self._on_fidelity_ready(res, g))
            worker.signals.error.connect(
                lambda err: logger.debug("fidelity worker error: %r", err, exc_info=True)
            )
            self._pool_start(worker, 1)
        except Exception:
            logger.debug("fidelity worker start failed", exc_info=True)

    def _on_fidelity_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late fidelity metrics dropped
        if not isinstance(result, dict):
            return
        self._apply_fidelity_map(result)

    def _apply_fidelity_map(self, result: dict) -> None:
        """Shared fidelity delivery: batched repaint + overlay refresh."""
        # Same batching as _on_artifacts_ready: skip items whose 4 keys did
        # not change, refresh the rest with one selection sweep. Optional
        # learned perceptual keys (LPIPS/DISTS) ride along when the backend is
        # installed; absent backend → they are simply not in the entry.
        required = ("ssim", "hf_ratio", "delta_e", "upscale_factor")
        optional = ("clipping_delta", "halo_delta", "chroma_fringe_delta", "lpips", "dists")
        try:
            from tabs.image_gallery.use_cases import quality as _quality
        except Exception:
            _quality = None  # type: ignore[assignment]
        changed: list = []
        for item in self.state.items:
            try:
                key = str(item.path)
            except Exception:
                continue
            entry = result.get(key)
            if not isinstance(entry, dict):
                continue
            # Identity fail-closed: entry key came from this item's own path;
            # write the 4 keys only when all measured, never a partial copy.
            if not all(k in entry for k in required):
                continue
            if _quality is None:
                continue
            keys = {k: entry[k] for k in required}
            for k in optional:
                if k in entry:
                    keys[k] = entry[k]
            try:
                if _quality.set_metrics(item, keys):
                    changed.append(item)
            except Exception:
                logger.debug("fidelity apply failed for %s", item.path, exc_info=True)
        # Shared delivery tail: repaint cards + live-refresh an open overlay.
        self._refresh_changed_metrics(changed, "fidelity")

    def _start_camera_metrics_analysis(self, items: list[GalleryItem]) -> None:
        """Background camera scalars (sharpness/exposure/clipping) — GenericWorker.

        Camera mode only (the report rows exist only there); unreadable items
        land nothing and keep "not measured" rows (fail-closed per item).
        """
        if not items:
            return
        if _camera_disabled():
            _dbg("camera metrics analysis skipped (IMGSLI_GALLERY_NO_CAMERA)")
            return
        try:
            from tabs.image_gallery.services.camera_metrics import run_camera_metrics_sync

            gen = self._folder_gen
            worker = GenericWorker(self._tracked(run_camera_metrics_sync), list(items))
            worker.signals.result.connect(lambda res, g=gen: self._on_camera_metrics_ready(res, g))
            worker.signals.error.connect(
                lambda err: logger.debug("camera metrics worker error: %r", err, exc_info=True)
            )
            self._pool_start(worker, 1)
        except Exception:
            logger.debug("camera metrics worker start failed", exc_info=True)

    def _refresh_changed_metrics(self, changed: list, tag: str) -> None:
        """Shared delivery tail: repaint cards + live-refresh an open overlay."""
        if changed:
            try:
                self.widget.refresh_cards(changed)  # type: ignore[attr-defined]
            except Exception:
                for item in changed:
                    try:
                        self.widget.refresh_card(item)
                    except Exception:
                        logger.debug("widget.refresh_card failed for %s %s", tag, item.path, exc_info=True)
        for item in changed:
            try:
                for attr in ("_quick_look_overlay", "_quick_look", "_quicklook", "_quicklook_overlay"):
                    ql = getattr(self.widget, attr, None)
                    if ql is not None and hasattr(ql, "refresh_metrics"):
                        try:
                            ql.refresh_metrics(item)
                        except Exception:
                            pass
            except Exception:
                pass

    def _on_camera_metrics_ready(self, result: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late camera metrics dropped
        if not isinstance(result, dict):
            return
        self._apply_camera_map(result)

    def _apply_camera_map(self, result: dict) -> None:
        """Shared camera delivery: merge scalars + repaint + overlay."""
        try:
            from tabs.image_gallery.use_cases import quality as _quality
        except Exception:
            return
        changed: list = []
        for item in self.state.items:
            try:
                key = str(item.path)
            except Exception:
                continue
            entry = result.get(key)
            if not isinstance(entry, dict):
                continue
            try:
                if _quality.set_metrics(item, entry):
                    changed.append(item)
            except Exception:
                logger.debug("camera metrics apply failed for %s", item.path, exc_info=True)
        self._refresh_changed_metrics(changed, "camera")

    # -- unified Stage-2 proxy step (Phase 2b+3; single-pass) ------------------

    @staticmethod
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

    def _schedule_proxy(self, items: list, priority: int, source, gen: int, wanted=None, include_camera: bool | None = None, full_res_artifacts: bool = False, on_done=None) -> int:
        """Chunked proxy batches: one worker per 50 items (never N)."""
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
                include_camera = bool(getattr(self.state, "mode", None) == Mode.CAMERA)
            except Exception:
                include_camera = False
        try:
            wanted_set = frozenset(wanted) if wanted else frozenset(("artifacts", "fidelity", "camera"))
        except Exception:
            wanted_set = frozenset(("artifacts", "fidelity", "camera"))
        self._proxy_done = 0
        self._proxy_total = len(chunks)
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
                self._tracked(GalleryController._run_proxy_chunk_sync),
                list(chunk), source, include_camera, full_res_artifacts,
            )
            worker.signals.result.connect(
                lambda res, g=gen, w=wanted_set: self._on_proxy_batch_ready(res, g, w)
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
            self._pool_start(worker, priority)
            started += 1
        # Chunk fan-out for tests (50-item batching assertion).
        try:
            self._sched_chunk_workers = int(getattr(self, "_sched_chunk_workers", 0)) + started
        except Exception:
            pass
        return started

    def _start_proxy_analysis(self, items: list[GalleryItem], source_path: Path | None, mode, *, on_done=None) -> None:
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
            self.schedule(
                list(items), PROXY_BATCH_PRIORITY, op="proxy",
                source=source_path, gen=self._folder_gen, wanted=wanted,
                include_camera=want_camera, full_res_artifacts=want_artifacts,
                on_done=on_done,
            )
        except Exception:
            logger.debug("proxy analysis start failed", exc_info=True)
            _finish()

    def _on_proxy_batch_ready(self, result: object, gen: int | None, wanted: object = None) -> None:
        """One chunk delivery: fan out by path into the legacy apply tails."""
        if gen is not None and not self._is_current_folder_gen(gen):
            return  # folder switched — late proxy chunk dropped
        if not isinstance(result, dict):
            return
        try:
            wanted_set = set(wanted or ("artifacts", "fidelity", "camera"))
        except Exception:
            wanted_set = {"artifacts", "fidelity", "camera"}
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
                self._apply_artifact_map(arts, maps)
            if "fidelity" in wanted_set:
                fid = {
                    k: (v.get("fidelity") if isinstance(v, dict) else None)
                    for k, v in result.items()
                }
                self._apply_fidelity_map(fid)
            if "camera" in wanted_set:
                cam = {
                    k: (v.get("camera") if isinstance(v, dict) else None)
                    for k, v in result.items()
                }
                self._apply_camera_map(cam)
        finally:
            try:
                self._proxy_done += 1
                total = int(self._proxy_total)
                done = int(self._proxy_done)
            except Exception:
                total, done = (0, 0)
            # Multi-chunk progress only: single-chunk (small-folder) runs
            # stay silent so small-folder latency/behavior cannot regress.
            if total > 1:
                background = getattr(self.widget, "set_background_scanning", None)
                if callable(background):
                    try:
                        background(done, total)
                    except Exception:
                        logger.debug("proxy progress hook failed", exc_info=True)
            try:
                self._trim_proxy_cache()
            except Exception:
                pass

    def _on_triage_ready(self, result: object, gen: int | None = None, sgen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            logger.debug("triage result dropped: stale folder generation")
            return
        if sgen is not None and sgen != self._series_gen:
            # A sync view rewrite (move / append-attach) landed while this
            # worker was in flight — its groups predate the manual
            # arrangement. Drop instead of clobbering it.
            logger.debug("triage result dropped: stale series generation")
            return
        try:
            series, source, mode = result  # type: ignore[misc]
        except Exception:
            logger.debug("triage result unpack failed: %r", result, exc_info=True)
            self.state.triage_state = TriageState.ERROR
            self._emit_triage_finished("error")
            return
        # Wave B: re-apply overrides on the GUI thread — the worker snapshot
        # may predate drops that landed while it was in flight. Idempotent.
        try:
            from tabs.image_gallery.use_cases import series_override as _override

            series = _override.apply_overrides(
                list(self.state.items), self._series_overrides, series
            )
        except Exception:
            logger.debug("series override re-apply failed", exc_info=True)
        series = self._commit_triage_series(series, source, mode)
        self._apply_triage_result(series, source, mode)

    def _commit_triage_series(self, series, source, mode):
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
            series = self._restore_singletons(
                list(self.state.items),
                self._series_overrides,
                None,
                series,
                series,
            )
        except Exception:
            logger.debug("pinned singleton restore failed", exc_info=True)
        self.state.series = series  # type: ignore[assignment]
        self.state.source_path = source  # type: ignore[assignment]
        self.state.mode = mode  # type: ignore[assignment]
        self.state.triage_state = TriageState.DONE
        # Algorithms rank: measured metric fusion over each series (never the
        # old centroid order). Single choke point for both the worker and the
        # inline fast path.
        self._apply_fusion_ranks(series, mode=mode)
        self._emit_triage_finished("done")
        return series

    @staticmethod
    def _analysis_fingerprint(items, source) -> tuple:
        """Content key for Stage-2 analyses (paths + mtimes + metrics state).

        Analyses derive everything from file content; identical fingerprints
        imply identical results, so the triage tail skips restarting them
        (e.g. regroup after tab return). Missing metrics force a re-run
        even when paths match (fresh objects after restore).
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

    def _apply_triage_result(self, series, source, mode) -> None:
        """Paint a triage outcome: view update + spinner off + analyses.

        Shared tail of the async worker delivery and the synchronous
        fast path — Stage-2 analyses start only when the content
        fingerprint changed since the last run.
        """
        try:
            self.widget.set_triage(series, mode, source)
        except Exception:
            logger.debug("widget.set_triage failed", exc_info=True)
        # A1: hide toolbar scanning spinner
        try:
            # Prefer widget helper, fallback to toolbar directly
            if hasattr(self.widget, "set_triage_done"):
                self.widget.set_triage_done()  # type: ignore[attr-defined]
            elif hasattr(self.widget, "toolbar") and hasattr(self.widget.toolbar, "set_triage_done"):
                self.widget.toolbar.set_triage_done()  # type: ignore[attr-defined]
        except Exception:
            logger.debug("toolbar.set_triage_done failed", exc_info=True)
        try:
            fingerprint = GalleryController._analysis_fingerprint(
                list(self.state.items), source
            )
        except Exception:
            fingerprint = None
        try:
            analyses_current = (
                fingerprint is not None
                and fingerprint == self._last_analysis_fingerprint
            )
        except Exception:
            analyses_current = False
        if analyses_current:
            logger.debug("triage tail: analyses unchanged, skipping restarts")
            # Nothing to compute — retire the local "analyzing" badge now, or it
            # would stick forever (no proxy settle will fire to stamp done).
            self._mark_local_pass(list(self.state.items), ActivityPhase.DONE)
        else:
            try:
                self._last_analysis_fingerprint = fingerprint
            except Exception:
                pass
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
                self._start_proxy_analysis(
                    list(self.state.items),
                    source,
                    mode,
                    on_done=lambda: self._mark_local_pass(
                        list(self.state.items), ActivityPhase.DONE
                    ),
                )
            except Exception:
                logger.debug("proxy analysis start failed", exc_info=True)
                # Fail-open: never leave the badge stuck in "analyzing".
                self._mark_local_pass(list(self.state.items), ActivityPhase.DONE)
        # Stage 3: targeted tie-break for top-2 when local metrics within epsilon (badge pending)
        try:
            for ser in series or []:
                self.run_tie_break_if_needed(ser)
        except Exception:
            logger.debug("tie-break auto-run failed", exc_info=True)

    def _on_triage_error(self, error_info: object, gen: int | None = None) -> None:
        if gen is not None and not self._is_current_folder_gen(gen):
            return
        logger.debug("triage worker error: %r", error_info, exc_info=True)
        self.state.triage_state = TriageState.ERROR
        self._emit_triage_finished("error")
        try:
            self.widget.set_triage([], None, None)
        except Exception:
            pass

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
                # normalize order
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
        self._pending_filter_text = text or ""
        timer = self._filter_timer
        if timer is None:
            try:
                timer = QTimer()
                timer.setSingleShot(True)
                timer.timeout.connect(self._apply_pending_filter)
                self._filter_timer = timer
            except Exception:
                timer = None
        if timer is None:
            # No Qt event loop (headless unit context) — apply synchronously.
            self._apply_filter(self._pending_filter_text, self._filter_gen + 1)
            return
        try:
            timer.stop()
            timer.start(self.FILTER_DEBOUNCE_MS)
        except Exception:
            self._apply_filter(self._pending_filter_text, self._filter_gen + 1)

    def apply_pending_filter(self) -> None:
        """Flush a debounced keystroke synchronously (tests / teardown)."""
        timer = self._filter_timer
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        self._apply_pending_filter()

    def _apply_pending_filter(self) -> None:
        self._filter_gen += 1
        self._apply_filter(self._pending_filter_text, self._filter_gen)

    def _apply_filter_fast(self, text: str) -> None:
        """UI-thread fast pass: filename + in-memory tags only, no disk."""
        from tabs.image_gallery.services.filtering import match_fast_items

        fast = {item.path for item in match_fast_items(self.state.items, text)}
        if not (text or "").strip():
            fast = {item.path for item in self.state.items}
        for item in self.state.items:
            try:
                self.widget.set_card_visible(item.path, item.path in fast)
            except Exception:
                pass

    def _apply_filter(self, text: str, filter_gen: int) -> None:
        from tabs.image_gallery.services.filtering import match_brief_items

        self._filter_gen = max(self._filter_gen, filter_gen)
        gen = self._filter_gen
        # Dispatch-only source (set_selection pattern): skip dispatch when
        # the slot already equals, else emit, then mirror locally.
        try:
            slot = self._gallery_slot()
            if slot is None or _gallery_selectors.get_filter_text(slot) != text:
                self._emit_gallery(GalleryFilterSet(filter_text=text))
        except Exception:
            self._emit_gallery(GalleryFilterSet(filter_text=text))
        self.state.filter_text = text
        self._apply_filter_fast(text)
        if not (text or "").strip():
            return
        # Slow pass off the UI thread: brief-cache disk match, mtime-honored.
        # Merged on arrival only if no newer keystroke/folder switch landed.
        snapshot = list(self.state.items)

        def _slow() -> set:
            try:
                return {item.path for item in match_brief_items(snapshot, text)}
            except Exception:
                return set()

        folder_gen = self._folder_gen
        worker = GenericWorker(_slow)
        worker.signals.result.connect(
            lambda extra, g=gen, fg=folder_gen: self._on_brief_filter_ready(extra, g, fg)
        )
        worker.signals.error.connect(lambda _err: None)
        self._pool_start(worker, 0)

    def _on_brief_filter_ready(self, extra_paths: set, filter_gen: int, folder_gen: int) -> None:
        if filter_gen != self._filter_gen or not self._is_current_folder_gen(folder_gen):
            return  # stale query or folder switch — never resurrect old matches
        if not extra_paths:
            return
        for item in self.state.items:
            if item.path in extra_paths:
                try:
                    self.widget.set_card_visible(item.path, True)
                except Exception:
                    pass