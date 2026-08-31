# Audit-Meta: pattern=state-machine reason="single memoised pixel+preview+unify LRU cache — three tiers sharing one lifecycle, stale QImage guard and unify memo by image_uid"
"""PipelineCache — memoised pixel + unify cache with LRU eviction.

Replaces ProgressiveImageLoader full and preview caches LRU 8 + ad-hoc
legacy dedup in session controller.

Keys:
  pixel: (path, mtime_ns, auto_crop, crop_box) -> TiledPixelStore
  unify: (uid1, uid2, method, target_w, target_h) -> (TiledPixelStore, TiledPixelStore)

Both memoise by identity; second slot with same path shares the same store
via refcount (no duplicate decode). Eviction calls close_pixel_store +
pyramid_registry sweep (like ProgressiveImageLoader.clear_cache).
"""

from __future__ import annotations

import logging
import os
from collections import OrderedDict
from typing import TYPE_CHECKING

logger = logging.getLogger("ImproveImgSLI")
try:
    from tabs.image_compare.debug import ic_preview_debug
except Exception:  # pragma: no cover
    def ic_preview_debug(msg, *a, **kw):  # type: ignore
        pass

# Throttle hot-path cache probes: get_pixel is called 4× per frame from
# render_flow (peek) + slot helpers; logging every hit at WARNING floods
# the stream at 60Hz. Only emit when (key, hit) changes.
_last_cache_get_pixel_sig: dict[tuple, bool | None] = {}
_last_cache_get_unified_sig: tuple | None = None
_last_cache_get_unified_hit: bool | None = None

import logging

logger = logging.getLogger("ImproveImgSLI")

if TYPE_CHECKING:
    from shared.image_processing.tiled_pixel_store import TiledPixelStore

# Embedded project pixel cache — single source via host-owned
# ``shared.image_processing.embedded_pixel_cache`` (host may not import tabs,
# see test_ui_tab_sandbox; tabs may import shared). PipelineCache is the
# logical owner; the dict is physically in shared so both layers see the same
# storage without a host→tabs import.
from shared.image_processing.embedded_pixel_cache import _cache as _embedded_cache


def register_embedded_cache(media_path: str, cache_path: str, width: int, height: int) -> None:
    """Register an extracted project cache buffer (B10). Writes to shared host dict."""
    from shared.image_processing import embedded_pixel_cache as _emb

    _emb.register(media_path, cache_path, width, height)
    try:
        norm = os.path.normpath(str(media_path))
        if norm != str(media_path):
            _emb.register(norm, cache_path, width, height)
    except Exception:
        pass


def lookup_embedded_cache(media_path: str) -> tuple[str, int, int] | None:
    from shared.image_processing import embedded_pixel_cache as _emb

    v = _emb.lookup(media_path)
    if v is not None:
        return v
    try:
        norm = os.path.normpath(str(media_path))
        if norm != str(media_path):
            v2 = _emb.lookup(norm)
            if v2 is not None:
                return v2
    except Exception:
        pass
    v = _embedded_cache.get(str(media_path))
    if v is not None:
        return v
    try:
        norm = os.path.normpath(str(media_path))
        if norm != str(media_path):
            return _embedded_cache.get(norm)
    except Exception:
        pass
    return None


def clear_embedded_cache() -> None:
    from shared.image_processing import embedded_pixel_cache as _emb

    _emb.clear()
    _embedded_cache.clear()


def pop_embedded_cache(media_path: str) -> None:
    from shared.image_processing import embedded_pixel_cache as _emb

    for key in (str(media_path), os.path.normpath(str(media_path))):
        _emb.pop(key)
        _embedded_cache.pop(key, None)


# Back-compat alias for isolated tests that patched the old private name.
_pixel_registry = None  # type: ignore


_PIXEL_CACHE_MAX = 8
_UNIFY_CACHE_MAX = 8


def _pixel_key(path: str, crop_service=None, auto_crop: bool | None = None, box_tuple=None) -> tuple:
    # Long-term fix: ключ без box_tuple, только (path,mtime,size,has_crop).
    # box вычисляется lazy внутри GenericWorker и включается в put_pixel ключ
    # только если явно передан (worker-side). GUI не делает sync crop_service.get.
    has_crop = False
    if crop_service is not None:
        has_crop = bool(crop_service) if not isinstance(crop_service, bool) else bool(crop_service)
    elif auto_crop is not None:
        has_crop = bool(auto_crop)
    # box_tuple intentionally NOT fetched synchronously here (was cache.py:121).
    # If caller explicitly provides box_tuple (lazy worker), include it for precise key.
    try:
        st = os.stat(path)
        mtime = st.st_mtime_ns
        size = st.st_size
    except OSError:
        mtime = 0
        size = 0
    if box_tuple is not None:
        return (os.path.normpath(path), mtime, size, bool(has_crop), box_tuple)
    return (os.path.normpath(path), mtime, size, bool(has_crop))


