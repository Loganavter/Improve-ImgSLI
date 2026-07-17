from __future__ import annotations

from shared.rendering.tile_geometry import (
    _TILE_APRON_PX,
    _TILE_RESIDENCY_MARGIN,
    _apron_rect,
    viewport_zoom_offset_for_tile as _viewport_zoom_offset_for_tile,
)

__all__ = [
    "_apron_rect",
    "_TILE_APRON_PX",
    "_TILE_RESIDENCY_MARGIN",
    "_viewport_zoom_offset_for_tile",
    "_visible_side_image_rect",
]


def _visible_side_image_rect(
    base_image,
    letterbox,
    grid,
    *,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> tuple[float, float, float, float]:
    """Mirrors base.frag's uv/sampleUV derivation (center, zoom, offset, then
    per-side letterbox) to compute the currently-visible rect in this side's
    tile-grid pixel space. Must stay numerically identical to the shader's
    math, or viewport-driven tile selection (docs/dev/
    TILED_RENDERING_DESIGN.md Phase 2) diverges from what's actually drawn,
    showing stale/missing tiles at zoom/pan boundaries. Split position is
    deliberately not applied here — both sides always see the same uv range
    regardless of which one the split shows, matching the existing N1xN2
    pairwise draw loop that doesn't cull by split either.

    ``viewport_zoom``/``viewport_offset`` mirror ``pack_base_uniforms``'s
    same-named parameters — pass the tiled-export per-tile values here too,
    or both stay ``None`` for the live scalar-zoom case."""
    zoom_x, zoom_y = viewport_zoom or (
        float(base_image.zoom) or 1.0,
        float(base_image.zoom) or 1.0,
    )
    offset_x, offset_y = viewport_offset or (
        float(base_image.pan_offset_x),
        float(base_image.pan_offset_y),
    )
    uv_left = -0.5 / zoom_x + 0.5 - offset_x
    uv_right = 0.5 / zoom_x + 0.5 - offset_x
    uv_top = -0.5 / zoom_y + 0.5 - offset_y
    uv_bottom = 0.5 / zoom_y + 0.5 - offset_y
    lb_x, lb_y, lb_w, lb_h = letterbox
    lb_w = lb_w if lb_w else 1.0
    lb_h = lb_h if lb_h else 1.0
    sample_left = (uv_left - lb_x) / lb_w
    sample_right = (uv_right - lb_x) / lb_w
    sample_top = (uv_top - lb_y) / lb_h
    sample_bottom = (uv_bottom - lb_y) / lb_h
    left = max(0.0, min(1.0, sample_left))
    right = max(0.0, min(1.0, sample_right))
    top = max(0.0, min(1.0, sample_top))
    bottom = max(0.0, min(1.0, sample_bottom))
    return (
        left * grid.total_width,
        top * grid.total_height,
        right * grid.total_width,
        bottom * grid.total_height,
    )
