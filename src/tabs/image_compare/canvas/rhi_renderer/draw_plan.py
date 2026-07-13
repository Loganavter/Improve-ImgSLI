from __future__ import annotations

from dataclasses import dataclass

from shared.rendering.tile_texture_service import TileTextureService

from ..texture_parts.tile_geometry import _apron_rect, _TILE_APRON_PX, _visible_side_image_rect
from .uniforms import _FULL_TILE_RECT


@dataclass(frozen=True)
class DrawItem:
    key1: object
    rect1: tuple[float, float, float, float]
    key2: object
    rect2: tuple[float, float, float, float]
    diff_key: object
    sampler_name: str


def _visible_tile_pairs(
    tile_service: TileTextureService,
    texture_keys: tuple[object, object],
    base_image,
    *,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> list[
    tuple[
        object,
        tuple[float, float, float, float],
        object,
        tuple[float, float, float, float],
    ]
]:
    """Returns every (image1 tile key, image1 tile rect, image2 tile key,
    image2 tile rect) combination that needs a draw call this frame.
    Grid/tile-key bookkeeping comes from ``tile_service``; for a multi-tile
    grid, only tiles intersecting the current viewport (docs/dev/
    TILED_RENDERING_DESIGN.md Phase 2 — same visible-rect computation
    ``resources.py``'s residency pass uses, so what's selected here is
    guaranteed already GPU-resident) are included, not the whole grid. Each
    rect is the tile's ``_TILE_APRON_PX``-padded region as (left, top,
    width, height) fractions of that side's total image size, matching both
    the shader's tileRect1/tileRect2 uniforms and the actual pixel bounds of
    the uploaded texture.

    ``viewport_zoom``/``viewport_offset``: see ``pack_base_uniforms`` (Phase
    3 tiled export)."""
    letterboxes = (tuple(base_image.letterbox1), tuple(base_image.letterbox2))
    tiles_by_side: list[list[tuple[object, tuple[float, float, float, float]]]] = []
    for key, letterbox in zip(texture_keys, letterboxes):
        grid = tile_service.grid_for(key)
        if grid is None:
            tiles_by_side.append([(key, _FULL_TILE_RECT)])
            continue
        if grid.rows == 1 and grid.columns == 1:
            tiles_by_side.append([(tile_service.tile_key(key, 0, 0), _FULL_TILE_RECT)])
            continue
        visible_rect = _visible_side_image_rect(
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
            tile_key = tile_service.tile_key(key, row, col)
            rect = (
                left / grid.total_width,
                top / grid.total_height,
                (right - left) / grid.total_width,
                (bottom - top) / grid.total_height,
            )
            side_tiles.append((tile_key, rect))
        tiles_by_side.append(side_tiles or [(key, _FULL_TILE_RECT)])
    pairs = []
    for key1, rect1 in tiles_by_side[0]:
        for key2, rect2 in tiles_by_side[1]:
            pairs.append((key1, rect1, key2, rect2))
    return pairs


def _resolve_diff_tile_key(
    tile_service: TileTextureService,
    diff_key: object,
    rect1: tuple[float, float, float, float],
) -> object:
    """Picks which diff-texture tile a draw call binds for image1's
    ``tileRect1`` window (docs/dev/TILED_RENDERING_DESIGN.md Phase 4).

    The shader has exactly one diff sampler slot and reuses tileRect1 to
    sample it, so this must return one tile even when several overlap.
    ``rect1`` is normalized fractions of image1's own space; applied to the
    diff grid's own total dimensions this is exact whenever the diff and
    image1 grids match — the steady-state case, since diff is built from the
    same full-res source image1 draws at rest. It degrades to a
    best-pixel-overlap pick (not necessarily exact) only while image1's
    *display* texture is transiently downscaled for interactive pan/zoom
    smoothing and simultaneously both it and the diff exceed one tile — a
    narrow, cosmetic-only edge case, not a crash/blank-texture bug like the
    untiled diff path had."""
    grid = tile_service.grid_for(diff_key)
    if grid is None:
        return diff_key
    if grid.rows == 1 and grid.columns == 1:
        return tile_service.tile_key(diff_key, 0, 0)
    left_f, top_f, width_f, height_f = rect1
    left = left_f * grid.total_width
    top = top_f * grid.total_height
    right = (left_f + width_f) * grid.total_width
    bottom = (top_f + height_f) * grid.total_height
    best_index = None
    best_overlap = -1.0
    for row, col, region in grid.iter_regions():
        overlap_w = max(0.0, min(right, region.right) - max(left, region.left))
        overlap_h = max(0.0, min(bottom, region.bottom) - max(top, region.top))
        overlap = overlap_w * overlap_h
        if overlap > best_overlap:
            best_overlap = overlap
            best_index = (row, col)
    if best_index is None:
        return diff_key
    return tile_service.tile_key(diff_key, *best_index)


def build_draw_plan(
    tile_service: TileTextureService,
    texture_keys: tuple[object, object],
    base_image,
    *,
    diff_key: object | None,
    sampler_name: str,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> list[DrawItem]:
    """Replaces ``_visible_tile_pairs`` + ``_resolve_diff_tile_key``
    composition. Queries ``tile_service`` for geometry only -- never touches
    a renderer's live GPU texture dict, since draw-plan construction must
    not depend on which GPU textures happen to exist yet (that dependency is
    exactly what let residency and drawing silently disagree before)."""
    pairs = _visible_tile_pairs(
        tile_service,
        texture_keys,
        base_image,
        viewport_zoom=viewport_zoom,
        viewport_offset=viewport_offset,
    )
    return [
        DrawItem(
            key1=key1,
            rect1=rect1,
            key2=key2,
            rect2=rect2,
            diff_key=(
                _resolve_diff_tile_key(tile_service, diff_key, rect1)
                if diff_key is not None
                else "placeholder"
            ),
            sampler_name=sampler_name,
        )
        for key1, rect1, key2, rect2 in pairs
    ]
