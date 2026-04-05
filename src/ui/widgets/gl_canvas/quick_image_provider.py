from __future__ import annotations

from PyQt6.QtCore import QSize
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtQuick import QQuickImageProvider

class QuickCanvasImageProvider(QQuickImageProvider):
    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._images: dict[str, QImage] = {}

    def set_image(self, key: str, image: QImage | None):
        if image is None or image.isNull():
            self._images.pop(key, None)
            return
        self._images[key] = image.copy()

    def clear(self):
        self._images.clear()

    def requestImage(self, image_id: str, requested_size: QSize):
        key = image_id.split("?", 1)[0]
        image = self._images.get(key)
        if image is None:
            empty = QImage(2, 2, QImage.Format.Format_RGBA8888)
            empty.fill(QColor(0, 0, 0, 0))
            return empty, QSize(empty.width(), empty.height())

        if (
            requested_size is not None
            and isinstance(requested_size, QSize)
            and requested_size.width() > 0
            and requested_size.height() > 0
        ):
            scaled = image.scaled(requested_size)
            return scaled, QSize(scaled.width(), scaled.height())
        return image, QSize(image.width(), image.height())
