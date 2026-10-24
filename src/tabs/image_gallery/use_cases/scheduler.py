"""Bounded gallery scheduler for the Image Gallery controller (Wave 5).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
This module owns gallery concurrency — the dedicated ``QThreadPool`` (never
the process-wide ``QThreadPool.globalInstance()``), the frozen
``schedule(items, priority)`` entry, the pending/active/peak accounting, the
visible-first partition for a fresh folder, the pausable background thumb lane
with its Hide/Show watcher, and the shared proxy decode-cache trim. The owner
keeps the shared primitives (``_find_item`` / folder+series generation
discipline) and thin delegators keep the method names verbatim.

The priority bands and the dedicated-pool size bounds stay declared on
``controller.py`` (mirroring the existing ``VISIBLE_THUMB_PRIORITY`` import
style in ``use_cases/thumbnails.py``); this module reads them lazily so the
declaration keeps one home.

Audit-Meta: pattern=thin-owner-target size=exempt reason="one bounded scheduler — dedicated pool + priority lanes + the pausable background thumb queue + the AI provider gate/run-level 429 pause, all sharing the owner counters"
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QObject, QThreadPool
from sli_ui_toolkit.workers import GenericWorker

from tabs.image_gallery.debug import gallery_debug as _dbg
from tabs.image_gallery.debug import gallery_thumbs_disabled as _thumbs_disabled
from tabs.image_gallery.models import ThumbnailStatus
from tabs.image_gallery.services.ai_client import _ai_debug

if TYPE_CHECKING:
    from tabs.image_gallery.controller import GalleryController

logger = logging.getLogger("ImproveImgSLI")


#: Memo for the configured judge concurrency. The pool is created once per
#: controller and the provider width is a durable setting, so a per-send
#: QSettings read would be pure overhead; ``reset_judge_concurrency_cache`` is
#: the test/settings-change seam.
_JUDGE_CONCURRENCY_CACHE: list[int | None] = [None]

#: Fallback width when the settings store cannot be read at all. Equal to
#: ``ai_settings_store.JUDGE_CONCURRENCY_DEFAULT`` on purpose: an unreadable
#: config must degrade to the same provider-friendly width, not to cpu_count.
_JUDGE_CONCURRENCY_FALLBACK = 3


def judge_concurrency() -> int:
    """How many AI requests may be in flight (setting, clamp 1..8, default 3).

    Read from ``AiSettings.judge_concurrency`` — NOT from ``os.cpu_count()``:
    the scarce resource is the provider (often a shared pool), and one thread
    per CPU let up to eight concurrent VLM POSTs hit it at once. Never raises.
    """
    cached = _JUDGE_CONCURRENCY_CACHE[0]
    if cached is not None:
        return cached
    value = _JUDGE_CONCURRENCY_FALLBACK
    try:
        from tabs.image_gallery.services.ai_settings_store import (
            AiSettingsStore,
            JUDGE_CONCURRENCY_MAX,
            JUDGE_CONCURRENCY_MIN,
        )

        value = int(AiSettingsStore().load().judge_concurrency)
        value = max(JUDGE_CONCURRENCY_MIN, min(JUDGE_CONCURRENCY_MAX, value))
    except Exception:
        value = _JUDGE_CONCURRENCY_FALLBACK
    _JUDGE_CONCURRENCY_CACHE[0] = value
    return value


def reset_judge_concurrency_cache() -> None:
    """Re-read the concurrency setting on next use (tests / settings apply)."""
    _JUDGE_CONCURRENCY_CACHE[0] = None


def _scheduler_thread_count() -> int:
    """Dedicated pool size: the provider's judge concurrency, clamped [4, 8].

    Was ``os.cpu_count()`` clamped [4, 8]. The upper end is now the declared
    ``judge_concurrency`` setting (never the CPU count). The LOWER end stays the
    decode floor (``_GALLERY_SCHED_MIN_THREADS``): this pool also serves
    thumbnail / proxy decodes, so a 1-wide provider setting must not serialize
    scrolling behind one VLM draw. The provider width itself — the number that
    actually reaches the API — is :func:`judge_concurrency`, enforced per send
    (:func:`ai_provider_slot`), so a 1..3 setting still means 1..3 concurrent
    requests even though the pool has more threads.
    """
    from tabs.image_gallery.controller import (
        _GALLERY_SCHED_MAX_THREADS,
        _GALLERY_SCHED_MIN_THREADS,
    )

    n = judge_concurrency()
    return max(_GALLERY_SCHED_MIN_THREADS, min(_GALLERY_SCHED_MAX_THREADS, n))


def _new_gallery_pool() -> QThreadPool:
    """Dedicated gallery pool (never QThreadPool.globalInstance())."""
    pool = QThreadPool()
    try:
        pool.setMaxThreadCount(_scheduler_thread_count())
    except Exception:
        pass
    return pool


# -- provider admission (judge lane width) ------------------------------------


_AI_SLOT_LOCK = threading.Lock()
_AI_SLOTS: threading.BoundedSemaphore | None = None
_AI_SLOTS_WIDTH = 0


def _provider_slots() -> threading.BoundedSemaphore:
    """The provider-width semaphore, sized on first use (env-free setting seam)."""
    global _AI_SLOTS, _AI_SLOTS_WIDTH
    with _AI_SLOT_LOCK:
        width = judge_concurrency()
        if _AI_SLOTS is None or _AI_SLOTS_WIDTH != width:
            _AI_SLOTS = threading.BoundedSemaphore(width)
            _AI_SLOTS_WIDTH = width
        return _AI_SLOTS


def reset_provider_slots() -> None:
    """Drop the sized semaphore so the next send re-reads the setting."""
    global _AI_SLOTS, _AI_SLOTS_WIDTH
    with _AI_SLOT_LOCK:
        _AI_SLOTS = None
        _AI_SLOTS_WIDTH = 0


class ai_provider_slot:
    """Context manager: one in-flight AI request (width ``judge_concurrency()``).

    Blocks the calling WORKER thread only (never the GUI thread): with the pool
    at 4-8 threads, a provider setting of 1..3 is what actually reaches the
    API, so a shared provider is not hammered by every pool thread.
    """

    def __enter__(self) -> "ai_provider_slot":
        self._sem = _provider_slots()
        self._sem.acquire()
        return self

    def __exit__(self, *exc_info) -> bool:
        try:
            self._sem.release()
        except Exception:
            pass
        return False


# -- run-level 429 pause (the WHOLE AI queue, not one request) ----------------

#: Pause bounds. The transport already honors ``Retry-After`` per request
#: (``_RETRY_MAX_DELAY_S`` = 30 s); this is the RUN-level gate: one 429 pauses
#: every queued send, so a single request's retries cannot keep the other
#: threads firing at a provider that just told us to slow down.
_AI_QUEUE_MIN_PAUSE_S = 0.5
_AI_QUEUE_MAX_PAUSE_S = 30.0
_AI_QUEUE_WAIT_MARGIN_S = 0.25


@dataclass
class AiQueuePause:
    """One run-level pause: a gate every AI send waits on, plus its window."""

    event: threading.Event
    until: float
    reason: str
    retry_after_s: float


def ai_queue_paused(owner) -> bool:
    """True while the run-level AI queue is paused."""
    return getattr(owner, "_ai_queue_pause", None) is not None


def pause_ai_queue(owner, retry_after_s: float, reason: str) -> None:
    """Pause the WHOLE AI queue for *retry_after_s* seconds.

    Every AI worker blocks in :func:`await_ai_queue` immediately before its
    request, so one 429 stops the run instead of letting the other threads keep
    hammering the provider. The pause auto-resumes through a Qt timer when an
    event loop exists (the deadline also releases a worker in headless runs —
    see :func:`await_ai_queue`). Re-pausing while paused extends the window.
    Cost, stated: waiting AI workers occupy pool threads, and the pool is shared
    with thumbnail decodes, so a pause also delays queued thumbs by up to the
    pause window — bounded by ``_AI_QUEUE_MAX_PAUSE_S``.
    """
    try:
        delay = float(retry_after_s or 0.0)
    except (TypeError, ValueError):
        delay = 0.0
    delay = max(_AI_QUEUE_MIN_PAUSE_S, min(_AI_QUEUE_MAX_PAUSE_S, delay))
    now = time.monotonic()
    with _AI_SLOT_LOCK:
        state = getattr(owner, "_ai_queue_pause", None)
        if state is not None:
            state.until = max(state.until, now + delay)
            state.retry_after_s = max(state.retry_after_s, delay)
            if reason:
                state.reason = str(reason)
            extended = state
        else:
            extended = AiQueuePause(
                event=threading.Event(),
                until=now + delay,
                reason=str(reason or "rate limit"),
                retry_after_s=delay,
            )
            try:
                owner._ai_queue_pause = extended
            except Exception:
                return
    _ai_debug("queue paused for %.1fs: %s", delay, extended.reason)
    _arm_ai_queue_resume(owner, delay)


def _arm_ai_queue_resume(owner, delay: float) -> None:
    """Resume the paused queue after *delay* on the GUI thread (when there is one)."""
    try:
        from PySide6.QtCore import QCoreApplication, QTimer

        if QCoreApplication.instance() is None:
            return  # headless: the workers' own deadline releases the gate
        QTimer.singleShot(int(delay * 1000) + 1, lambda: resume_ai_queue(owner))
    except Exception:
        logger.debug("AI queue resume timer failed", exc_info=True)


def await_ai_queue(owner) -> bool:
    """Block the calling (worker) thread while the run-level queue is paused.

    Returns True when it actually waited. Bounded by the pause deadline: a
    headless caller with no event loop can never hang on a pause whose timer
    will not fire.
    """
    state = getattr(owner, "_ai_queue_pause", None)
    if state is None:
        return False
    remaining = max(0.0, float(state.until) - time.monotonic())
    if remaining <= 0.0:
        return False
    try:
        state.event.wait(remaining + _AI_QUEUE_WAIT_MARGIN_S)
    except Exception:
        return False
    return True


def resume_ai_queue(owner) -> None:
    """Release the pause gate and re-dispatch the cards that were 429'd.

    No card is lost: ``_on_analysis_error`` parks a rate-limited card on
    ``owner._ai_queue_retry`` instead of marking it ERROR, and this re-enters
    the ordinary ``_begin_analysis`` path for those paths (same run budget, so
    a retry loop cannot bypass the ceiling).
    """
    with _AI_SLOT_LOCK:
        state = getattr(owner, "_ai_queue_pause", None)
        if state is None:
            return
        try:
            owner._ai_queue_pause = None
        except Exception:
            pass
    try:
        state.event.set()
    except Exception:
        pass
    _ai_debug("queue resumed (paused for %s)", state.reason)
    _retry_parked_ai_cards(owner)


def _retry_parked_ai_cards(owner) -> None:
    """Re-queue the cards parked by a 429 (runs in the AI run's own budget)."""
    try:
        parked = list(getattr(owner, "_ai_queue_retry", None) or ())
    except Exception:
        return
    if not parked:
        return
    try:
        owner._ai_queue_retry = []
    except Exception:
        pass
    try:
        from tabs.image_gallery.use_cases import judge_budget

        judge_budget.retry_parked_ai_cards(owner, parked)
    except Exception:
        logger.debug("AI queue resume: retry dispatch failed", exc_info=True)


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


def schedule(owner, items, priority: int, *, op: str = "thumb", source=None, gen: int | None = None, wanted=None, include_camera: bool | None = None, full_res_artifacts: bool = False, on_done=None) -> int:
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
            gen = owner._folder_gen
        except Exception:
            gen = 0
    if op == "proxy":
        return owner._schedule_proxy(batch, int(priority), source, gen, wanted=wanted, include_camera=include_camera, full_res_artifacts=full_res_artifacts, on_done=on_done)
    return owner._schedule_thumbs(batch, int(priority), gen)


def sched_stats(owner) -> dict:
    """Scheduler introspection (tests / debugging)."""
    try:
        with owner._sched_lock:
            pending = int(owner._sched_pending)
            active = int(owner._sched_active)
            peak = int(owner._sched_peak)
    except Exception:
        pending, active, peak = (0, 0, 0)
    try:
        queued = len(owner._bg_queue)
    except Exception:
        queued = 0
    return {"pending": pending, "active": active, "peak": peak, "queued": queued}


def _tracked(owner, fn):
    """Wrap a worker body with active/peak accounting (pool depth)."""
    def _run(*args, **kwargs):
        try:
            with owner._sched_lock:
                owner._sched_active += 1
                if owner._sched_active > owner._sched_peak:
                    owner._sched_peak = owner._sched_active
        except Exception:
            pass
        try:
            return fn(*args, **kwargs)
        finally:
            try:
                with owner._sched_lock:
                    owner._sched_active -= 1
            except Exception:
                pass
    return _run


def _pool_start(owner, worker, priority: int | None) -> None:
    """Start one worker with pending accounting (all pool traffic)."""
    try:
        with owner._sched_lock:
            owner._sched_pending += 1
    except Exception:
        pass
    try:
        finished = getattr(getattr(worker, "signals", None), "finished", None)
        if finished is not None and hasattr(finished, "connect"):
            try:
                finished.connect(owner._on_sched_finished)
            except Exception:
                pass
    except Exception:
        pass
    try:
        if priority is None:
            owner._thread_pool.start(worker)
        else:
            owner._thread_pool.start(worker, priority)
    except TypeError:
        owner._thread_pool.start(worker)


def _on_sched_finished(owner) -> None:
    try:
        with owner._sched_lock:
            owner._sched_pending = max(0, owner._sched_pending - 1)
    except Exception:
        pass


def _schedule_thumbs(owner, items: list, priority: int, gen: int) -> int:
    """One thumbnail worker per item (visible-first caller partitions)."""
    from tabs.image_gallery.controller import (
        BACKGROUND_THUMB_PRIORITY,
        render_and_cache_thumbnail,
    )

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
            if key in owner._thumb_inflight:
                continue
            if getattr(item, "thumbnail_status", None) == ThumbnailStatus.LOADED:
                continue
        except Exception:
            pass
        # Paused background lane queues instead of starting.
        try:
            paused = bool(owner._bg_paused)
        except Exception:
            paused = False
        if paused and priority <= BACKGROUND_THUMB_PRIORITY:
            try:
                owner._bg_queue.append((item, gen))
            except Exception:
                pass
            continue
        try:
            item.thumbnail_status = ThumbnailStatus.LOADING
        except Exception:
            pass
        try:
            owner._thumb_inflight.add(key)
        except Exception:
            pass
        worker = GenericWorker(
            owner._tracked(render_and_cache_thumbnail), item.path, item.mtime_ns
        )
        worker.signals.result.connect(
            lambda cache_path, path=item.path, g=gen: owner._on_thumbnail_ready(path, cache_path, g)
        )
        worker.signals.error.connect(
            lambda err, path=item.path, g=gen: owner._on_thumbnail_error(path, g)
        )
        owner._pool_start(worker, priority)
        started += 1
    return started


def _begin_folder_schedule(owner, items: list, gen: int) -> None:
    """Visible-first partition for a fresh folder (open_folder only).

    Cards intersecting the viewport (+ overscan) decode first at
    ``VISIBLE_THUMB_PRIORITY``; the rest drain from the background
    lane. ``visible_paths()`` fails open to everything when the grid
    is not laid out yet — identical to the old flood, never a
    starvation. Widgets without the Phase-2a API (older doubles)
    take the same fail-open path.
    """
    from tabs.image_gallery.controller import (
        BACKGROUND_THUMB_PRIORITY,
        VISIBLE_THUMB_PRIORITY,
    )

    try:
        visible = getattr(owner.widget, "visible_paths", None)
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
    owner.schedule(first, VISIBLE_THUMB_PRIORITY, gen=gen)
    owner.schedule(rest, BACKGROUND_THUMB_PRIORITY, gen=gen)


def _subscribe_visible_range(owner) -> None:
    """Reprioritize on scroll (grid debounces 120 ms upstream)."""
    try:
        sig = getattr(owner.widget, "visible_range_changed", None)
        connect = getattr(sig, "connect", None)
        if callable(connect):
            connect(owner._on_visible_range_changed)
    except Exception:
        logger.debug("visible_range_changed subscription failed", exc_info=True)


def _on_visible_range_changed(owner, paths: object) -> None:
    """Scroll delivery: newly visible items jump the thumb queue."""
    from tabs.image_gallery.controller import VISIBLE_THUMB_PRIORITY

    try:
        keys = {str(p) for p in (paths or [])}
    except Exception:
        return
    if not keys:
        return
    try:
        gen = owner._folder_gen
    except Exception:
        gen = 0
    for item in list(getattr(owner.state, "items", None) or []):
        try:
            if str(item.path) not in keys:
                continue
            if getattr(item, "thumbnail_status", None) == ThumbnailStatus.LOADED:
                continue
            if str(item.path) in owner._thumb_inflight:
                continue
        except Exception:
            continue
        try:
            owner.schedule([item], VISIBLE_THUMB_PRIORITY, gen=gen)
        except Exception:
            pass


def _install_visibility_pause(owner) -> None:
    """Pause the background lane while the tab page is hidden."""
    try:
        widget = owner.widget
        install = getattr(widget, "installEventFilter", None)
        if not callable(install):
            return
        try:
            parent = widget if isinstance(widget, QObject) else None
        except Exception:
            parent = None
        filt = _GalleryVisibilityPauseFilter(owner, parent)
        install(filt)
        owner._visibility_pause_filter = filt
    except Exception:
        logger.debug("visibility pause filter install failed", exc_info=True)


def pause_background(owner) -> None:
    """Pause the background thumb lane (tab hidden)."""
    try:
        owner._bg_paused = True
    except Exception:
        pass


def resume_background(owner) -> None:
    """Resume the background lane; stale entries drop, fresh drain."""
    from tabs.image_gallery.controller import BACKGROUND_THUMB_PRIORITY

    try:
        owner._bg_paused = False
    except Exception:
        return
    try:
        queued = list(owner._bg_queue)
        owner._bg_queue.clear()
    except Exception:
        return
    try:
        current = owner._folder_gen
    except Exception:
        current = 0
    fresh = [it for (it, g) in queued if g == current]
    if fresh:
        try:
            owner.schedule(fresh, BACKGROUND_THUMB_PRIORITY, gen=current)
        except Exception:
            logger.debug("background resume schedule failed", exc_info=True)


def _trim_proxy_cache(owner) -> int:
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
