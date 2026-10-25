"""Disk-cached thumbnail generation for gallery items.

Cache key/dir scheme mirrors ``services.io.project_preview`` (sha256 of
``path:mtime_ns``, so an edited file naturally misses the old cache entry).
Rendering runs off the UI thread — call ``render_and_cache_thumbnail`` from a
``GenericWorker``, never directly on the main thread.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PIL import Image
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

THUMBNAIL_SIZE = (192, 192)


def thumbnail_cache_dir() -> Path:
    from services.io.project_package import _cache_root

    root = _cache_root() / "gallery_thumbnails"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_key_for(path: Path, mtime_ns: int) -> str:
    digest = hashlib.sha256(f"{Path(path).resolve()}:{mtime_ns}".encode("utf-8")).hexdigest()
    return digest[:24]


def cached_thumbnail_path(path: Path, mtime_ns: int) -> Path:
    return thumbnail_cache_dir() / f"{cache_key_for(path, mtime_ns)}.png"


def _is_valid_cached_file(cache_path: Path) -> bool:
    """A cache entry is only a hit if it is a loadable image — a truncated or
    garbage file must not poison the hit path (the consumer would otherwise
    show a permanently broken thumbnail until the source is edited)."""
    try:
        with Image.open(cache_path) as image:
            image.verify()
        return True
    except Exception:
        return False


def _try_pyramid_render(path: Path, cache_path: Path, size: tuple[int, int]) -> bool:
    """Coarse-direct thumbnail render via the frozen wave-A1 pyramid seam.

    Bounded decode (``coarse_from_source`` never materializes a full frame)
    sampled verbatim through ``PyramidPixelStore.best_pixels``, fit-scaled to
    ``size`` and saved as PNG. True on success; False on any miss (the caller
    keeps the PIL ladder below). Disk keying untouched — only the pixel
    pipeline is replaced. Runs on a worker thread (QImage only, no pixmaps).
    """
    coarse = None
    try:
        from engine.store.pyramid_pixel_store import PyramidPixelStore
    except Exception:
        return False
    try:
        try:
            tw, th = max(1, int(size[0])), max(1, int(size[1]))
        except Exception:
            return False
        try:
            coarse = PyramidPixelStore.coarse_from_source(
                str(path), long_edge=max(256, 2 * max(tw, th))
            )
        except Exception:
            return False
        if coarse is None:
            return False
        try:
            base_w, base_h = coarse.size
        except Exception:
            return False
        if base_w <= 0 or base_h <= 0:
            return False
        try:
            pyramid = PyramidPixelStore(coarse)
        except Exception:
            return False
        try:
            # Single-level pyramid (coarse base is already complete), so the
            # scale only satisfies the seam signature — L0 is always served.
            img = pyramid.best_pixels((0, 0, base_w, base_h), 1.0)
        except Exception:
            img = None
        finally:
            try:
                pyramid.close()
            except Exception:
                pass
        if img is None:
            return False
        try:
            if img.isNull():
                return False
            if img.width() > tw or img.height() > th:
                from PySide6.QtCore import Qt

                img = img.scaled(
                    tw,
                    th,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            return bool(img.save(str(cache_path), "PNG"))
        except Exception:
            return False
    except Exception:
        return False
    finally:
        if coarse is not None:
            try:
                coarse.close()
            except Exception:
                pass


def render_and_cache_thumbnail(
    path: Path, mtime_ns: int, *, size: tuple[int, int] = THUMBNAIL_SIZE
) -> Path | None:
    """Render + disk-cache a thumbnail. Runs on a worker thread. Returns the
    cache file path on success, ``None`` on failure (missing/corrupt image)."""
    cache_path = cached_thumbnail_path(path, mtime_ns)
    if cache_path.is_file() and _is_valid_cached_file(cache_path):
        return cache_path
    if cache_path.exists():
        # Corrupt/partial cache entry: drop it and re-render below.
        try:
            cache_path.unlink()
        except OSError:
            logger.debug(
                "Could not remove corrupt gallery thumbnail cache entry %s",
                cache_path,
                exc_info=True,
            )
    if _try_pyramid_render(path, cache_path, size):
        return cache_path
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail(size)
            image.save(cache_path, "PNG")
        return cache_path
    except Exception:
        logger.debug("Gallery thumbnail render failed for %s", path, exc_info=True)
        return None