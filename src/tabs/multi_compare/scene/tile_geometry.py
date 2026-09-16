"""Per-slot tiling geometry for Multi Compare's ``BaseImagesPass``.

Thin adapters over ``engine.cache.draw_plans`` (which owns all visible-
rect/apron/coverage math on engine types): this module only converts
engine plan structs to the tab's item classes. No coverage or geometry
math remains here.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.cache import draw_plans as _engine_draw_plans
from engine.cache.draw_plans import FULL_TILE_RECT
from engine.cache.tile_texture_service import TileTextureService


@dataclass(frozen=True)
class SlotDrawItem:
    tile_key: object
    tile_rect: tuple[float, float, float, float]


@dataclass(frozen=True)
class SlotArrayTile:
    """One (row, col) tile of a slot, for the texture-array instanced draw
    path (docs/dev/rendering/tile-array-atlas-plan.md Phase 4). Carries the
    tile's own grid index (needed to look up its array slot/content-scale
    via ``TileTextureService.slot_for``/``content_size_for``) instead of a
    resolved GPU texture key like ``SlotDrawItem``."""

    tile_rect: tuple[float, float, float, float]
    index: tuple[int, int]


def _visible_slot_image_rect(
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
    grid,
) -> tuple[float, float, float, float]:
    """Thin adapter over the engine visible-rect derivation (kept under
    this name for the residency-spec pass, which shares the exact same
    viewport math the draw plan enumerates from)."""
    return _engine_draw_plans.slot_visible_rect(pan_offset, fit_scale, zoom, grid)


def build_slot_draw_plan(
    tile_service: TileTextureService,
    slot_id: object,
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
) -> list[SlotDrawItem]:
    """Every tile this slot needs a draw call for this frame, each carrying
    its own ``tileRect`` (that tile's apron-padded region, as (left, top,
    width, height) fractions of the slot's total image size). A slot that
    fits within one GPU texture (the common case) always returns exactly
    one item with the identity rect. Thin adapter: enumeration math lives
    in the engine builder; this only resolves GPU texture keys."""
    grid = tile_service.grid_for(slot_id)
    if grid is None:
        return [SlotDrawItem(slot_id, FULL_TILE_RECT)]
    tiles = _engine_draw_plans.build_slot_plan_tiles(
        tile_service, slot_id, pan_offset, fit_scale, zoom
    )
    items = [
        SlotDrawItem(tile_service.tile_key(slot_id, row, col), tile.rect)
        for tile in tiles
        for row, col in [tile.index]
    ]
    return items or [SlotDrawItem(slot_id, FULL_TILE_RECT)]


def build_slot_array_tiles(
    tile_service: TileTextureService,
    slot_id: object,
    pan_offset: tuple[float, float],
    fit_scale: tuple[float, float],
    zoom: float,
) -> list[SlotArrayTile]:
    """Array-path counterpart of ``build_slot_draw_plan``: every visible
    tile's own ``(row, col)`` index, needed to resolve its array slot/
    content-scale, resolved instead of a GPU texture key. Unlike
    ``build_slot_draw_plan``, never takes the 1x1-grid shortcut -- an
    array-path frame uploads a still-1x1 slot into the array too, since
    every slot's tiles this frame end up in the same shared instanced draw.
    Thin adapter: enumeration math lives in the engine builder."""
    tiles = _engine_draw_plans.build_slot_plan_tiles(
        tile_service, slot_id, pan_offset, fit_scale, zoom
    )
    return [SlotArrayTile(tile.rect, tile.index) for tile in tiles]


def drop_covered_fallback_tiles(
    fallback_tiles: list[SlotArrayTile],
    current_tiles: list[SlotArrayTile],
) -> list[SlotArrayTile]:
    """Drops fallback-LOD tiles whose footprint is already fully covered by
    the current level's (possibly partial) tile set (docs/dev/rendering/
    tile-array-atlas-plan.md Phase 9, mirrors the fixed-pair render tab's
    pair-based drop, simplified for the single-image-per-slot model): tile
    rects are already fractions of the slot's own image with no letterbox
    to map through, and every pyramid level of the same base image shares
    that same 0..1 fraction space, so a fallback tile's rect and a current
    tile's rect are directly comparable with no coordinate transform needed.

    Thin adapter over the engine rect-level drop (which applies the
    per-tile ``covered_fraction`` math at ``FALLBACK_COVERAGE_THRESHOLD``):
    rect adaptation happens here, coverage math lives in the engine."""
    kept_indices = _engine_draw_plans.drop_covered_fallback_tiles(
        [tile.tile_rect for tile in fallback_tiles],
        [tile.tile_rect for tile in current_tiles],
    )
    return [fallback_tiles[index] for index in kept_indices]
