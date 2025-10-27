
import logging
from typing import Optional

import numpy as np
from PIL import Image
from skimage.feature import canny
from skimage.util import img_as_ubyte

logger = logging.getLogger("ImproveImgSLI")

def create_edge_map(image: Image.Image, sigma: float = 1.0) -> Optional[Image.Image]:
    if not image:
        return None

    try:
        img_gray = np.array(image.convert('L'))
        edges = canny(img_gray, sigma=sigma)

        return Image.fromarray(img_as_ubyte(edges)).convert("RGBA")
    except Exception as e:
        logger.error(f"Error creating edge map: {e}", exc_info=True)
        return None

