# Audit-Meta: pattern=state-machine reason="single memoised pixel+preview+unify LRU cache — three tiers sharing one lifecycle, stale QImage guard and unify memo by image_uid"
"""PipelineCache — memoised pixel + unify cache with LRU eviction.

Keys:
  pixel: (path, mtime_ns, size, has_crop) -> TiledPixelStore
  preview: (path, mtime_ns, size, has_crop, 1024) -> QImage
  unify: (uid1, uid2, method, target_w, target_h) -> (TiledPixelStore, TiledPixelStore)

box_tuple НЕ входит в ключи: CropService детерминирован для того же
контента, box уже запечён в пиксели при заливке (src_box).

Both memoise by identity; second slot with same path shares the same store
via refcount (no duplicate decode). Eviction calls close_pixel_store +
pyramid_registry sweep + eager-drop unify by uid. Budgets: count AND bytes;
pinned (currently displayed) entries are never evicted.
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
_PREVIEW_CACHE_MAX = 8
_PREVIEW_SIZE = 1024

# Byte budgets (count limits above still apply; eviction triggers on either).
# ~8 × 24MP RGBA (96MB) fits in the pixel/unify budgets; previews are ~4MB each.
_PIXEL_CACHE_MAX_BYTES = 1536 * 1024 * 1024
_UNIFY_CACHE_MAX_BYTES = 1536 * 1024 * 1024
_PREVIEW_CACHE_MAX_BYTES = 128 * 1024 * 1024


def _store_bytes(store) -> int:
    """Best-effort RGBA byte size for budget accounting (0 when unknown/closed)."""
    try:
        from shared.image_processing.tiled_pixel_store import pixel_source_size

        w, h = pixel_source_size(store)
        if w > 0 and h > 0:
            return int(w) * int(h) * 4
    except Exception:
        pass
    return 0


def _qimage_bytes(qimage) -> int:
    try:
        from shared.image_processing.tiled_pixel_store import pixel_source_size

        w, h = pixel_source_size(qimage)
        if w > 0 and h > 0:
            return int(w) * int(h) * 4
    except Exception:
        pass
    return 0


def _unify_pair_bytes(pair) -> int:
    try:
        u1, u2 = pair
    except Exception:
        return 0
    return _store_bytes(u1) + _store_bytes(u2)


def _uid_of(store) -> int | None:
    try:
        from shared.rendering.image_identity import image_uid

        return int(image_uid(store))
    except Exception:
        return None


def _pixel_key(path: str, crop_service=None, auto_crop: bool | None = None, box_tuple=None) -> tuple:
    # Ключ без box_tuple, только (path,mtime,size,has_crop).
    # box детерминирован CropService для того же контента (compute кэширует
    # по normpath, thr15→thr30), уже запечён в пиксели при заливке через
    # src_box — включать его в ключ значит плодить дубли одной картинки.
    # box_tuple принят для совместимости и игнорируется.
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


def _preview_key(path: str, crop_service=None, auto_crop: bool | None = None, box_tuple=None) -> tuple:
    """Preview tier key: (path, mtime_ns, size, has_crop, 1024), box игнирируется.

    См. _pixel_key: box детерминирован и запечён в пиксели, в ключ не входит.
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
        max_pixel_bytes: int = _PIXEL_CACHE_MAX_BYTES,
        max_unify_bytes: int = _UNIFY_CACHE_MAX_BYTES,
        max_preview_bytes: int = _PREVIEW_CACHE_MAX_BYTES,
    ):
        self._pixel: OrderedDict[tuple, object] = OrderedDict()
        self._unify: OrderedDict[tuple, tuple] = OrderedDict()
        self._preview: OrderedDict[tuple, object] = OrderedDict()
        self._max_pixel = int(max_pixel)
        self._max_unify = int(max_unify)
        self._max_preview = int(max_preview)
        self._max_pixel_bytes = int(max_pixel_bytes)
        self._max_unify_bytes = int(max_unify_bytes)
        self._max_preview_bytes = int(max_preview_bytes)
        # Pin: pixel-ключи и unify-uid которые сейчас на canvas.
        # Eviction пропускает их (см. tile/texture evict_over_budget с protected).
        self._pinned_pixel_keys: set[tuple] = set()
        self._pinned_uids: set[int] = set()
        self.crop_service = crop_service

    # -- pin (защита видимого от eviction) --

    def pin_paths(self, paths) -> None:
        """Запинить пути текущего показа (ключи без box, все has_crop-варианты)."""
        try:
            for p in list(paths or []):
                if not p:
                    continue
                norm = os.path.normpath(str(p))
                for k in list(self._pixel.keys()):
                    if k and k[0] == norm:
                        self._pinned_pixel_keys.add(k)
                for s in list(self._pixel.values()):
                    uid = _uid_of(s)
                    # пиним только uid показанных путей
                    try:
                        same = any(k and k[0] == norm for k in list(self._pixel.keys()))
                    except Exception:
                        same = False
                    if same and uid is not None:
                        self._pinned_uids.add(uid)
        except Exception:
            pass

    def unpin_paths(self, paths) -> None:
        try:
            norms = {os.path.normpath(str(p)) for p in list(paths or []) if p}
        except Exception:
            return
        self._pinned_pixel_keys = {k for k in self._pinned_pixel_keys if not (k and k[0] in norms)}
        # uids чистим лениво: дропаем те, чьих путей больше нет в пикселях
        try:
            live_uids = {_uid_of(s) for s in self._pixel.values()}
            self._pinned_uids = {u for u in self._pinned_uids if u in live_uids}
        except Exception:
            pass

    def set_pinned_paths(self, paths) -> None:
        self._pinned_pixel_keys.clear()
        self._pinned_uids.clear()
        self.pin_paths(paths)

    # -- budget helpers --

    def _pixel_bytes(self) -> int:
        return sum(_store_bytes(s) for s in self._pixel.values())

    def _preview_bytes(self) -> int:
        return sum(_qimage_bytes(q) for q in self._preview.values())

    def _unify_bytes(self) -> int:
        return sum(_unify_pair_bytes(p) for p in self._unify.values())

    def _ensure_pixel_budget(self) -> None:
        while (len(self._pixel) > self._max_pixel or self._pixel_bytes() > self._max_pixel_bytes) and self._pixel:
            evicted = False
            for k in list(self._pixel.keys()):
                if k in self._pinned_pixel_keys:
                    continue
                old = self._pixel.pop(k, None)
                uid = _uid_of(old)
                if uid is not None:
                    self._pinned_uids.discard(uid)
                self._drop_unify_for_uids({uid})
                self._close_store(old)
                evicted = True
                break
            if not evicted:
                break  # всё запинено — терпим over-budget, не выселяем видимое

    def _ensure_preview_budget(self) -> None:
        while (len(self._preview) > self._max_preview or self._preview_bytes() > self._max_preview_bytes) and self._preview:
            try:
                self._preview.popitem(last=False)
            except Exception:
                break

    def _ensure_unify_budget(self) -> None:
        while (len(self._unify) > self._max_unify or self._unify_bytes() > self._max_unify_bytes) and self._unify:
            evicted = False
            for k in list(self._unify.keys()):
                try:
                    u1, u2 = self._unify[k][0], self._unify[k][1]
                    uids = {_uid_of(u1), _uid_of(u2)} - {None}
                except Exception:
                    uids = set()
                if uids & self._pinned_uids:
                    continue
                pair = self._unify.pop(k, None)
                self._close_unify_pair(pair)
                evicted = True
                break
            if not evicted:
                break

    def _close_unify_pair(self, pair) -> None:
        """Закрыть unify-пару, не трогая сторы всё ещё живые в _pixel."""
        if pair is None:
            return
        try:
            u1, u2 = pair
        except Exception:
            return
        try:
            live_ids = {id(s) for s in self._pixel.values()}
        except Exception:
            live_ids = set()
        for s in (u1, u2):
            try:
                if s is not None and id(s) not in live_ids:
                    self._close_store(s)
            except Exception:
                pass

    def _drop_unify_for_uids(self, uids: set) -> None:
        """Eager-drop unify-записей, ссылающихся на выселяемые пиксели."""
        uids = {u for u in (uids or set()) if u is not None}
        if not uids:
            return
        for k in list(self._unify.keys()):
            try:
                uid1, uid2 = k[0], k[1]
            except Exception:
                continue
            if uid1 in uids or uid2 in uids:
                pair = self._unify.pop(k, None)
                self._close_unify_pair(pair)

    # -- pixel tier --

    def get_pixel(self, path: str, crop_service=None, auto_crop: bool | None = None, **_kw):
        # Поддержка старой сигнатуры get_pixel(path, True)
        if isinstance(crop_service, bool) and auto_crop is None:
            auto_crop = crop_service
            crop_service = None
        eff = crop_service if crop_service is not None else (self.crop_service if auto_crop is None else None)
        # если явно передан auto_crop, он приоритетнее сервиса
        key = _pixel_key(path, eff, auto_crop)
        hit = key in self._pixel
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
        if store is not None:
            # LRU bump
            try:
                self._pixel.move_to_end(key)
            except Exception:
                pass
            # validate store still open
            is_open = getattr(store, "is_open", None)
            if callable(is_open):
                try:
                    if not is_open():
                        self._pixel.pop(key, None)
                        return None
                except Exception:
                    pass
            elif is_open is not None and not is_open:
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
        key = _pixel_key(path, eff, auto_crop)
        ic_preview_debug("cache put_pixel path=%s eff=%s auto_crop=%s key=%s store=%s", path, bool(eff), auto_crop, key, getattr(store, "uid", id(store)))
        self._pixel[key] = store
        try:
            self._pixel.move_to_end(key)
        except Exception:
            pass
        self._ensure_pixel_budget()

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
        key = _preview_key(path, eff, has_crop_arg)
        qimg = self._preview.get(key)
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
        key = _preview_key(path, crop_service, auto_crop)
        self._preview[key] = qimage
        try:
            self._preview.move_to_end(key)
        except Exception:
            pass
        self._ensure_preview_budget()

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
        # pixel eviction (uid собираем ДО close — info живёт и после, но так надёжнее)
        to_drop = [k for k in list(self._pixel.keys()) if k and k[0] == os.path.normpath(path)]
        evicted_uids: set = set()
        for k in to_drop:
            old = self._pixel.pop(k, None)
            uid = _uid_of(old)
            if uid is not None:
                evicted_uids.add(uid)
                self._pinned_uids.discard(uid)
            self._pinned_pixel_keys.discard(k)
            self._close_store(old)
        # preview eviction
        try:
            norm = os.path.normpath(path)
            to_drop_prev = [k for k in list(self._preview.keys()) if k and k[0] == norm]
            for k in to_drop_prev:
                self._preview.pop(k, None)
        except Exception:
            pass
        # eager-drop unify, ссылающихся на высеченные пиксели (иначе .raw висят до LRU)
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
        self._drop_unify_for_uids(evicted_uids)

    def clear(self) -> None:
        for s in list(self._pixel.values()):
            self._close_store(s)
        self._pixel.clear()
        self._preview.clear()
        self._pinned_pixel_keys.clear()
        self._pinned_uids.clear()
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
        self._ensure_unify_budget()

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
