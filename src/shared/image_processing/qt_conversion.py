

import logging
from typing import Optional

import numpy as np
from PIL import Image
from PyQt6.QtGui import QImage, QPixmap

logger = logging.getLogger("ImproveImgSLI")

def pil_to_qimage_zero_copy(pil_image: Image.Image) -> Optional[QImage]:
    if pil_image is None:
        return None

    try:

        if pil_image.mode != 'RGBA':
            pil_image = pil_image.convert('RGBA')

        width, height = pil_image.size

        img_array = np.asarray(pil_image, dtype=np.uint8)

        if len(img_array.shape) != 3 or img_array.shape[2] != 4:
            logger.warning(f"Unexpected array shape: {img_array.shape}, converting to RGBA")
            pil_image = pil_image.convert('RGBA')
            img_array = np.asarray(pil_image, dtype=np.uint8)

        if not img_array.flags['C_CONTIGUOUS']:
            img_array = np.ascontiguousarray(img_array)

        array_memoryview = memoryview(img_array)

        bytes_per_line = width * 4

        try:
            qimage = QImage(
                array_memoryview,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGBA8888
            )

            if qimage.isNull():
                raise ValueError("QImage creation returned null")

        except (TypeError, ValueError):

            data_bytes = img_array.tobytes()
            qimage = QImage(
                data_bytes,
                width,
                height,
                bytes_per_line,
                QImage.Format.Format_RGBA8888
            )

        qimage._pil_array_ref = img_array

        return qimage

    except Exception as e:
        logger.error(f"Error in zero-copy PIL to QImage conversion: {e}", exc_info=True)

        try:
            data = pil_image.tobytes("raw", "RGBA")
            return QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
        except Exception as e2:
            logger.error(f"Fallback conversion also failed: {e2}", exc_info=True)
            return None

def pil_to_qpixmap_optimized(pil_image: Image.Image, copy: bool = False) -> Optional[QPixmap]:
    qimage = pil_to_qimage_zero_copy(pil_image)
    if qimage is None or qimage.isNull():
        return None

    pixmap = QPixmap.fromImage(qimage)

    if copy:
        pixmap = pixmap.copy()

    return pixmap