def _unify_key(uid1: int | None, uid2: int | None, method: str, w: int, h: int) -> tuple:
    return (uid1, uid2, method, int(w), int(h))


_PREVIEW_CACHE_MAX = 8
_PREVIEW_SIZE = 1024


def _preview_key(path: str, crop_service=None, auto_crop: bool | None = None, box_tuple=None) -> tuple:
    """Preview tier key: (path, mtime_ns, size, has_crop, 1024) без box.

    Long-term fix: как _pixel_key, без синхронного crop_service.get.
    Mirrors _pixel_key but appends PREVIEW_SIZE sentinel. box вычисляется
    lazy в воркере и передаётся явно если нужен.
    """
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
    if box_tuple is not None:
        return (os.path.normpath(path), mtime, size, bool(has_crop), box_tuple, _PREVIEW_SIZE)
    return (os.path.normpath(path), mtime, size, bool(has_crop), _PREVIEW_SIZE)


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
        max_preview: int = _PREVIEW_CACHE_MAX,
    ):
        self._pixel: OrderedDict[tuple, object] = OrderedDict()
        self._unify: OrderedDict[tuple, tuple] = OrderedDict()
        self._preview: OrderedDict[tuple, object] = OrderedDict()
        self._max_pixel = int(max_pixel)
        self._max_unify = int(max_unify)
        self._max_preview = int(max_preview)
        self.crop_service = crop_service

    # -- pixel tier --

    def get_pixel(self, path: str, crop_service=None, auto_crop: bool | None = None, **_kw):
        # Поддержка старой сигнатуры get_pixel(path, True)
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else (self.crop_service if auto_crop is None else None)
        # если явно передан auto_crop, он приоритетнее сервиса
        box_tuple = _kw.get("box_tuple")
        # support explicit box passed via positional _kw? also check if crop_service hack carried box
        key = _pixel_key(path, eff, auto_crop, box_tuple=box_tuple)
        hit = key in self._pixel
        # fallback: if miss and box not in key, try any box variant (old cache entries or lazy put with box)
        fallback_key = None
        if not hit and box_tuple is None:
            # scan for any key with same prefix (path,mtime,size,has_crop) — handles lazy put with box or old 5-tuple
            try:
                norm = os.path.normpath(path)
                # mtime/size from key (already computed)
                _, mtime, size, has_crop = key[:4] if len(key) >= 4 else (None, None, None, None)
                for k in list(self._pixel.keys()):
                    if len(k) >= 4 and k[0] == norm and k[1] == mtime and k[2] == size and k[3] == bool(has_crop):
                        fallback_key = k
                        hit = True
                        break
            except Exception:
                pass
        # throttle: same (key, hit) repeats at 60Hz from render_flow _peek
        try:
            _last = _last_cache_get_pixel_sig.get(key)
            if _last is not hit:  # type: ignore[has-type]
                _last_cache_get_pixel_sig[key] = hit
                ic_preview_debug("cache get_pixel path=%s eff=%s auto_crop=%s key=%s hit=%s", path, bool(eff), auto_crop, key, hit)
            # keep dict bounded
            if len(_last_cache_get_pixel_sig) > 64:
                # drop oldest
                _last_cache_get_pixel_sig.pop(next(iter(_last_cache_get_pixel_sig)))
        except Exception:
            ic_preview_debug("cache get_pixel path=%s eff=%s auto_crop=%s key=%s hit=%s", path, bool(eff), auto_crop, key, hit)
        store = self._pixel.get(key)
        if store is None and fallback_key is not None:
            store = self._pixel.get(fallback_key)
            key = fallback_key
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
        eff = crop_service if crop_service is not None else (self.crop_service if auto_crop is None else None)
        box_tuple = _kw.get("box_tuple")
        # Если box вычислен lazy в воркере — включаем в ключ (long-term fix)
        key = _pixel_key(path, eff, auto_crop, box_tuple=box_tuple)
        ic_preview_debug("cache put_pixel path=%s eff=%s auto_crop=%s key=%s store=%s", path, bool(eff), auto_crop, key, getattr(store, "uid", id(store)))
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
        """Return cached or load via TiledPixelStore.from_path (DI crop_service).

        Embedded project cache (pixel_cache_registry) is checked first via
        ``lookup_embedded_cache`` → ``TiledPixelStore.from_embedded_cache``,
        otherwise falls back to ``from_path`` (streaming/pyvips or PIL).
        """
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
        # -- embedded project cache (private, migrated from pixel_cache_registry) --
        embedded = lookup_embedded_cache(str(path))
        if embedded is not None:
            cache_path, width, height = embedded
            try:
                from shared.image_processing.autocrop.debug import autocrop_debug
                from shared.image_processing.tiled_pixel_store import TiledPixelStore as _TPS

                autocrop_debug(
                    "cache-hit path=%s -> from_embedded_cache %dx%d (crop_service=%s NOT applied)",
                    str(path), width, height, bool(eff_service),
                )
                store = _TPS.from_embedded_cache(cache_path, width, height)
                if store is not None:
                    self.put_pixel(path, eff_service, store, has_crop_arg)
                return store
            except Exception:
                raise
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

    # -- preview tier (QImage, 1024 cap) --

    def get_preview(self, path: str, crop_service=None, auto_crop: bool | None = None, **_kw):
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else (self.crop_service if auto_crop is None else None)
        if auto_crop is not None:
            eff = eff if auto_crop else None
            has_crop_arg = auto_crop
        else:
            has_crop_arg = None
            eff = eff
        box_tuple = _kw.get("box_tuple")
        key = _preview_key(path, eff, has_crop_arg, box_tuple=box_tuple)
        qimg = self._preview.get(key)
        fallback_key = None
        if qimg is None and box_tuple is None:
            try:
                norm = os.path.normpath(path)
                _, mtime, size, has_crop = key[0], key[1], key[2], key[3]
                for k in list(self._preview.keys()):
                    if len(k) >= 5 and k[0] == norm and k[1] == mtime and k[2] == size and k[3] == bool(has_crop):
                        fallback_key = k
                        qimg = self._preview.get(k)
                        key = k
                        break
            except Exception:
                pass
        if qimg is not None:
            try:
                self._preview.move_to_end(key)
            except Exception:
                pass
            # QImage has isNull() — stale if null
            try:
                if hasattr(qimg, "isNull") and qimg.isNull():
                    self._preview.pop(key, None)
                    return None
            except Exception:
                pass
            return qimg
        return None

    def put_preview(self, path: str, crop_service=None, qimage=None, auto_crop: bool | None = None, **_kw) -> None:
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        if qimage is None and crop_service is not None and hasattr(crop_service, "isNull"):
            # called as put_preview(path, qimage)
            qimage = crop_service
            crop_service = self.crop_service
        if qimage is None:
            return
        if isinstance(crop_service, bool):
            auto_crop = crop_service
            crop_service = None
        box_tuple = _kw.get("box_tuple")
        key = _preview_key(path, crop_service, auto_crop, box_tuple=box_tuple)
        self._preview[key] = qimage
        try:
            self._preview.move_to_end(key)
        except Exception:
            pass
        while len(self._preview) > self._max_preview:
            try:
                self._preview.popitem(last=False)
            except Exception:
                break

    def get_or_load_preview(self, path: str, crop_service=None, auto_crop: bool | None = None):
        """Return cached QImage or load via load_preview_image (DI crop_service)."""
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff_service = crop_service if crop_service is not None else self.crop_service
        if auto_crop is not None:
            eff_service = eff_service if auto_crop else None
            has_crop_arg = auto_crop
        else:
            has_crop_arg = None
        cached = self.get_preview(path, eff_service, has_crop_arg)
        if cached is not None:
            return cached
        try:
            from shared.image_processing.progressive_loader import load_preview_image as _load_preview

            qimg = _load_preview(path, crop_service=eff_service if has_crop_arg is not False else None)
        except Exception:
            raise
        if qimg is not None:
            self.put_preview(path, eff_service, qimg, has_crop_arg)
        return qimg

    def evict(self, path: str) -> None:
        """Evict all pixel+preview entries for path (all auto_crop variants) + sweep pyramid."""
        # embedded project cache — central invalidation (was pixel_cache_registry._cache.pop)
        try:
            pop_embedded_cache(path)
        except Exception:
            pass
        # pixel eviction
        to_drop = [k for k in list(self._pixel.keys()) if k[0] == os.path.normpath(path)]
        for k in to_drop:
            old = self._pixel.pop(k, None)
            self._close_store(old)
        # preview eviction
        try:
            norm = os.path.normpath(path)
            to_drop_prev = [k for k in list(self._preview.keys()) if k[0] == norm]
            for k in to_drop_prev:
                self._preview.pop(k, None)
        except Exception:
            pass
        # pyramid sweep is best-effort (registry may be per-tab) — centralized here
        try:
            from shared.rendering.pyramid_registry import get_pyramid_registry

            reg = get_pyramid_registry()
            if reg is not None:
                try:
                    reg.sweep(path)  # type: ignore[attr-defined]
                except TypeError:
                    reg.sweep()  # type: ignore[attr-defined]
        except Exception:
            try:
                from shared.image_processing import pyramid_registry

                pyramid_registry.sweep()
            except Exception:
                pass
        # unify entries that depend on this path are still keyed by uid, not path,
        # so they naturally miss after pixel eviction; we also drop unify entries
        # whose key contains a closed uid lazily on next get_unified hit.

    def clear(self) -> None:
        for s in list(self._pixel.values()):
            self._close_store(s)
        self._pixel.clear()
        self._preview.clear()
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
            # validate both still open / not stale QImage
            for s in val:
                # QImage preview can become null after eviction / stale
                try:
                    if hasattr(s, "isNull") and s.isNull():
                        self._unify.pop(key, None)
                        ic_preview_debug("cache get_unified key=%s stale QImage.isNull -> miss", key)
                        return None
                except Exception:
                    pass
                is_open = getattr(s, "is_open", None)
                if is_open is not None:
                    try:
                        if not is_open:
                            self._unify.pop(key, None)
                            ic_preview_debug("cache get_unified key=%s stale closed -> miss", key)
                            return None
                        # is_open may be a method (TiledPixelStore) — call if callable
                        if callable(is_open) and not is_open():
                            self._unify.pop(key, None)
                            ic_preview_debug("cache get_unified key=%s stale closed call -> miss", key)
                            return None
                    except Exception:
                        # if check fails, treat as stale
                        pass
            # throttle hit/miss: same key at 60Hz from render_flow
            try:
                global _last_cache_get_unified_sig, _last_cache_get_unified_hit  # type: ignore[used-before-def]
                if _last_cache_get_unified_sig != key or _last_cache_get_unified_hit is not True:  # type: ignore[has-type]
                    _last_cache_get_unified_sig = key  # type: ignore[has-type]
                    _last_cache_get_unified_hit = True  # type: ignore[has-type]
                    ic_preview_debug("cache get_unified hit key=%s", key)
            except Exception:
                ic_preview_debug("cache get_unified hit key=%s", key)
            return val
        # throttle miss
        try:
            if _last_cache_get_unified_sig != key or _last_cache_get_unified_hit is not False:  # type: ignore[has-type]
                _last_cache_get_unified_sig = key  # type: ignore[has-type]
                _last_cache_get_unified_hit = False  # type: ignore[has-type]
                ic_preview_debug("cache get_unified miss key=%s", key)
        except Exception:
            ic_preview_debug("cache get_unified miss key=%s", key)
        return None

    def put_unified(self, uid1, uid2, method: str, w: int, h: int, pair) -> None:
        key = _unify_key(uid1, uid2, method, w, h)
        ic_preview_debug("cache put_unified key=%s pair=%s", key, pair)
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

    # -- embedded cache DI adapter (host -> PipelineCache) --
    # Host layers (services/io/project_io, shared/pixel_cache_loader) accept an
    # injected ``embedded_cache`` object with ``register``/``lookup`` so they
    # never import ``tabs``. When a tab passes its PipelineCache instance,
    # these wrappers delegate to the host-owned storage via the module helpers.
    def register(self, media_path: str, cache_path: str, width: int, height: int) -> None:
        register_embedded_cache(media_path, cache_path, width, height)

    def lookup(self, media_path: str) -> tuple[str, int, int] | None:
        return lookup_embedded_cache(media_path)

    def lookup_embedded_cache(self, media_path: str) -> tuple[str, int, int] | None:  # alias
        return lookup_embedded_cache(media_path)

    def register_embedded_cache(self, media_path: str, cache_path: str, width: int, height: int) -> None:  # alias
        register_embedded_cache(media_path, cache_path, width, height)

    # -- introspection for tests --

    @property
    def pixel_size(self) -> int:
        return len(self._pixel)

    @property
    def unify_size(self) -> int:
        return len(self._unify)

    @property
    def preview_size(self) -> int:
        return len(self._preview)
