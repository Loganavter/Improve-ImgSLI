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

logger = logging.getLogger("ImproveImgSLI")

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
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail(size)
            image.save(cache_path, "PNG")
        return cache_path
    except Exception:
        logger.debug("Gallery thumbnail render failed for %s", path, exc_info=True)
        return None