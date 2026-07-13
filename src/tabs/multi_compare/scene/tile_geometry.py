"""Per-slot tiling geometry for Multi Compare's ``BaseImagesPass``.

Mirrors image_compare's ``rhi_renderer/draw_plan.py`` (visible-tile-pairs +
tile-rect resolution), simplified for multi_compare's single-image-per-slot
model: no letterbox/split, just ``multi_compare.frag``'s own
``uv = (TexCoord-0.5)/fitScale + 0.5; uv = (uv-0.5)/zoom + 0.5 - panOffset``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.rendering.tile_geometry import _apron_rect, _TILE_APRON_PX
from shared.rendering.tile_texture_service import TileTextureService

_FULL_TILE_RECT = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class SlotDrawItem:
    tile_key: object
    tile_rect: tuple[float, float, float, float]


def _visible_slot_image_rect(
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
    grid,
) -> tuple[float, float, float, float]:
    """Mirrors ``multi_compare.frag``'s uv derivation to compute the
    currently-visible rect in this slot's tile-grid pixel space. Must stay
    numerically identical to the shader's math, or viewport-driven tile
    selection diverges from what's actually drawn."""
    zoom = zoom or 1.0
    fit_x = fit_scale[0] or 1.0
    fit_y = fit_scale[1] or 1.0
    pan_x, pan_y = pan_offset
    uv_left = -0.5 / (fit_x * zoom) + 0.5 - pan_x
    uv_right = 0.5 / (fit_x * zoom) + 0.5 - pan_x
    uv_top = -0.5 / (fit_y * zoom) + 0.5 - pan_y
    uv_bottom = 0.5 / (fit_y * zoom) + 0.5 - pan_y
    left = max(0.0, min(1.0, uv_left))
    right = max(0.0, min(1.0, uv_right))
    top = max(0.0, min(1.0, uv_top))
    bottom = max(0.0, min(1.0, uv_bottom))
    return (
        left * grid.total_width,
        top * grid.total_height,
        right * grid.total_width,
        bottom * grid.total_height,
    )


def build_slot_draw_plan(
    tile_service: TileTextureService,
    slot_id: object,
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
) -> list[SlotDrawItem]:
    """Every tile this slot needs a draw call for this frame, each carrying
    its own ``tileRect`` (that tile's ``_TILE_APRON_PX``-padded region, as
    (left, top, width, height) fractions of the slot's total image size).
    A slot that fits within one GPU texture (the common case) always
    returns exactly one item with the identity rect."""
    grid = tile_service.grid_for(slot_id)
    if grid is None:
        return [SlotDrawItem(slot_id, _FULL_TILE_RECT)]
    if grid.rows == 1 and grid.columns == 1:
        return [SlotDrawItem(tile_service.tile_key(slot_id, 0, 0), _FULL_TILE_RECT)]
    visible_rect = _visible_slot_image_rect(pan_offset, fit_scale, zoom, grid)
    visible_indices = tile_service.visible_tiles(slot_id, visible_rect)
    items: list[SlotDrawItem] = []
    for row, col, region in grid.iter_regions():
        if (row, col) not in visible_indices:
            continue
        left, top, right, bottom = _apron_rect(
            grid.total_width, grid.total_height, region, _TILE_APRON_PX
        )
        tile_key = tile_service.tile_key(slot_id, row, col)
        rect = (
            left / grid.total_width,
            top / grid.total_height,
            (right - left) / grid.total_width,
            (bottom - top) / grid.total_height,
        )
        items.append(SlotDrawItem(tile_key, rect))
    return items or [SlotDrawItem(slot_id, _FULL_TILE_RECT)]
