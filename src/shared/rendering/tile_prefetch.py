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

from PySide6.QtCore import QThreadPool
from sli_ui_toolkit.workers import GenericWorker

from shared.rendering.tile_geometry import crop_apron_tile

logger = logging.getLogger("ImproveImgSLI")


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

    def __init__(self) -> None:
        self._in_flight: set[tuple[object, tuple[int, int]]] = set()

    def warm(self, key: object, index: tuple[int, int], crop_source, region, apron_px: int) -> bool:
        """Submits a background warm request; returns whether it actually
        submitted a new task (``False`` if deduped against one already in
        flight) -- callers budgeting how many warms to fire per call should
        only count submissions that returned ``True``."""
        cache_key = (key, index)
        if crop_source is None or cache_key in self._in_flight:
            return False
        self._in_flight.add(cache_key)
        worker = GenericWorker(
            _warm_tile, crop_source, region.left, region.top, region.right, region.bottom, apron_px
        )

        def _on_finished(cache_key=cache_key) -> None:
            self._in_flight.discard(cache_key)

        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(
            lambda err, cache_key=cache_key: logger.debug(
                "[TilePrefetch] warm failed for %s: %s", cache_key, err
            )
        )
        QThreadPool.globalInstance().start(worker)
        return True
