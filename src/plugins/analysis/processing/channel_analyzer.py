

import logging
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

def extract_channel(image: Image.Image, mode: str) -> Optional[Image.Image]:
    if not image:
        return None

    try:

        if image.mode not in ('RGB', 'RGBA'):
            src = image.convert('RGBA')
        else:
            src = image

        if mode == 'L':

            return src.convert("L").convert("RGBA")

        img_array = np.asarray(src, dtype=np.uint8)
        height, width = img_array.shape[:2]

        result = np.zeros((height, width, 4), dtype=np.uint8)

        if mode == 'R':

            result[:, :, 0] = img_array[:, :, 0]
            result[:, :, 3] = img_array[:, :, 3] if img_array.shape[2] == 4 else 255
        elif mode == 'G':

            result[:, :, 1] = img_array[:, :, 1]
            result[:, :, 3] = img_array[:, :, 3] if img_array.shape[2] == 4 else 255
        elif mode == 'B':

            result[:, :, 2] = img_array[:, :, 2]
            result[:, :, 3] = img_array[:, :, 3] if img_array.shape[2] == 4 else 255
        else:

            return src.convert("RGBA")

        return Image.fromarray(result, 'RGBA')

    except Exception as e:
        logger.error(f"Error extracting channel {mode}: {e}", exc_info=True)
        return image.convert("RGBA")

