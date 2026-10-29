"""Source-image cache for the video editor.

``get_image`` used to decode every (path, auto_crop) key with
``TiledPixelStore.from_path`` even when the Image Compare tab already held
that exact decode (opening the editor re-decoded the full PNGs, ~0.27 s per
2816x2304 frame). The session's decodes live in
``engine.store.shared_pixel_registry``, published by the IC tab's
``load_pixel_store`` funnel under ``(realpath, mtime_ns, size,
crop_fingerprint)``; a lookup-only ``acquire(path, crop_fingerprint=None)``
therefore hits the very store the tab published. Only the no-crop key is
reused: ``auto_crop=True`` needs the crop box, which is not known before
decoding, so it keeps today's ``from_path`` path (and its published box key
is a different fingerprint anyway).

A hit is a NON-OWNING registry view: this repository tracks it and drops it
via ``shared_pixel_registry.release_store`` when it clears the cache, so the
tab's spill is never pulled out from under it. A miss, a ``None``, or any
registry failure falls through to ``from_path`` unchanged (fail-open).
"""

from __future__ import annotations

import logging
import os
import threading

from engine.store.tiled_pixel_store import TiledPixelStore
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def _acquire_shared_store(path: str):
    """Session-wide decoded store for ``path`` under the IC publish key.

    ``crop_fingerprint=None`` is exactly what ``load_pixel_store`` publishes
    when no crop service is in play. Never raises: a miss, a malformed
    handle or any registry error means "no shared store".
    """
    try:
        from engine.store import shared_pixel_registry

        handle = shared_pixel_registry.acquire(path, crop_fingerprint=None)
    except Exception:
        return None
    if handle is None:
        return None
    try:
        return getattr(handle, "store", None)
    except Exception:
        return None


def _release_shared_store(store) -> None:
    """Drop one registry ref for a cached view (never raises)."""
    try:
        from engine.store import shared_pixel_registry

        shared_pixel_registry.release_store(store)
    except Exception:
        pass


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
        # Cache keys whose value is a NON-OWNING shared-registry view. These
        # end their life via shared_pixel_registry.release_store (refcount
        # drop), never via close() — the owning base belongs to the tab that
        # decoded it.
        self._shared_views: set[tuple[str, bool]] = set()

    def clear(self) -> None:
        """Single reset path for the image cache.

        Only ``VideoExporterService._clear_frame_caches`` calls this (export
        start/finish); nothing clears entries ad-hoc, so preview, export,
        and thumbnail renders share one image identity per (path, auto_crop).
        In-flight decodes keep their markers — their owners publish under
        the guard mutex after this returns, which only re-adds entries.

        Cached shared views are released here so the session registry does
        not keep a ref for a store this repository no longer uses. Directly
        decoded stores keep today's lifecycle (the caller that dropped them
        owns the close).
        """
        with self._images_lock:
            for cache_key in list(self._shared_views):
                _release_shared_store(self._images_cache.get(cache_key))
            self._shared_views.clear()
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

        shared = None if auto_crop else _acquire_shared_store(path)
        img = shared
        if img is None:
            try:
                img = TiledPixelStore.from_path(path, auto_crop=auto_crop)
            except Exception as exc:
                logger.error("Failed to load image for video: %s - %s", path, exc)
                img = None

        with self._images_lock:
            if img is not None:
                previous = self._images_cache.get(cache_key)
                if cache_key in self._shared_views and previous is not img:
                    # Replace path (post-clear re-add): the old view's ref
                    # must not outlive the entry it was cached under.
                    _release_shared_store(previous)
                    self._shared_views.discard(cache_key)
                self._images_cache[cache_key] = img
                if shared is not None:
                    self._shared_views.add(cache_key)
            self._inflight.pop(cache_key, None)
            waiter.set()
        return img
