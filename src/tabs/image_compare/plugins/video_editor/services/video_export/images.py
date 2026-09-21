from __future__ import annotations

import logging
import os
import threading

from engine.store.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

class VideoExportImageRepository:
    def __init__(self) -> None:
        self._images_cache: dict[tuple[str, bool], object] = {}
        # Per-key single-flight: one in-flight marker per cold
        # (path, auto_crop) key. Threads decoding DIFFERENT keys never
        # block each other (the old global double-checked lock serialized
        # every decode behind one mutex); threads racing on the SAME cold
        # key decode once — losers wait on the winner's event and reuse.
        # The guard mutex only protects the dicts, never the decode.
        self._images_lock = threading.Lock()
        self._inflight: dict[tuple[str, bool], threading.Event] = {}

    def clear(self) -> None:
        """Single reset path for the image cache.

        Only ``VideoExporterService._clear_frame_caches`` calls this (export
        start/finish); nothing clears entries ad-hoc, so preview, export,
        and thumbnail renders share one image identity per (path, auto_crop).
        In-flight decodes keep their markers — their owners publish under
        the guard mutex after this returns, which only re-adds entries.
        """
        with self._images_lock:
            self._images_cache.clear()

    def get_image(self, path: str, auto_crop: bool = False):
        if not path or not os.path.exists(path):
            return None

        cache_key = (path, auto_crop)
        cached = self._images_cache.get(cache_key)
        if cached is not None:
            return cached

        # Per-key single-flight: claim ownership of this cold key under
        # the guard mutex, decode WITHOUT holding it, then publish.
        # Same-key losers wait on the owner's event outside the mutex.
        with self._images_lock:
            cached = self._images_cache.get(cache_key)
            if cached is not None:
                return cached
            waiter = self._inflight.get(cache_key)
            if waiter is None:
                waiter = threading.Event()
                self._inflight[cache_key] = waiter
                owner = True
            else:
                owner = False

        if not owner:
            try:
                waiter.wait(timeout=60.0)
            except Exception:
                pass
            # Winner published, failed (miss), or timed out — whatever
            # the outcome, return what's cached now (None = clean miss,
            # caller falls back; never decode twice for one key here).
            return self._images_cache.get(cache_key)

        try:
            img = TiledPixelStore.from_path(path, auto_crop=auto_crop)
        except Exception as exc:
            logger.error("Failed to load image for video: %s - %s", path, exc)
            img = None

        with self._images_lock:
            if img is not None:
                self._images_cache[cache_key] = img
            self._inflight.pop(cache_key, None)
            waiter.set()
        return img
