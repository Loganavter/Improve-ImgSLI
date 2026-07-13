from __future__ import annotations

from collections import OrderedDict

from PySide6.QtGui import QImage

from shared.rendering.image_identity import image_uid

# Small bridge cache, not a general-purpose store: dedupes the decode when
# the same PIL image is uploaded to two texture keys back-to-back (e.g.
# stored_N/source_N under shader letterbox mode -- see
# docs/dev/rendering/tile-rendering-system.md Phase 1). Bounded and LRU-evicted
# so it never becomes another permanent full-resolution resident like
# ``_texture_upload_cache`` (see Phase 2 in that doc).
_QIMAGE_BY_UID_CACHE_CAPACITY = 4


def qimage_from_pil(pil_image) -> QImage:
    # docs/dev/rendering/tile-rendering-system.md Phase 3: LazyPixelSource
    # doesn't have PIL's .convert() -- materialize it here as a safety
    # net. Callers that already know the source is lazy
    # (realize_tile_plan's multi-tile path) avoid reaching this by
    # cropping via LazyPixelSource.crop() directly instead of passing the
    # whole source in; this fallback only fires for the one-time initial
    # texture queue (see upload_source_pil_image), and the resulting
    # cached QImage is naturally evicted by the host texture cache's LRU
    # budget once tile realization takes over and stops touching it.
    from shared.image_processing.lazy_pixel_source import LazyPixelSource

    if isinstance(pil_image, LazyPixelSource):
        pil_image = pil_image.to_pil()
    image = pil_image.convert("RGBA")
    return QImage(
        image.tobytes("raw", "RGBA"),
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


def _texture_upload_cache(widget) -> OrderedDict:
    state = widget.runtime_state
    cache = getattr(state, "_texture_upload_cache", None)
    if cache is None:
        cache = OrderedDict()
        setattr(state, "_texture_upload_cache", cache)
    return cache


def touch_texture_upload_cache(widget, texture_key):
    """Reads ``texture_key`` from ``_texture_upload_cache`` and, on a hit,
    marks it most-recently-used (moves it to the end). Read call sites must
    use this instead of a raw ``cache.get(key)`` so
    ``evict_texture_upload_cache_over_budget``'s LRU order reflects actual
    recent use, not just insertion order."""
    cache = _texture_upload_cache(widget)
    image = cache.get(texture_key)
    if image is not None:
        cache.move_to_end(texture_key)
    return image


def cache_texture_upload(widget, texture_key, image: QImage) -> None:
    """Stores an already-prepared full-resolution QImage directly, without
    queuing a GPU upload. Used by the ``realize_tile_plan`` cache-miss
    fallback: the tile crop is uploaded to the GPU, not this full image --
    this just re-populates the host cache entry that
    ``touch_texture_upload_cache``/eviction expect to find next time."""
    cache = _texture_upload_cache(widget)
    cache[texture_key] = image
    cache.move_to_end(texture_key)


def evict_texture_upload_cache_over_budget(
    widget, protected: set, budget_bytes: int
) -> None:
    """Bounds the host-side full-resolution QImage residents (docs/dev/
    tile-rendering-system.md Phase 2): evicts least-recently-touched
    entries (oldest first, per ``touch_texture_upload_cache``'s ordering)
    until total resident bytes are back under budget, never evicting a key
    in ``protected`` regardless of budget -- callers pass the texture keys
    they just used this frame, so whichever "side" (stored vs. hi-res
    source) is actually on screen right now always survives eviction; only
    the currently-unused side/diff buffer gets dropped, to be lazily
    re-derived from the still-retained PIL image next time it's needed
    (see the cache-miss fallback in ``RhiResources.realize_tile_plan``)."""
    cache = _texture_upload_cache(widget)
    total_bytes = sum(image.sizeInBytes() for image in cache.values())
    if total_bytes <= budget_bytes:
        return
    for texture_key in list(cache.keys()):
        if total_bytes <= budget_bytes:
            break
        if texture_key in protected:
            continue
        evicted = cache.pop(texture_key, None)
        if evicted is not None:
            total_bytes -= evicted.sizeInBytes()


def _qimage_by_uid_cache(widget) -> OrderedDict:
    state = widget.runtime_state
    cache = getattr(state, "_qimage_by_uid_cache", None)
    if cache is None:
        cache = OrderedDict()
        setattr(state, "_qimage_by_uid_cache", cache)
    return cache


def queue_prepared_texture_upload(
    widget,
    texture_key,
    image: QImage,
    slot_index: int | None = None,
) -> None:
    if image is None or image.isNull() or not texture_key:
        return
    prepared = (
        image
        if image.format() == QImage.Format.Format_RGBA8888
        else image.convertToFormat(QImage.Format.Format_RGBA8888).copy()
    )
    cache = _texture_upload_cache(widget)
    cache[texture_key] = prepared
    cache.move_to_end(texture_key)
    widget.runtime_state._pending_texture_uploads.append(
        (texture_key, prepared, slot_index)
    )
    if slot_index is not None and 0 <= slot_index < len(
        widget.runtime_state._images_uploaded
    ):
        widget.runtime_state._images_uploaded[slot_index] = True


def queue_texture_upload(
    widget,
    pil_image,
    texture_key,
    slot_index: int | None = None,
) -> None:
    if pil_image is None or not texture_key:
        return
    uid = image_uid(pil_image)
    uid_cache = _qimage_by_uid_cache(widget)
    image = uid_cache.get(uid)
    if image is not None:
        uid_cache.move_to_end(uid)
    else:
        image = qimage_from_pil(pil_image)
        uid_cache[uid] = image
        if len(uid_cache) > _QIMAGE_BY_UID_CACHE_CAPACITY:
            uid_cache.popitem(last=False)
    queue_prepared_texture_upload(
        widget,
        texture_key,
        image,
        slot_index,
    )
