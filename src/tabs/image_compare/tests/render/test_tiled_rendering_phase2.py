"""Phase 2 viewport-driven tiling geometry (docs/dev/TILED_RENDERING_DESIGN.md)."""

from types import SimpleNamespace

import pytest

from shared.image_processing.regions import build_uniform_tile_grid
from tabs.image_compare.canvas.rhi_renderer import (
    _apron_rect,
    _TILE_APRON_PX,
    _tile_indices_with_margin,
    _TILE_CACHE_BUDGET_BYTES,
    _visible_side_image_rect,
)
from tabs.image_compare.canvas.texture_parts.tile_texture_service import (
    TileTextureService,
)


def _grid():
    return build_uniform_tile_grid(6000, 4000, max_tile_width=2048)


def test_visible_side_image_rect_full_view_at_zoom_one():
    grid = _grid()
    base = SimpleNamespace(zoom=1.0, pan_offset_x=0.0, pan_offset_y=0.0)

    rect = _visible_side_image_rect(base, (0.0, 0.0, 1.0, 1.0), grid)

    assert rect == pytest.approx((0.0, 0.0, 6000.0, 4000.0))


def test_visible_side_image_rect_zoomed_in_centers_on_middle():
    grid = _grid()
    base = SimpleNamespace(zoom=2.0, pan_offset_x=0.0, pan_offset_y=0.0)

    rect = _visible_side_image_rect(base, (0.0, 0.0, 1.0, 1.0), grid)

    assert rect == pytest.approx((1500.0, 1000.0, 4500.0, 3000.0))


def test_visible_side_image_rect_pan_shifts_window():
    grid = _grid()
    base = SimpleNamespace(zoom=2.0, pan_offset_x=0.1, pan_offset_y=0.0)

    rect = _visible_side_image_rect(base, (0.0, 0.0, 1.0, 1.0), grid)

    assert rect == pytest.approx((900.0, 1000.0, 3900.0, 3000.0))


def test_visible_side_image_rect_clamped_to_image_bounds():
    grid = _grid()
    base = SimpleNamespace(zoom=1.0, pan_offset_x=5.0, pan_offset_y=-5.0)

    rect = _visible_side_image_rect(base, (0.0, 0.0, 1.0, 1.0), grid)

    left, top, right, bottom = rect
    assert 0.0 <= left <= right <= grid.total_width
    assert 0.0 <= top <= bottom <= grid.total_height


def test_apron_rect_pads_and_clamps_at_image_edges():
    grid = _grid()
    regions = {(row, col): region for row, col, region in grid.iter_regions()}

    middle_column = _apron_rect(grid.total_width, grid.total_height, regions[(0, 1)], 1)
    assert middle_column[0] == regions[(0, 1)].left - 1
    assert middle_column[2] == regions[(0, 1)].right + 1

    top_left_corner = _apron_rect(grid.total_width, grid.total_height, regions[(0, 0)], 1)
    assert top_left_corner[0] == 0
    assert top_left_corner[1] == 0

    bottom_right_corner = _apron_rect(
        grid.total_width, grid.total_height, regions[(grid.rows - 1, grid.columns - 1)], 1
    )
    assert bottom_right_corner[2] == grid.total_width
    assert bottom_right_corner[3] == grid.total_height


def test_tile_indices_with_margin_includes_neighbor_ring():
    grid = _grid()

    target = _tile_indices_with_margin(grid, {(0, 1)}, 1)

    assert target == {(0, 0), (0, 1), (0, 2), (1, 0), (1, 1), (1, 2)}


def test_tile_indices_with_margin_clips_at_grid_edges():
    grid = _grid()

    target = _tile_indices_with_margin(grid, {(0, 0)}, 1)

    assert target == {(0, 0), (0, 1), (1, 0), (1, 1)}


def _service_with_resident_tiles(
    byte_size_per_tile: int, indices: list[tuple[int, int]]
) -> TileTextureService:
    service = TileTextureService(max_tile_extent=2048)
    service.register_source("side", (6000, 4000))
    for index in indices:
        service.mark_resident("side", index, byte_size_per_tile)
    return service


def test_evict_over_budget_noop_when_under_budget():
    service = _service_with_resident_tiles(1024, [(0, 0), (0, 1)])

    evicted = service.evict_over_budget(
        {"side": {(0, 0), (0, 1)}}, _TILE_CACHE_BUDGET_BYTES
    )

    assert evicted == []
    assert service.is_resident("side", (0, 0))
    assert service.is_resident("side", (0, 1))


def test_evict_over_budget_evicts_least_recently_used_first():
    per_tile = _TILE_CACHE_BUDGET_BYTES // 2 + 1
    service = _service_with_resident_tiles(per_tile, [(0, 0), (0, 1), (0, 2)])

    evicted = service.evict_over_budget({"side": set()}, _TILE_CACHE_BUDGET_BYTES)

    evicted_indices = {index for _source_id, index in evicted}
    assert (0, 0) in evicted_indices
    assert (0, 2) not in evicted_indices
    assert not service.is_resident("side", (0, 0))
    assert service.is_resident("side", (0, 2))


def test_evict_over_budget_never_evicts_protected_tiles_even_if_over_budget():
    per_tile = _TILE_CACHE_BUDGET_BYTES + 1
    service = _service_with_resident_tiles(per_tile, [(0, 0)])

    evicted = service.evict_over_budget({"side": {(0, 0)}}, _TILE_CACHE_BUDGET_BYTES)

    assert evicted == []
    assert service.is_resident("side", (0, 0))


def test_apron_rects_overlap_across_internal_tile_boundary():
    # Zoom/pan seam correctness (docs/dev/TILED_RENDERING_DESIGN.md Phase 2
    # remainder): a bilinear sample exactly on a tile boundary must land on
    # real neighbor pixel data on both sides, not a ClampToEdge repeat of
    # either tile's own edge texel. That requires each tile's apron-padded
    # rect to cross the shared boundary by exactly _TILE_APRON_PX pixels.
    grid = _grid()
    regions = {(row, col): region for row, col, region in grid.iter_regions()}
    boundary = regions[(0, 0)].right
    assert regions[(0, 1)].left == boundary  # adjacent tiles, no gap

    left_tile = _apron_rect(grid.total_width, grid.total_height, regions[(0, 0)], _TILE_APRON_PX)
    right_tile = _apron_rect(grid.total_width, grid.total_height, regions[(0, 1)], _TILE_APRON_PX)

    assert left_tile[2] == boundary + _TILE_APRON_PX
    assert right_tile[0] == boundary - _TILE_APRON_PX
    assert left_tile[2] - right_tile[0] == 2 * _TILE_APRON_PX


def test_visible_rect_straddling_tile_boundary_selects_both_neighbor_tiles():
    # If a viewport rect that straddles a seam only resolved to one tile,
    # the other side of the seam would sample the placeholder/stale
    # texture instead of real data -- this is the residency-side half of
    # seam correctness (the apron test above is the sampling-side half).
    grid = _grid()
    service = TileTextureService(max_tile_extent=2048)
    service.register_source("side", (grid.total_width, grid.total_height))
    regions = {(row, col): region for row, col, region in grid.iter_regions()}
    boundary = regions[(0, 0)].right

    rect = (boundary - 5.0, 0.0, boundary + 5.0, float(regions[(0, 0)].bottom))

    visible = service.visible_tiles("side", rect)

    assert (0, 0) in visible
    assert (0, 1) in visible
