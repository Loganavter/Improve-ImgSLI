from __future__ import annotations

from .tile_constants import TILE_APRON_PX, TILE_RESIDENCY_MARGIN

_TILE_APRON_PX = TILE_APRON_PX
_TILE_RESIDENCY_MARGIN = TILE_RESIDENCY_MARGIN


def _apron_rect(
    total_width: int, total_height: int, region, apron: int = _TILE_APRON_PX
) -> tuple[int, int, int, int]:
    left = max(0, region.left - apron)
    top = max(0, region.top - apron)
    right = min(total_width, region.right + apron)
    bottom = min(total_height, region.bottom + apron)
    return left, top, right, bottom


def viewport_zoom_offset_for_tile(
    canvas_width: int,
    canvas_height: int,
    tile_rect: tuple[float, float, float, float],
    base_zoom: tuple[float, float] = (1.0, 1.0),
    base_offset: tuple[float, float] = (0.0, 0.0),
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Zoom/offset for rendering one export tile (see tab export tiling path)."""
    left, top, right, bottom = tile_rect
    canvas_width = max(1, canvas_width)
    canvas_height = max(1, canvas_height)
    left_n, right_n = left / canvas_width, right / canvas_width
    top_n, bottom_n = top / canvas_height, bottom / canvas_height
    tile_w_frac = max(1e-9, right_n - left_n)
    tile_h_frac = max(1e-9, bottom_n - top_n)
    center_x = left_n + 0.5 * tile_w_frac
    center_y = top_n + 0.5 * tile_h_frac
    base_zoom_x = base_zoom[0] or 1.0
    base_zoom_y = base_zoom[1] or 1.0
    zoom_x = base_zoom_x / tile_w_frac
    zoom_y = base_zoom_y / tile_h_frac
    offset_x = base_offset[0] - (center_x - 0.5) / base_zoom_x
    offset_y = base_offset[1] - (center_y - 0.5) / base_zoom_y
    return (zoom_x, zoom_y), (offset_x, offset_y)


def crop_apron_tile(pixel_store, left: int, top: int, right: int, bottom: int, apron: int = _TILE_APRON_PX):
    """Crop a tile region with apron from a TiledPixelStore, QImage, or PIL-like source.

    TiledPixelStore and QImage go through ``qimage_from_pixel_source``'s
    type-specific fast paths (numpy memmap view / ``QImage.copy``) and
    return a ``QImage`` directly -- this is a per-frame hot path (one call
    per visible tile), so every canvas tab shares this single
    implementation instead of keeping its own inline copy. Anything else
    (plain PIL-like sources) falls back to generic ``.size``/``.crop()``.
    """
    from PySide6.QtGui import QImage

    from shared.image_processing.tiled_pixel_store import (
        TiledPixelStore,
        pixel_source_size,
        qimage_from_pixel_source,
    )

    if isinstance(pixel_store, (TiledPixelStore, QImage)):
        w, h = pixel_source_size(pixel_store)
        al = max(0, left - apron)
        at = max(0, top - apron)
        ar = min(w, right + apron)
        ab = min(h, bottom + apron)
        return qimage_from_pixel_source(pixel_store, (al, at, ar, ab))
    w, h = pixel_store.size
    al = max(0, left - apron)
    at = max(0, top - apron)
    ar = min(w, right + apron)
    ab = min(h, bottom + apron)
    return pixel_store.crop((al, at, ar, ab))
