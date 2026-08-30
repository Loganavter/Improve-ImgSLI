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


def scale_box_to_original(
    probe_box: CropBox,
    orig_size: tuple[int, int],
    probe_size: tuple[int, int],
) -> CropBox | None:
    """Обратный скейл probe_box → оригинальные координаты (для зонда)."""
    if probe_box is None:
        return None
    orig_w, orig_h = orig_size
    probe_w, probe_h = probe_size
    if orig_w <= 0 or orig_h <= 0 or probe_w <= 0 or probe_h <= 0:
        return None
    # probe создан через NEAREST с scale = probe_max / max(orig)
    scale_w = probe_w / float(orig_w)
    scale_h = probe_h / float(orig_h)
    # Используем обратный скейл как в _auto_crop_box_scaled (1/scale)
    inv_w = 1.0 / scale_w if scale_w else 1.0
    inv_h = 1.0 / scale_h if scale_h else 1.0
    # Но для квадратных скейлов достаточно одной величины; берём инверсию по
    # каждой оси отдельно для корректности неквадратных кейсов.
    left = max(0, int(probe_box.left * inv_w))
    top = max(0, int(probe_box.top * inv_h))
    right = min(orig_w, max(left + 1, int(round(probe_box.right * inv_w))))
    bottom = min(orig_h, max(top + 1, int(round(probe_box.bottom * inv_h))))
    if (left, top, right, bottom) == (0, 0, orig_w, orig_h):
        return None
    return CropBox(left, top, right, bottom)
