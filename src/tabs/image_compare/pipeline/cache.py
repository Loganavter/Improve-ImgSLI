"""PipelineCache — memoised pixel + unify cache with LRU eviction.

Replaces ProgressiveImageLoader._full_cache LRU 8 + ad-hoc
_pending_image_loads / _pending_full_loads dedup in _session_controller.py.

Keys:
  pixel: (path, mtime_ns, auto_crop, crop_box) -> TiledPixelStore
  unify: (uid1, uid2, method, target_w, target_h) -> (TiledPixelStore, TiledPixelStore)

Both memoise by identity; second slot with same path shares the same store
via refcount (no duplicate decode). Eviction calls close_pixel_store +
pyramid_registry sweep (like ProgressiveImageLoader.clear_cache).
"""

from __future__ import annotations

import os
from collections import OrderedDict
from typing import TYPE_CHECKING

import logging

logger = logging.getLogger("ImproveImgSLI")

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

_PIXEL_CACHE_MAX = 8
_UNIFY_CACHE_MAX = 8


def _pixel_key(path: str, auto_crop: bool) -> tuple:
    try:
        st = os.stat(path)
        mtime = st.st_mtime_ns
        size = st.st_size
    except OSError:
        mtime = 0
        size = 0
    # crop_box is part of key via autocrop_service.get_crop_box cache,
    # but we include auto_crop flag; box itself is resolved at load time.
    return (os.path.normpath(path), mtime, size, bool(auto_crop))


def _unify_key(uid1: int | None, uid2: int | None, method: str, w: int, h: int) -> tuple:
    return (uid1, uid2, method, int(w), int(h))


class PipelineCache:
    """Single source for pixels; owns TiledPixelStore lifecycle."""

    def __init__(self, max_pixel: int = _PIXEL_CACHE_MAX, max_unify: int = _UNIFY_CACHE_MAX):
        self._pixel: OrderedDict[tuple, object] = OrderedDict()
        self._unify: OrderedDict[tuple, tuple] = OrderedDict()
        self._max_pixel = int(max_pixel)
        self._max_unify = int(max_unify)

    # -- pixel tier --

    def get_pixel(self, path: str, auto_crop: bool = True):
        key = _pixel_key(path, auto_crop)
        store = self._pixel.get(key)
        if store is not None:
            # LRU bump
            try:
                self._pixel.move_to_end(key)
            except Exception:
                pass
            # validate store still open
            is_open = getattr(store, "is_open", None)
            if is_open is not None and not is_open:
                # stale closed store — evict and miss
                self._pixel.pop(key, None)
                return None
            return store
        return None

    def put_pixel(self, path: str, auto_crop: bool, store) -> None:
        if store is None:
            return
        key = _pixel_key(path, auto_crop)
        self._pixel[key] = store
        try:
            self._pixel.move_to_end(key)
        except Exception:
            pass
        while len(self._pixel) > self._max_pixel:
            try:
                _k, _old = self._pixel.popitem(last=False)
                self._close_store(_old)
            except Exception:
                break

    def _close_store(self, store) -> None:
        try:
            from shared.image_processing.tiled_pixel_store import close_pixel_store

            close_pixel_store(store)
        except Exception:
            pass

    def get_or_load(self, path: str, auto_crop: bool = True):
        """Return cached or load via TiledPixelStore.from_path (single-flight caller must dedup)."""
        cached = self.get_pixel(path, auto_crop)
        if cached is not None:
            return cached
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            store = TiledPixelStore.from_path(path, auto_crop=auto_crop)
        except Exception:
            raise
        if store is not None:
            self.put_pixel(path, auto_crop, store)
        return store

    def evict(self, path: str) -> None:
        """Evict all pixel entries for path (all auto_crop variants) + sweep pyramid."""
        # pixel eviction
        to_drop = [k for k in list(self._pixel.keys()) if k[0] == os.path.normpath(path)]
        for k in to_drop:
            old = self._pixel.pop(k, None)
            self._close_store(old)
        # pyramid sweep is best-effort (registry may be per-tab)
        try:
            from shared.rendering.pyramid_registry import get_pyramid_registry

            reg = get_pyramid_registry()
            if reg is not None:
                reg.sweep(path)  # type: ignore[attr-defined]
        except Exception:
            pass
        # unify entries that depend on this path are still keyed by uid, not path,
        # so they naturally miss after pixel eviction; we also drop unify entries
        # whose key contains a closed uid lazily on next get_unified hit.

    def clear(self) -> None:
        for s in list(self._pixel.values()):
            self._close_store(s)
        self._pixel.clear()
        # unify stores are the same objects as pixel stores (unified copies) —
        # they are already closed via pixel eviction if shared; otherwise close.
        for u1, u2 in list(self._unify.values()):
            # u1/u2 may be same as pixel entries — close is idempotent via is_open
            self._close_store(u1)
            self._close_store(u2)
        self._unify.clear()

    # -- unify tier --

    def get_unified(self, uid1, uid2, method: str, w: int, h: int):
        key = _unify_key(uid1, uid2, method, w, h)
        val = self._unify.get(key)
        if val is not None:
            try:
                self._unify.move_to_end(key)
            except Exception:
                pass
            # validate both still open
            for s in val:
                is_open = getattr(s, "is_open", None)
                if is_open is not None and not is_open:
                    self._unify.pop(key, None)
                    return None
            return val
        return None

    def put_unified(self, uid1, uid2, method: str, w: int, h: int, pair) -> None:
        key = _unify_key(uid1, uid2, method, w, h)
        self._unify[key] = pair
        try:
            self._unify.move_to_end(key)
        except Exception:
            pass
        while len(self._unify) > self._max_unify:
            try:
                self._unify.popitem(last=False)
            except Exception:
                break

    # -- introspection for tests --

    @property
    def pixel_size(self) -> int:
        return len(self._pixel)

    @property
    def unify_size(self) -> int:
        return len(self._unify)
