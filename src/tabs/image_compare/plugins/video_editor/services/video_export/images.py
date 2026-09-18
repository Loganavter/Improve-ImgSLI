from __future__ import annotations

import logging
import os
import threading

from engine.store.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

class VideoExportImageRepository:
    def __init__(self) -> None:
        self._images_cache: dict[tuple[str, bool], object] = {}
        # Single-flight for thumbnail-strip stampedes: N workers racing on
        # the same cold (path, auto_crop) key must decode once, not N times.
        self._images_lock = threading.Lock()

    def clear(self) -> None:
        """Single reset path for the image cache.

        Only ``VideoExporterService._clear_frame_caches`` calls this (export
        start/finish); nothing clears entries ad-hoc, so preview, export,
        and thumbnail renders share one image identity per (path, auto_crop).
        """
        self._images_cache.clear()

    def get_image(self, path: str, auto_crop: bool = False):
        if not path or not os.path.exists(path):
            return None

        cache_key = (path, auto_crop)
        cached = self._images_cache.get(cache_key)
        if cached is not None:
            return cached

        # Double-checked single-flight: re-check under the lock so N workers
        # racing on one cold key decode exactly once; losers reuse the winner.
        with self._images_lock:
            cached = self._images_cache.get(cache_key)
            if cached is not None:
                return cached

            try:
                img = TiledPixelStore.from_path(path, auto_crop=auto_crop)
            except Exception as exc:
                logger.error("Failed to load image for video: %s - %s", path, exc)
                return None

            if img is not None:
                self._images_cache[cache_key] = img
            return img
