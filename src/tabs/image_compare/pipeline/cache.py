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


def _pixel_key(path: str, crop_service=None, auto_crop: bool | None = None) -> tuple:
    # DI: ключ содержит наличие crop_service (а не bool), box резолвится при загрузке
    has_crop = False
    if crop_service is not None:
        has_crop = bool(crop_service) if not isinstance(crop_service, bool) else bool(crop_service)
    elif auto_crop is not None:
        has_crop = bool(auto_crop)
    try:
        st = os.stat(path)
        mtime = st.st_mtime_ns
        size = st.st_size
    except OSError:
        mtime = 0
        size = 0
    return (os.path.normpath(path), mtime, size, bool(has_crop))


def _unify_key(uid1: int | None, uid2: int | None, method: str, w: int, h: int) -> tuple:
    return (uid1, uid2, method, int(w), int(h))


class PipelineCache:
    """Single source for pixels; owns TiledPixelStore lifecycle.

    CropService инжектируется (DI) — ключ пикселя зависит от has_crop, а сам
    bbox вычисляется внутри TiledPixelStore через сервис.
    """

    def __init__(
        self,
        max_pixel: int = _PIXEL_CACHE_MAX,
        max_unify: int = _UNIFY_CACHE_MAX,
        crop_service=None,
    ):
        self._pixel: OrderedDict[tuple, object] = OrderedDict()
        self._unify: OrderedDict[tuple, tuple] = OrderedDict()
        self._max_pixel = int(max_pixel)
        self._max_unify = int(max_unify)
        self.crop_service = crop_service

    # -- pixel tier --

    def get_pixel(self, path: str, crop_service=None, auto_crop: bool | None = None, **_kw):
        # Поддержка старой сигнатуры get_pixel(path, True)
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else (self.crop_service if auto_crop is None else None)
        # если явно передан auto_crop, он приоритетнее сервиса
        key = _pixel_key(path, eff, auto_crop)
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

    def put_pixel(self, path: str, crop_service=None, store=None, auto_crop: bool | None = None, **_kw) -> None:
        # Нормализация перегрузки: старый пут put_pixel(path, True, store)
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        # Если store is None и crop_service — это на самом деле store (вызов put_pixel(path, store))
        if store is None and crop_service is not None and hasattr(crop_service, "is_open"):
            store = crop_service
            crop_service = self.crop_service
        if store is None:
            return
        # Если crop_service всё ещё bool
        if isinstance(crop_service, bool):
            auto_crop = crop_service
            crop_service = None
        key = _pixel_key(path, crop_service, auto_crop)
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

    def get_or_load(self, path: str, crop_service=None, auto_crop: bool | None = None):
        """Return cached or load via TiledPixelStore.from_path (DI crop_service)."""
        # Совместимость: если первый arg bool после path — это auto_crop
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff_service = crop_service if crop_service is not None else self.crop_service
        # если явно auto_crop передан, он решает has_crop, иначе наличие eff_service
        if auto_crop is not None:
            eff_service = eff_service if auto_crop else None
            has_crop_arg = auto_crop
        else:
            has_crop_arg = None
        cached = self.get_pixel(path, eff_service, has_crop_arg)
        if cached is not None:
            return cached
        try:
            from shared.image_processing.tiled_pixel_store import TiledPixelStore

            if eff_service is not None and has_crop_arg is not False:
                store = TiledPixelStore.from_path(path, crop_service=eff_service)
            else:
                # нет сервиса → без кропа; поддержка legacy auto_crop bool
                if auto_crop is not None:
                    store = TiledPixelStore.from_path(path, auto_crop=bool(auto_crop))
                else:
                    store = TiledPixelStore.from_path(path, crop_service=None)
        except Exception:
            raise
        if store is not None:
            # кладём с тем же ключом что и get
            self.put_pixel(path, eff_service, store, has_crop_arg)
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
