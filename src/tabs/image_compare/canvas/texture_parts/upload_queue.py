from __future__ import annotations

from PySide6.QtGui import QImage

from shared.rendering.host_texture_cache import cache_for_widget, qimage_from_pil
from shared.rendering.image_identity import image_uid

_QIMAGE_BY_UID_CACHE_CAPACITY = 4


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
    queue_prepared_texture_upload(widget, texture_key, image, slot_index)
