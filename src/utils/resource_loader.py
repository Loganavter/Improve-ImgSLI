import sys
from pathlib import Path
from typing import Callable, Tuple, Union

from PIL import Image, ImageFont
from PyQt6.QtCore import QPoint, QRect

def safe_rect(x, y, w, h) -> QRect:
    return QRect(int(round(x)), int(round(y)), int(round(w)), int(round(h)))

def safe_point(x, y) -> QPoint:
    return QPoint(int(round(x)), int(round(y)))

def resource_path(relative_path: str) -> str:
    try:
        base_path = Path(sys._MEIPASS)
    except Exception:

        current_file = Path(__file__).resolve()
        base_path = current_file.parent.parent
    return (base_path / relative_path).as_posix()

FontType = Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]
GetSizeFuncType = Callable[[str, FontType], Tuple[int, int]]

def _find_longest_prefix(
    text_to_fit: str,
    max_available_width: int,
    max_chars_limit: int,
    font_instance: FontType,
    get_size_func: GetSizeFuncType,
) -> Union[str, None]:
    best_fit = None
    low = 0
    high = min(len(text_to_fit), max_chars_limit)

    while low <= high:
        mid = (low + high) // 2
        prefix = text_to_fit[:mid]
        try:
            width, _ = get_size_func(prefix, font_instance)
            if width <= max_available_width:
                best_fit = prefix
                low = mid + 1
            else:
                high = mid - 1
        except Exception:
            high = mid - 1

    return best_fit

def truncate_text(
    raw_text: str,
    available_width: int,
    max_len: int,
    font_instance: FontType,
    get_size_func: GetSizeFuncType,
) -> str:
    if not raw_text or available_width <= 5:
        return ""

    if len(raw_text) <= max_len:
        try:
            text_w, _ = get_size_func(raw_text, font_instance)
            if text_w <= available_width:
                return raw_text
        except Exception:
            pass

    for ellipsis in ["...", "..", "."]:
        if max_len < len(ellipsis):
            continue

        try:
            ellipsis_width, _ = get_size_func(ellipsis, font_instance)

            if ellipsis_width > available_width:
                continue

            available_width_for_text = available_width - ellipsis_width
            max_chars_for_text = max_len - len(ellipsis)

            base_text = _find_longest_prefix(
                raw_text,
                available_width_for_text,
                max_chars_for_text,
                font_instance,
                get_size_func,
            )

            if base_text is not None:
                return base_text + ellipsis
        except Exception:
            continue

    final_attempt_text = _find_longest_prefix(
        raw_text, available_width, max_len, font_instance, get_size_func
    )

    return final_attempt_text or ""

def get_scaled_pixmap_dimensions(
    image1: Image.Image,
    image2: Image.Image,
    target_width: int,
    target_height: int,
) -> Tuple[int, int]:
    if not image1 or not image2:
        return target_width, target_height

    img1_w, img1_h = image1.size
    img2_w, img2_h = image2.size

    if img1_w <= 0 or img1_h <= 0 or img2_w <= 0 or img2_h <= 0:
        return target_width, target_height

    scale1 = min(target_width / img1_w, target_height / img1_h)
    scale2 = min(target_width / img2_w, target_height / img2_h)
    scale = min(scale1, scale2)

    scaled_w = int(round(img1_w * scale))
    scaled_h = int(round(img1_h * scale))

    return scaled_w, scaled_h
