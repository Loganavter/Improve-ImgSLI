"""VIPS-реализация поиска bbox через pyvips find_trim."""
from __future__ import annotations

import logging

import numpy as np

from .model import CropBox

logger = logging.getLogger("ImproveImgSLI")


def find_box_vips(rgb: np.ndarray, threshold: int = 15) -> CropBox | None:
    """BBox не-чёрного содержимого через vips find_trim — без PIL-проходов.

    rgb должен быть уже зондом (возможно даунскейл). Оборачивает его в vips
    одним memcpy, без попиксельного Python. Возвращает None при ошибке.
    """
    try:
        from shared.image_processing.progressive_loader import PYVIPS_SUPPORTED

        if not PYVIPS_SUPPORTED:
            return None
    except Exception:
        return None
    try:
        import pyvips  # type: ignore[import-untyped]

        a = np.ascontiguousarray(rgb[:, :, :3], dtype=np.uint8)
        h, w = a.shape[0], a.shape[1]
        vimg = pyvips.Image.new_from_memory(a.tobytes(), w, h, 3, "uchar")
        left, top, width, height = vimg.find_trim(threshold=threshold, background=[0, 0, 0])
        if width <= 0 or height <= 0:
            return None
        right, bottom = left + width, top + height
        if (left, top, right, bottom) == (0, 0, w, h):
            return None
        return CropBox(int(left), int(top), int(right), int(bottom))
    except Exception as e:
        logger.debug("vips find_trim failed thr=%s: %s", threshold, e)
        return None
