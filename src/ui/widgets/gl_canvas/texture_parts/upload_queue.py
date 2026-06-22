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


def queue_texture_upload(
    widget,
    pil_image,
    texture_key,
    slot_index: int | None = None,
) -> None:
    if pil_image is None or not texture_key:
        return
    widget.runtime_state._pending_texture_uploads.append(
        (texture_key, qimage_from_pil(pil_image), slot_index)
    )
    if slot_index is not None and 0 <= slot_index < len(
        widget.runtime_state._images_uploaded
    ):
        widget.runtime_state._images_uploaded[slot_index] = True
