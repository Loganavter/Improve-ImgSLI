"""Whole-image texture-upload staging queue (single owner, E2 decision).

This module is the one live owner of whole-image texture-upload staging:
PIL/store-to-QImage conversion (uid-deduped), RGBA normalization, and
appending to ``widget.runtime_state._pending_texture_uploads``, which the
rhi_renderer apply path flushes. Retention underneath is engine-owned
(``engine.gpu.host_texture_cache``); this module only stages.

Not a second queue: the multi-slot tab's ``pending_uploads`` intake is a
different stage (slot-source swap decisions feeding the base-images swap
machine, ``engine.gpu.base_images_pass.apply_swap_spec``), never staged
here -- the two never hold the same content.
"""

from __future__ import annotations

import logging

from PySide6.QtGui import QImage

from engine.gpu.host_texture_cache import cache_for_widget, qimage_from_pil
from engine.cache.image_identity import image_uid

_QIMAGE_BY_UID_CACHE_CAPACITY = 4

logger = logging.getLogger("ImproveImgSLI")


def _record_crop_failure(widget, texture_key, exc: BaseException) -> None:
    """Drop a failed crop and record it (V11: never upload the unclipped image).

    Before this, both crop paths swallowed the exception and fell through to the
    *unclipped* upload, which was then marked as a finished tile — the frame showed
    content from outside the tile's slot as if it were the tile (silent-wrong).
    The counter and the once-per-key warning make the degradation a recorded fact
    instead of an invisible one.
    """
    widget._crop_failure_count = int(getattr(widget, "_crop_failure_count", 0) or 0) + 1
    seen = getattr(widget, "_crop_failure_keys", None)
    if seen is None:
        seen = set()
        widget._crop_failure_keys = seen
    if texture_key not in seen:
        seen.add(texture_key)
        logger.warning(
            "[upload-queue] crop failed for %r — upload skipped, the unclipped "
            "image is never substituted: %s",
            texture_key,
            exc,
        )


def _qimage_by_uid_cache(widget):
    state = widget.runtime_state
    cache = getattr(state, "_qimage_by_uid_cache", None)
    if cache is None:
        from collections import OrderedDict

        cache = OrderedDict()
        state._qimage_by_uid_cache = cache
    return cache


def touch_texture_upload_cache(widget, texture_key):
    return cache_for_widget(widget).touch(texture_key)


def cache_texture_upload(widget, texture_key, image: QImage) -> None:
    cache_for_widget(widget).store(texture_key, image)


def evict_texture_upload_cache_over_budget(widget, protected: set, budget_bytes: int) -> None:
    cache_for_widget(widget).evict_over_budget(protected, budget_bytes)


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
    cache_for_widget(widget).store(texture_key, prepared)
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
    *,
    crop_box=None,
) -> None:
    """Queue a whole-image upload, optionally clipped to *crop_box* (W3a).

    *crop_box* is already in the image's own coords (callers scale via
    ``crop_clip.clip_box_for_image``); ``None`` (default) uploads unchanged,
    exactly as before.
    """
    if pil_image is None or not texture_key:
        return
    if crop_box is not None:
        try:
            box_tuple = (
                int(crop_box[0]),
                int(crop_box[1]),
                int(crop_box[2]),
                int(crop_box[3]),
            )
        except Exception as exc:
            # An unparseable crop box is a caller bug; falling through here used
            # to upload the WHOLE image under this tile's key (V11).
            _record_crop_failure(widget, texture_key, exc)
            return
        try:
            from engine.store.tiled_pixel_store import (
                TiledPixelStore,
                qimage_from_pixel_source,
            )
        except Exception:
            # Import failure is not a crop failure: fall through to the PIL path.
            TiledPixelStore = None  # type: ignore[assignment,misc]
            qimage_from_pixel_source = None  # type: ignore[assignment]
        if TiledPixelStore is not None and isinstance(pil_image, TiledPixelStore):
            # Existing sub-rect util: box region straight from the
            # memmap, never a full-frame materialization.
            try:
                prepared = qimage_from_pixel_source(pil_image, box_tuple)
            except Exception as exc:
                _record_crop_failure(widget, texture_key, exc)
                return
            queue_prepared_texture_upload(widget, texture_key, prepared, slot_index)
            return
        try:
            from .crop_clip import clip_image_for_upload

            pil_image = clip_image_for_upload(pil_image, box_tuple)
        except Exception as exc:
            _record_crop_failure(widget, texture_key, exc)
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
    queue_prepared_texture_upload(widget, texture_key, image, slot_index)
