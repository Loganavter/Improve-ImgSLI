
import logging
from typing import Optional

from PIL import Image

logger = logging.getLogger("ImproveImgSLI")

def extract_channel(image: Image.Image, mode: str) -> Optional[Image.Image]:
    if not image:
        return None

    try:
        if image.mode == 'L':
            return image.convert("RGBA")
        if mode == 'L':
            return image.convert("L").convert("RGBA")

        channels = image.convert("RGB").split()
        if mode == 'R':
            return Image.merge("RGB", (channels[0], Image.new("L", image.size, 0), Image.new("L", image.size, 0))).convert("RGBA")
        if mode == 'G':
            return Image.merge("RGB", (Image.new("L", image.size, 0), channels[1], Image.new("L", image.size, 0))).convert("RGBA")
        if mode == 'B':
            return Image.merge("RGB", (Image.new("L", image.size, 0), Image.new("L", image.size, 0), channels[2])).convert("RGBA")

        return image.convert("RGBA")
    except Exception as e:
        logger.error(f"Error extracting channel {mode}: {e}", exc_info=True)
        return None

