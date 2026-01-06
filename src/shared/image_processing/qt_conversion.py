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

        img_array = np.array(pil_image, copy=False)

        if not img_array.flags['C_CONTIGUOUS']:
            img_array = np.ascontiguousarray(img_array)

        height, width, channels = img_array.shape

        if channels != 4:

            logger.warning(f"Unexpected array shape: {img_array.shape}, falling back to slow copy.")
            data = pil_image.tobytes("raw", "RGBA")
            qimage = QImage(data, width, height, QImage.Format.Format_RGBA8888)

            return qimage.copy()

        qimage = QImage(
            img_array.data,
            width,
            height,
            img_array.strides[0],
            QImage.Format.Format_RGBA8888
        )

        qimage._ndarray_ref = img_array

        return qimage

    except Exception as e:
        logger.error(f"Error in zero-copy PIL to QImage conversion: {e}", exc_info=True)

        try:
            if pil_image.mode != 'RGBA':
                pil_image = pil_image.convert('RGBA')
            data = pil_image.tobytes("raw", "RGBA")
            qimage = QImage(data, pil_image.width, pil_image.height, QImage.Format.Format_RGBA8888)
            return qimage.copy()
        except Exception as e2:
            logger.error(f"Fallback conversion also failed: {e2}", exc_info=True)
            return None

def pil_to_qpixmap_optimized(pil_image: Image.Image, copy: bool = False) -> Optional[QPixmap]:
    qimage = pil_to_qimage_zero_copy(pil_image)
    if qimage is None or qimage.isNull():
        return None

    pixmap = QPixmap.fromImage(qimage)

    if copy:
        return pixmap.copy()

    return pixmap
