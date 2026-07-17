from __future__ import annotations

import logging
import os

from shared.image_processing.tiled_pixel_store import TiledPixelStore

logger = logging.getLogger("ImproveImgSLI")

class VideoExportImageRepository:
    def __init__(self) -> None:
        self._images_cache: dict[tuple[str, bool], object] = {}

    def clear(self) -> None:
        self._images_cache.clear()

    def get_image(self, path: str, auto_crop: bool = False):
        if not path or not os.path.exists(path):
            return None

        cache_key = (path, auto_crop)
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
