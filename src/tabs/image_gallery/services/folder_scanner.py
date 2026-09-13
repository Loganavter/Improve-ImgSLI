"""Flat (non-recursive) folder scan for gallery items. Pure — no Qt."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from shared.image_extensions import ACCEPTED_IMAGE_EXTENSIONS
from tabs.image_gallery.debug import gallery_dnd_debug as _scan_log

from tabs.image_gallery.models import GalleryItem

logger = logging.getLogger("ImproveImgSLI")

IMAGE_EXTENSIONS = ACCEPTED_IMAGE_EXTENSIONS


def scan_folder(folder: Path) -> list[GalleryItem]:
    """Return gallery items for images directly inside ``folder`` (no recursion)."""
    t0 = time.perf_counter()
    folder = Path(folder)
    _scan_log("scan_folder: ENTER %s is_dir=%s", folder, folder.is_dir())
    if not folder.is_dir():
        _scan_log("scan_folder: %s not a dir -> 0 items (%.1f ms)", folder, (time.perf_counter() - t0) * 1000)
        return []

    entries: list[tuple[str, Path, int]] = []
    try:
        with os.scandir(folder) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                path = Path(entry.path)
                if path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                try:
                    mtime_ns = entry.stat().st_mtime_ns
                except OSError:
                    continue
                entries.append((path.name, path, mtime_ns))
    except Exception as e:
        _scan_log("scan_folder: scandir failed for %s: %r (%.1f ms)", folder, e, (time.perf_counter() - t0) * 1000)
        return []

    entries.sort(key=lambda e: e[0].lower())
    result = [GalleryItem(path=path, mtime_ns=mtime_ns) for _name, path, mtime_ns in entries]
    _scan_log("scan_folder: EXIT %s -> %d items (%.1f ms)", folder, len(result), (time.perf_counter() - t0) * 1000)
    return result
