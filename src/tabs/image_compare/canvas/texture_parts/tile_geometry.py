from __future__ import annotations

# 1px of real neighboring source pixels duplicated on every tile edge so
# bilinear filtering at a tile boundary samples true neighbor data instead
# of ClampToEdge-repeating its own edge texel (which would show as a seam).
# tileRect1/tileRect2 describe this padded region, not the bare grid cell,
# so the shader's tileUV mapping (base.frag) stays a plain 0..1 span over
# whatever the texture actually contains.
_TILE_APRON_PX = 1
# Extra ring of tiles kept GPU-resident beyond what's strictly visible this
# frame, so a one-tile pan/zoom nudge doesn't immediately re-crop/re-upload
# from the CPU-side cached QImage next frame.
_TILE_RESIDENCY_MARGIN = 1


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


def _apron_rect(
    total_width: int, total_height: int, region, apron: int
) -> tuple[int, int, int, int]:
    left = max(0, region.left - apron)
    top = max(0, region.top - apron)
    right = min(total_width, region.right + apron)
    bottom = min(total_height, region.bottom + apron)
    return left, top, right, bottom


def _tile_indices_with_margin(grid, visible_indices, margin: int) -> set[tuple[int, int]]:
    target: set[tuple[int, int]] = set()
    for row, col in visible_indices:
        for delta_row in range(-margin, margin + 1):
            for delta_col in range(-margin, margin + 1):
                candidate_row = row + delta_row
                candidate_col = col + delta_col
                if 0 <= candidate_row < grid.rows and 0 <= candidate_col < grid.columns:
                    target.add((candidate_row, candidate_col))
    return target


def _viewport_zoom_offset_for_tile(
    canvas_width: int,
    canvas_height: int,
    tile_rect: tuple[float, float, float, float],
    base_zoom: tuple[float, float] = (1.0, 1.0),
    base_offset: tuple[float, float] = (0.0, 0.0),
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Derive the (anisotropic) zoom/offset pair that makes base.frag's
    ``uv = (vTexCoord - 0.5) / zoom + 0.5 - offset`` show exactly the same
    image content as the untiled ``base_zoom``/``base_offset`` shader would
    show at ``tile_rect`` (left, top, right, bottom, in canvas pixels), when
    rendered into a ``(tile_rect width x height)``-sized viewport (docs/dev/
    TILED_RENDERING_DESIGN.md Phase 3 tiled export).

    Composed, not a bare canvas-px-to-uv mapping: substituting the tile's
    local ``vTexCoord in [0,1]`` for the untiled shader's global one and
    solving for an equivalent single-tile zoom/offset gives, per axis,
    ``zoom_tile = base_zoom / tile_width_fraction`` and ``offset_tile =
    base_offset - (tile_center_fraction - 0.5) / base_zoom``. This makes the
    function an exact no-op (returns ``base_zoom``/``base_offset``
    unchanged) when ``tile_rect`` covers the whole canvas — required so
    passing it unconditionally in ``render()`` doesn't perturb the
    non-tiled/live-preview/zoom-preserving export path."""
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
