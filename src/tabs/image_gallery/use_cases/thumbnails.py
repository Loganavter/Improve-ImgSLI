"""Thumbnail load + completion handling for the Image Gallery.

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
``_load_thumbnail`` schedules through the owner's frozen ``schedule`` seam
(visible priority, fail-open, for single loads). The ready/error handlers clear
the owner's in-flight set, honor the folder-generation guard, then coalesce the
card repaint + ``GalleryThumbnailsReady`` dispatch through
``use_cases/completion_coalescing``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QPixmap

from tabs.image_gallery.models import GalleryItem, ThumbnailStatus

logger = logging.getLogger("ImproveImgSLI")


def _load_thumbnail(owner, item: GalleryItem, *, priority: int | None = None) -> None:
    """Schedule one thumbnail load (visible-first callers pass priority).

    Default is ``VISIBLE_THUMB_PRIORITY`` (fail-open): single loads are
    user-triggered or already-visible, so latency must not regress. The
    folder-open path partitions explicitly via ``_begin_folder_schedule``.
    """
    # The priority constants move with the scheduler wave; until then the
    # default resolves lazily from the owner module (late-bound, no cycle).
    from tabs.image_gallery.controller import VISIBLE_THUMB_PRIORITY

    if priority is None:
        priority = VISIBLE_THUMB_PRIORITY
    try:
        owner.schedule([item], int(priority), gen=owner._folder_gen)
    except Exception:
        logger.debug(
            "thumbnail schedule failed for %s",
            getattr(item, "path", "?"),
            exc_info=True,
        )


def _on_thumbnail_ready(
    owner, path: Path, cache_path: Path | None, gen: int | None = None
) -> None:
    try:
        owner._thumb_inflight.discard(str(path))
    except Exception:
        pass
    if gen is not None and not owner._is_current_folder_gen(gen):
        return  # folder switched mid-flight — late thumbnail dropped
    item = owner._find_item(path)
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
    owner._queue_card_refresh(item)
    # Per-item completion coalesces to ONE GalleryThumbnailsReady per turn.
    try:
        owner._queue_thumb_ready(path, item.thumbnail_status.value)
    except Exception:
        pass


def _on_thumbnail_error(owner, path: Path, gen: int | None = None) -> None:
    try:
        owner._thumb_inflight.discard(str(path))
    except Exception:
        pass
    if gen is not None and not owner._is_current_folder_gen(gen):
        return
    item = owner._find_item(path)
    if item is None:
        return
    item.thumbnail_status = ThumbnailStatus.ERROR
    owner._queue_card_refresh(item)
    try:
        owner._queue_thumb_ready(path, ThumbnailStatus.ERROR.value)
    except Exception:
        pass
