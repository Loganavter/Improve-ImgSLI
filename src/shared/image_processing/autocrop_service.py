"""Centralized auto-crop service — single source of truth for bounding box.

All decode paths (preview QImage ≤1024, full TiledPixelStore memmap, thumbnail)
must use the same bbox. Previously the bbox was computed in 3 places:
- tiled_pixel_store.get_cached_crop_box (PIL 1024 probe, thr15 only)
- progressive_loader JXL/QImage branches (direct crop_black_borders on preview)
- loading.py post-unify recrop (thr15→thr30 on 2797 unified store)

This service owns the cache and the thr15→thr30 fallback policy, so unify
never mutates size.

Audit-Meta: pattern=collaborator reason="owns _crop_box_cache state, single bbox per path"
"""
from __future__ import annotations

import os

from shared.image_processing.tiled_pixel_store import get_cached_crop_box as _get_cached


def get_crop_box(path_str: str) -> tuple[int, int, int, int] | None:
    """Return bbox or None, trying thr15 then thr30 on the 1024 probe.

    The probe is bounded (1024 longest), so the thr30 fallback fixes the
    764→2797 Lanczos dark edge without a post-unify resize. Result is cached
    per threshold in tiled_pixel_store._crop_box_cache; this wrapper just
    tries both thresholds atomically.
    """
    box = _get_cached(path_str, threshold=15)
    if box is not None:
        return box
    return _get_cached(path_str, threshold=30)


def get_scaled_box_for_thumb(
    orig_box: tuple[int, int, int, int] | None,
    orig_size: tuple[int, int],
    thumb_size: tuple[int, int],
) -> tuple[int, int, int, int] | None:
    """Scale orig_box from orig_size to thumb_size with rounding consistent with load Preview."""
    if orig_box is None:
        return None
    orig_w, orig_h = orig_size
    thumb_w, thumb_h = thumb_size
    if orig_w <= 0 or orig_h <= 0 or thumb_w <= 0 or thumb_h <= 0:
        return None
    scale_w = thumb_w / float(orig_w)
    scale_h = thumb_h / float(orig_h)
    l, t, r, b = orig_box
    left = max(0, int(round(l * scale_w)))
    top = max(0, int(round(t * scale_h)))
    right = min(thumb_w, max(left + 1, int(round(r * scale_w))))
    bottom = min(thumb_h, max(top + 1, int(round(b * scale_h))))
    if (left, top, right, bottom) == (0, 0, thumb_w, thumb_h):
        return None
    return (left, top, right, bottom)


def invalidate(path: str | None = None) -> None:
    """Clear cache for path or all."""
    try:
        from shared.image_processing.tiled_pixel_store import _crop_box_cache
    except Exception:
        return
    if path is None:
        _crop_box_cache.clear()
        return
    for thr in (15, 30):
        _crop_box_cache.pop(f"{path}:{thr}", None)
        _crop_box_cache.pop(f"{os.fspath(path)}:{thr}", None)


def invalidate_all() -> None:
    invalidate(None)
