from __future__ import annotations

from engine.cache.tile_coverage import intersection_rect, rects_overlap
from engine.cache.tile_geometry import (
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
    "best_tile_overlap_index",
    "iter_visible_side_tiles",
    "resolve_side_visible_rect",
]

# Full-image fraction rect for a side with no registered grid (1x1
# degenerate case) -- same value as rhi_renderer/uniforms._FULL_TILE_RECT,
# duplicated as a literal so this shared module never imports the renderer.
_FULL_TILE_RECT = (0.0, 0.0, 1.0, 1.0)


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


def resolve_side_visible_rect(
    base_image,
    letterbox,
    grid,
    *,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
    capture_uv_rect: tuple[float, float, float, float] | None = None,
) -> tuple[float, float, float, float]:
    """One side's visible rect in its own grid pixel space -- the single
    derivation shared by the residency pass (``ResidencySpec.visible_rect``)
    and the draw-plan pass (visible-tile enumeration), so "what's uploaded"
    and "what's drawn" can't diverge (see "Summary of the invariant" in
    docs/dev/rendering/tile-rendering-system.md).

    ``capture_uv_rect`` overrides the viewport-derived rect with an explicit
    ``(left, top, right, bottom)`` fraction of the target key's own full
    image, bypassing letterbox mapping entirely (magnifier ``source_*``
    realize call -- the overlay's uv_rect is already in native 0..1 space).
    ``None`` (the base-canvas case) keeps the letterbox-mapped derivation."""
    if capture_uv_rect is not None:
        cap_left, cap_top, cap_right, cap_bottom = capture_uv_rect
        return (
            cap_left * grid.total_width,
            cap_top * grid.total_height,
            cap_right * grid.total_width,
            cap_bottom * grid.total_height,
        )
    return _visible_side_image_rect(
        base_image,
        letterbox,
        grid,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )


def iter_visible_side_tiles(
    tile_service,
    key: object,
    letterbox: tuple[float, float, float, float],
    base_image,
    *,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> list[tuple[object, tuple[float, float, float, float], tuple[int, int]]]:
    """Every visible tile of one side as ``(key, apron-padded rect, (row,
    col))`` -- the tab-side tile enumeration both the draw plan (pairing
    loop) and residency-spec resolution agree on. The grid/visibility
    decision itself stays with ``TileTextureService`` (engine decides);
    this only translates the visible set into per-tile rects. A side with
    no registered grid contributes its single whole-image entry, so the
    untiled case flows through the same code path with a degenerate
    one-element list.

    Residency filtering (``slot_for(...) is not None``) is deliberately
    NOT done here -- mirroring multi_compare's ``build_slot_array_tiles``,
    which returns every tile the viewport wants regardless of upload
    status, so the draw plan's own pairing loop stays the single place
    that filters to actually-resident tiles (pinned by
    tests/contracts/test_coverage_uses_slot_for.py)."""
    grid = tile_service.grid_for(key)
    if grid is None:
        return [(key, _FULL_TILE_RECT, (0, 0))]
    visible_rect = resolve_side_visible_rect(
        base_image,
        letterbox,
        grid,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    visible_indices = tile_service.visible_tiles(key, visible_rect)
    side_tiles = []
    for row, col, region in grid.iter_regions():
        if (row, col) not in visible_indices:
            continue
        left, top, right, bottom = _apron_rect(
            grid.total_width, grid.total_height, region, _TILE_APRON_PX
        )
        rect = (
            left / grid.total_width,
            top / grid.total_height,
            (right - left) / grid.total_width,
            (bottom - top) / grid.total_height,
        )
        side_tiles.append((key, rect, (row, col)))
    return side_tiles


def best_tile_overlap_index(grid, rect: tuple[float, float, float, float]) -> tuple[int, int] | None:
    """Best-pixel-overlap tile pick for an image-fraction ``rect``: returns
    the ``(row, col)`` whose region overlaps ``rect`` by the largest pixel
    area. Shared core of the diff-tile resolution (the diff overlay has one
    sampler slot and reuses image1's tile rect to sample it). Exact whenever
    the diff grid and image1's live grid match (steady state); approximate
    only during transient pan/zoom display downscaling (cosmetic)."""
    left_f, top_f, width_f, height_f = rect
    left = left_f * grid.total_width
    top = top_f * grid.total_height
    right = (left_f + width_f) * grid.total_width
    bottom = (top_f + height_f) * grid.total_height
    query = (left, top, right - left, bottom - top)
    best_index = None
    best_overlap = -1.0
    for row, col, region in grid.iter_regions():
        candidate = (
            region.left,
            region.top,
            region.right - region.left,
            region.bottom - region.top,
        )
        if rects_overlap(query, candidate):
            _, _, overlap_w, overlap_h = intersection_rect(query, candidate)
            overlap = overlap_w * overlap_h
        else:
            # Zero-area touch (or no touch at all): same 0.0 the inline
            # max(0, ...) form produced, so degenerate rects keep picking
            # the first iterated region instead of returning None.
            overlap = 0.0
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = (row, col)
    return best_index
