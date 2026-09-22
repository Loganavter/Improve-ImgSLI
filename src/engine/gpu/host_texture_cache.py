"""Host-side QImage LRU cache for GPU texture upload paths."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import fields, is_dataclass

from PySide6.QtGui import QImage

from engine.store.tiled_pixel_store import TiledPixelStore, qimage_from_pixel_source
from engine.cache.image_identity import image_uid

_QIMAGE_BY_UID_CACHE_CAPACITY = 4
DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES = 3 * 1024 * 1024 * 1024


def qimage_from_pil(pil_image) -> QImage:
    """Convert PIL or TiledPixelStore to RGBA QImage."""
    if isinstance(pil_image, QImage):
        if pil_image.format() != QImage.Format.Format_RGBA8888:
            return pil_image.convertToFormat(QImage.Format.Format_RGBA8888)
        return pil_image.copy()
    if isinstance(pil_image, TiledPixelStore):
        return qimage_from_pixel_source(pil_image)
    # PIL's convert() always copies even when mode already matches -- on a
    # cropped hi-res tile (already RGBA out of TiledPixelStore.crop) that's a
    # full extra tile-sized memcpy for nothing, and this path runs per-tile,
    # synchronously, inside render()'s realize_tile_plan.
    image = pil_image if pil_image.mode == "RGBA" else pil_image.convert("RGBA")
    return QImage(
        image.tobytes("raw", "RGBA"),
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


class HostTextureUploadCache:
    """LRU byte-budget cache of full-resolution QImages keyed by texture role.

    Aliasing contract (audited): ``_uid_cache`` owns one canonical QImage
    per content uid and ``_cache`` holds a second reference to the *same*
    object for the texture-role lookup -- not a copy, so a decode serves
    every role without re-decoding. Consequences, both enforced here:

    - Callers must treat the returned QImage as read-only. Mutating it
      (paint, convert in place) would corrupt every role sharing that
      uid. Upload paths only sample from it.
    - Byte accounting dedupes by object identity (``_cache_bytes``): the
      shared image is charged once no matter how many role keys point at
      it. Evicting a role key drops only that reference; the canonical
      entry's own bytes are released only when the uid entry itself is
      evicted, and each release subtracts exactly once in both
      directions (role-evict and uid-evict never double-subtract a still-
      referenced image).
    """

    def __init__(self, budget_bytes: int):
        self._budget_bytes = budget_bytes
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._uid_cache: OrderedDict[int, QImage] = OrderedDict()
        # Live byte total, charged once per unique QImage object even when
        # it is referenced from both dicts (see class docstring). Updated
        # incrementally on store/evict so eviction never has to re-scan.
        self._cache_bytes = 0

    @staticmethod
    def _image_bytes(image: QImage) -> int:
        try:
            return int(image.sizeInBytes())
        except Exception:
            return 0

    def _total_bytes(self) -> int:
        # Recomputed (not trusted blindly from the incremental counter)
        # because QImages can detach/reallocate under implicit sharing;
        # cheap: both dicts are tiny (roles + <=cap uid entries).
        seen: set[int] = set()
        total = 0
        for image in list(self._cache.values()) + list(self._uid_cache.values()):
            if id(image) in seen:
                continue
            seen.add(id(image))
            total += self._image_bytes(image)
        return total

    def touch(self, texture_key: str) -> QImage | None:
        image = self._cache.get(texture_key)
        if image is not None:
            self._cache.move_to_end(texture_key)
        return image

    def store(self, texture_key: str, image: QImage) -> None:
        old = self._cache.get(texture_key)
        if old is not None and old is image:
            self._cache.move_to_end(texture_key)
            return
        self._cache[texture_key] = image
        self._cache.move_to_end(texture_key)
        self._cache_bytes = self._total_bytes()

    def evict_over_budget(self, protected: set[str], budget_bytes: int | None = None) -> None:
        budget = self._budget_bytes if budget_bytes is None else budget_bytes
        total_bytes = self._total_bytes()
        if total_bytes <= budget:
            self._cache_bytes = total_bytes
            return
        for texture_key in list(self._cache.keys()):
            if total_bytes <= budget:
                break
            if texture_key in protected:
                continue
            evicted = self._cache.pop(texture_key, None)
            if evicted is not None:
                total_bytes = self._total_bytes()
        # If still over budget after draining _cache, evict oldest UID entries.
        if total_bytes > budget:
            for uid in list(self._uid_cache.keys()):
                if total_bytes <= budget:
                    break
                evicted = self._uid_cache.pop(uid, None)
                if evicted is not None:
                    total_bytes = self._total_bytes()
        self._cache_bytes = total_bytes

    def qimage_from_source(self, pil_image, texture_key: str) -> QImage:
        uid = image_uid(pil_image)
        image = self._uid_cache.get(uid)
        if image is not None:
            self._uid_cache.move_to_end(uid)
        else:
            image = qimage_from_pil(pil_image)
            self._uid_cache[uid] = image
            if len(self._uid_cache) > _QIMAGE_BY_UID_CACHE_CAPACITY:
                self._uid_cache.popitem(last=False)
        self.store(texture_key, image)
        self._cache_bytes = self._total_bytes()
        return image

    @property
    def entries(self) -> OrderedDict[str, QImage]:
        return self._cache


def _host_has_field(host, attr: str) -> bool:
    if is_dataclass(host):
        return attr in {field.name for field in fields(host)}
    return hasattr(host, attr)


def cache_for_widget(widget, budget_bytes: int | None = None) -> HostTextureUploadCache:
    return cache_for_host(widget, budget_bytes=budget_bytes, attr="_host_texture_upload_cache")


def cache_for_host(
    host,
    *,
    budget_bytes: int | None = None,
    attr: str = "_host_texture_upload_cache",
) -> HostTextureUploadCache:
    """Return (or create) the host QImage LRU cache on ``host``.

    Image Compare stores the cache on ``widget.runtime_state``; Multi Compare
    stores it on the canvas widget directly. Both pass ``host`` here.
    """
    state = getattr(host, "runtime_state", host)
    cache = None
    if _host_has_field(state, attr):
        cache = getattr(state, attr, None)
    if cache is None and host is not state:
        cache = getattr(host, attr, None)
    if cache is None:
        if budget_bytes is None:
            budget_bytes = DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES
        cache = HostTextureUploadCache(budget_bytes)
        if _host_has_field(state, attr):
            setattr(state, attr, cache)
        else:
            setattr(host, attr, cache)
    # Barrier-seam aliasing (canvas-runtime dogma): never rebind the
    # runtime state's live upload dict here. The only writer of
    # ``state._texture_upload_cache`` is the DerivedGpuState barrier
    # (``engine.cache.display_tier_service.upload_pil_images`` and its
    # queue/upload collaborators); this helper only *adopts* the state's
    # existing dict as the cache backend in place, so ``cache.entries IS
    # state._texture_upload_cache`` with zero direct state mutation.
    if _host_has_field(state, "_texture_upload_cache"):
        live = getattr(state, "_texture_upload_cache", None)
        if isinstance(live, OrderedDict) and cache.entries is not live:
            for key, image in list(cache.entries.items()):
                live.setdefault(key, image)
            cache._cache = live
    return cache
