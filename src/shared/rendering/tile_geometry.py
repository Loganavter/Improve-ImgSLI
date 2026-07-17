from __future__ import annotations

# 1px of real neighboring source pixels duplicated on every tile edge so
# bilinear filtering at a tile boundary samples true neighbor data instead
# of ClampToEdge-repeating its own edge texel (which would show as a seam).
# Any canvas that composites multiple GPU tiles into one continuous image
# (the compare tabs, ...) needs this same apron, so it lives here rather
# than under one tab.
_TILE_APRON_PX = 1
# Extra ring of tiles kept GPU-resident beyond what's strictly visible this
# frame, so a one-tile pan/zoom nudge doesn't immediately re-crop/re-upload
# from the CPU-side cached image next frame.
_TILE_RESIDENCY_MARGIN = 1


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
    """Zoom/offset for rendering one export tile (see image_compare export path)."""
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
    """Crop a tile region with apron from TiledPixelStore or PIL-like source."""
    if hasattr(pixel_store, "crop_apron_rect"):
        return pixel_store.crop_apron_rect(left, top, right, bottom, apron=apron)
    w, h = pixel_store.size
    al = max(0, left - apron)
    at = max(0, top - apron)
    ar = min(w, right + apron)
    ab = min(h, bottom + apron)
    return pixel_store.crop((al, at, ar, ab))
