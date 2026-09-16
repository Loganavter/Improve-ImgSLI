"""Централизованная логика скейлинга bbox — оригинал ↔ превью."""
from __future__ import annotations

from .model import CropBox


def get_scaled_box_for_thumb(
    orig_box: CropBox | tuple[int, int, int, int] | None,
    orig_size: tuple[int, int],
    thumb_size: tuple[int, int],
) -> CropBox | None:
    """Отмасштабировать orig_box из orig_size в thumb_size с консистентным округлением.

    Логика 1:1 с бывшим autocrop_service.get_scaled_box_for_thumb — round на
    каждом шаге, clamp, фильтр полного кадра → None.
    """
    if orig_box is None:
        return None
    if isinstance(orig_box, CropBox):
        l, t, r, b = orig_box.left, orig_box.top, orig_box.right, orig_box.bottom
    else:
        l, t, r, b = orig_box
    orig_w, orig_h = orig_size
    thumb_w, thumb_h = thumb_size
    if orig_w <= 0 or orig_h <= 0 or thumb_w <= 0 or thumb_h <= 0:
        return None
    scale_w = thumb_w / float(orig_w)
    scale_h = thumb_h / float(orig_h)
    left = max(0, int(round(l * scale_w)))
    top = max(0, int(round(t * scale_h)))
    right = min(thumb_w, max(left + 1, int(round(r * scale_w))))
    bottom = min(thumb_h, max(top + 1, int(round(b * scale_h))))
    if (left, top, right, bottom) == (0, 0, thumb_w, thumb_h):
        return None
    return CropBox(left, top, right, bottom)
