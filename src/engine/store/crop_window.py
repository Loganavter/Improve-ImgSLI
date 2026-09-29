"""Parametric-crop box math — pure helpers, no Qt, no tabs (engine seal).

The crop window is always expressed in full-frame source px, half-open
``(left, top, right, bottom)`` — the same convention as
``TiledPixelStore.read_array`` and ``CropBox.to_tuple`` — so render passes
can intersect their read boxes directly without converting conventions.
"""

from __future__ import annotations

import operator


def _as_box(box) -> tuple[int, int, int, int] | None:
    try:
        left, top, right, bottom = (operator.index(v) for v in box)
    except Exception:
        return None
    return (int(left), int(top), int(right), int(bottom))


def intersect_box(
    box: tuple[int, int, int, int],
    crop: tuple[int, int, int, int] | None,
) -> tuple[int, int, int, int] | None:
    """Intersect a read ``box`` with the crop window (fail-closed).

    ``None`` crop = passthrough (normalized copy of ``box``). Empty or
    inverted intersections yield ``None`` (gap) — never a degenerate box
    that could sample neighbor bytes. Malformed input yields ``None``.
    """
    want = _as_box(box)
    if want is None:
        return None
    if crop is None:
        return want
    window = _as_box(crop)
    if window is None:
        return None
    left = max(want[0], window[0])
    top = max(want[1], window[1])
    right = min(want[2], window[2])
    bottom = min(want[3], window[3])
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def crop_view_size(
    full_size: tuple[int, int],
    crop: tuple[int, int, int, int] | None,
) -> tuple[int, int]:
    """Reported ``(width, height)`` for a source under ``crop``.

    ``None`` crop (or a crop covering nothing usable) falls back to the
    full size / ``(0, 0)`` respectively — callers treat ``(0, 0)`` as
    imageless, mirroring ``pixel_source_size`` conventions.
    """
    try:
        full_w, full_h = int(full_size[0]), int(full_size[1])
    except Exception:
        return (0, 0)
    if crop is None:
        return (max(0, full_w), max(0, full_h))
    window = _as_box(crop)
    if window is None:
        return (max(0, full_w), max(0, full_h))
    left = min(max(window[0], 0), full_w)
    top = min(max(window[1], 0), full_h)
    right = min(max(window[2], 0), full_w)
    bottom = min(max(window[3], 0), full_h)
    return (max(0, right - left), max(0, bottom - top))
