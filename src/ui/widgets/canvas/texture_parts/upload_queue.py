from __future__ import annotations

from PySide6.QtGui import QImage


def qimage_from_pil(pil_image) -> QImage:
    image = pil_image.convert("RGBA")
    return QImage(
        image.tobytes("raw", "RGBA"),
        image.width,
        image.height,
        image.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()


def _texture_upload_cache(widget) -> dict:
    state = widget.runtime_state
    cache = getattr(state, "_texture_upload_cache", None)
    if cache is None:
        cache = {}
        setattr(state, "_texture_upload_cache", cache)
    return cache


def queue_prepared_texture_upload(
    widget,
    texture_key,
    image: QImage,
    slot_index: int | None = None,
) -> None:
    if image is None or image.isNull() or not texture_key:
        return
    prepared = image.convertToFormat(QImage.Format.Format_RGBA8888).copy()
    _texture_upload_cache(widget)[texture_key] = prepared
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
    queue_prepared_texture_upload(
        widget,
        texture_key,
        qimage_from_pil(pil_image),
        slot_index,
    )
