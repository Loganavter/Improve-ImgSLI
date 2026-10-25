"""Background page-cache warm-up for tiles the render loop wants resident
soon but hasn't budgeted an upload for this call (see
``TileResidencyRealizerBase.realize_specs`` in ``residency.py``).

``TiledPixelStore`` is always memmap-backed straight to disk, never tmpfs
(``tiled_pixel_store.py``'s module docstring) -- a tile's *first* touch
after the OS has never cached (or has evicted) its pages is a synchronous
page fault -> disk read, which today happens inline inside
``crop_apron_tile`` on the render/GUI thread. Warming those same pages
ahead of time, off-thread, turns that stall into a cheap memory copy by the
time the tile's budgeted turn actually comes up -- the same idea as a
professional image editor's background tile loader (GIMP/Photoshop-style
tile cache prefetch).

Purely advisory: a cache miss (still in flight, budget starves the tile
forever, or the source closes mid-warm) leaves behavior identical to no
prefetch at all -- this can never make residency worse, only sometimes
faster.
"""

from __future__ import annotations

import logging
import threading
import time

from PySide6.QtCore import QThreadPool, Qt
from sli_ui_toolkit.workers import GenericWorker

from engine.cache.tile_geometry import crop_apron_tile
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: How long an in-flight warm entry may live before it is treated as lost
#: (worker died without emitting, pool starved, source closed mid-flight in
#: a worker flavor that never signals): swept opportunistically on every
#: ``warm()`` plus explicitly via ``sweep()``. Warms should finish in
#: milliseconds; 30 s is abandonment, not a deadline.
PREFETCH_INFLIGHT_TIMEOUT_S = 30.0


def _warm_tile(crop_source, left: int, top: int, right: int, bottom: int, apron_px: int) -> None:
    # Result is discarded -- this call's only purpose is to force the
    # underlying memmap pages into the OS page cache. A closed
    # ``TiledPixelStore`` raises (see ``_ensure_open``); that's expected if
    # the source got swapped out from under an in-flight warm request and
    # is caught by ``GenericWorker`` itself, same as any other worker error.
    crop_apron_tile(crop_source, left, top, right, bottom, apron_px)


class TilePrefetcher:
    """Dedupes and dispatches background tile-warm requests onto Qt's
    global thread pool.

    Uses ``QThreadPool.globalInstance()`` rather than the app's own
    lifecycle-managed pool (``bootstrap.py``'s ``self.thread_pool``) on
    purpose: this class lives deep in the QRhi renderer layer
    (``TileResidencyRealizerBase``, constructed with no app/session
    context -- see ``resources.py``), and Qt owns the global pool's
    lifetime for the whole process, so no extra plumbing or shutdown
    draining is needed here beyond the try/except in ``_warm_tile``.
    """

    def __init__(self, *, timeout_s: float = PREFETCH_INFLIGHT_TIMEOUT_S) -> None:
        # key -> monotonic submit time. Guarded by a lock: finished/error
        # slots fire on the GUI thread while warm() may be called from the
        # render thread, so check-and-add must be atomic. finished-after-
        # error is verified behaviorally (GenericWorker emits finished even
        # when the warm raises), but the error slot discards too — the
        # release must never depend on one signal flavor alone.
        self._in_flight: dict[tuple[object, tuple[int, int]], float] = {}
        self._lock = threading.Lock()
        self._timeout_s = max(0.0, float(timeout_s))

    def __len__(self) -> int:
        with self._lock:
            return len(self._in_flight)

    def sweep(self, *, timeout_s: float | None = None) -> int:
        """Drop entries older than ``timeout_s`` (default: constructor's).

        Returns how many were dropped. Lost entries would otherwise dedup
        every future warm for the same tile forever — a silent permanent
        prefetch stand-down for hot tiles.
        """
        limit = self._timeout_s if timeout_s is None else max(0.0, float(timeout_s))
        now = time.monotonic()
        with self._lock:
            stale = [key for key, born in self._in_flight.items() if now - born > limit]
            for key in stale:
                del self._in_flight[key]
        if stale:
            logger.debug("[TilePrefetch] swept %d stale in-flight warms", len(stale))
        return len(stale)

    def warm(self, key: object, index: tuple[int, int], crop_source, region, apron_px: int) -> bool:
        """Submits a background warm request; returns whether it actually
        submitted a new task (``False`` if deduped against one already in
        flight) -- callers budgeting how many warms to fire per call should
        only count submissions that returned ``True``."""
        if crop_source is None:
            return False
        cache_key = (key, index)
        with self._lock:
            self._sweep_locked()
            if cache_key in self._in_flight:
                return False
            self._in_flight[cache_key] = time.monotonic()
        worker = GenericWorker(
            _warm_tile, crop_source, region.left, region.top, region.right, region.bottom, apron_px
        )

        def _release(cache_key=cache_key) -> None:
            with self._lock:
                self._in_flight.pop(cache_key, None)

        def _on_error(err, cache_key=cache_key) -> None:
            logger.debug("[TilePrefetch] warm failed for %s: %s", cache_key, err)
            _release(cache_key)

        # Direct connections: the signals object carries the constructing
        # thread's affinity, so a warm submitted off the GUI thread would
        # otherwise queue finished/error to a thread with no event loop and
        # the entry would never release (verified behaviorally). Both slots
        # are lock-guarded + logging-only, hence safe to run in the pool
        # thread. The timeout sweep stays as the backstop for truly lost
        # signals.
        worker.signals.finished.connect(_release, Qt.ConnectionType.DirectConnection)
        worker.signals.error.connect(_on_error, Qt.ConnectionType.DirectConnection)
        try:
            QThreadPool.globalInstance().start(worker)
        except Exception:
            _release(cache_key)
            raise
        return True

    def _sweep_locked(self) -> None:
        now = time.monotonic()
        stale = [key for key, born in self._in_flight.items() if now - born > self._timeout_s]
        for key in stale:
            del self._in_flight[key]
