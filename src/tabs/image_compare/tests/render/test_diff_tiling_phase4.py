"""Phase 4 diff-mode GPU tile consumption (docs/dev/TILED_RENDERING_DESIGN.md).

Before this, an oversized diff image (bigger than one GPU texture) silently
rendered blank: the diff source was registered with TileTextureService like
any other key, but nothing ever resolved a per-draw-call diff *tile*, so
`ensure_srb_for` fell back to the transparent placeholder texture. These
tests cover `_resolve_diff_tile_key`, the function that picks which diff
tile a draw call binds for a given image1 tileRect1 window.
"""

from __future__ import annotations

import pytest

from tabs.image_compare.canvas.rhi_renderer.draw_plan import _resolve_diff_tile_key
from shared.rendering.tile_texture_service import (
    TileTextureService,
)


def test_resolve_diff_tile_key_unregistered_source_returns_bare_key():
    service = TileTextureService(max_tile_extent=2048)

    key = _resolve_diff_tile_key(service, "diff", (0.0, 0.0, 1.0, 1.0))

    assert key == "diff"


def test_resolve_diff_tile_key_single_tile_grid_returns_bare_key():
    service = TileTextureService(max_tile_extent=4096)
    service.register_source("diff", (2000, 1500))

    key = _resolve_diff_tile_key(service, "diff", (0.0, 0.0, 1.0, 1.0))

    assert key == "diff"


def test_resolve_diff_tile_key_matches_row_col_when_grids_align():
    # image1 and diff share the same pixel dimensions (the steady-state
    # case) -> both register an identical grid against the same service.
    service = TileTextureService(max_tile_extent=2048)
    service.register_source("stored_0", (6000, 4000))
    service.register_source("diff", (6000, 4000))

    # image1's own top-left tile, expressed as a tileRect1 fraction.
    grid = service.grid_for("stored_0")
    rect1 = (0.0, 0.0, grid.tile_width / grid.total_width, grid.tile_height / grid.total_height)

    diff_key = _resolve_diff_tile_key(service, "diff", rect1)

    assert diff_key == ("diff", 0, 0)


def test_resolve_diff_tile_key_matches_bottom_right_when_grids_align():
    service = TileTextureService(max_tile_extent=2048)
    service.register_source("stored_0", (6000, 4000))
    service.register_source("diff", (6000, 4000))

    grid = service.grid_for("stored_0")
    last_row, last_col = grid.rows - 1, grid.columns - 1
    rect1 = (
        last_col * grid.tile_width / grid.total_width,
        last_row * grid.tile_height / grid.total_height,
        grid.tile_width / grid.total_width,
        grid.tile_height / grid.total_height,
    )

    diff_key = _resolve_diff_tile_key(service, "diff", rect1)

    assert diff_key == ("diff", last_row, last_col)


def test_resolve_diff_tile_key_best_overlap_when_grids_differ():
    # Diff stays full-res while image1's display texture is transiently
    # downscaled (interactive pan/zoom) -> grids diverge; the resolver must
    # still return some in-bounds diff tile rather than crashing/blanking.
    service = TileTextureService(max_tile_extent=2048)
    service.register_source("stored_0", (3000, 2000))
    service.register_source("diff", (6000, 4000))

    diff_key = _resolve_diff_tile_key(service, "diff", (0.0, 0.0, 0.5, 0.5))

    assert isinstance(diff_key, tuple) and diff_key[0] == "diff"
    diff_grid = service.grid_for("diff")
    row, col = diff_key[1], diff_key[2]
    assert 0 <= row < diff_grid.rows
    assert 0 <= col < diff_grid.columns
