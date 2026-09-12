"""Host-side QImage LRU cache for GPU texture upload paths."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import fields, is_dataclass

from PySide6.QtGui import QImage

from shared.image_processing.tiled_pixel_store import TiledPixelStore, qimage_from_pixel_source
from shared.rendering.image_identity import image_uid

_QIMAGE_BY_UID_CACHE_CAPACITY = 4
DEFAULT_HOST_TEXTURE_CACHE_BUDGET_BYTES = 3 * 1024 * 1024 * 1024


def qimage_from_pil(pil_image) -> QImage:
    """Convert PIL or TiledPixelStore to RGBA QImage."""
    if isinstance(pil_image, TiledPixelStore):
        return qimage_from_pixel_source(pil_image)
    image = pil_image.convert("RGBA")
    return QImage(
        image.tobytes("raw", "RGBA"),
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


class HostTextureUploadCache:
    """LRU byte-budget cache of full-resolution QImages keyed by texture role."""

    def __init__(self, budget_bytes: int):
        self._budget_bytes = budget_bytes
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._uid_cache: OrderedDict[int, QImage] = OrderedDict()

    def touch(self, texture_key: str) -> QImage | None:
        image = self._cache.get(texture_key)
        if image is not None:
            self._cache.move_to_end(texture_key)
        return image

    def store(self, texture_key: str, image: QImage) -> None:
        self._cache[texture_key] = image
        self._cache.move_to_end(texture_key)

    def evict_over_budget(self, protected: set[str], budget_bytes: int | None = None) -> None:
        budget = self._budget_bytes if budget_bytes is None else budget_bytes
        total_bytes = sum(image.sizeInBytes() for image in self._cache.values())
        if total_bytes <= budget:
            return
        for texture_key in list(self._cache.keys()):
            if total_bytes <= budget:
                break
            if texture_key in protected:
                continue
            evicted = self._cache.pop(texture_key, None)
            if evicted is not None:
                total_bytes -= evicted.sizeInBytes()

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
    if _host_has_field(state, "_texture_upload_cache"):
        state._texture_upload_cache = cache.entries
    return cache
