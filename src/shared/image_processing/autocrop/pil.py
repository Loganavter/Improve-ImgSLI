"""PIL-реализация поиска bbox — port resize.get_auto_crop_box с типизацией."""
from __future__ import annotations

import logging

from PIL import Image

from .model import CropBox

logger = logging.getLogger("ImproveImgSLI")


def find_box_pil(probe: Image.Image, threshold: int = 15) -> CropBox | None:
    """Найти bbox не-чёрного содержимого через PIL.

    Семантика 1:1 с resize.get_auto_crop_box — конверсия RGB→L, point>thr, getbbox.
    Возвращает None если bbox отсутствует или совпадает с полным кадром.
    """
    try:
        analysis = probe.convert("RGB").convert("L")
        mask = analysis.point(lambda p: 255 if p > threshold else 0)
        bbox = mask.getbbox()
        if bbox and bbox != (0, 0, probe.width, probe.height):
            return CropBox(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3]))
        return None
    except Exception as e:
        logger.debug("PIL find_box failed thr=%s: %s", threshold, e)
        return None
