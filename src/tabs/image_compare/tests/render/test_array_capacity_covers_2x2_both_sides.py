"""Regression test for a user-reported bug (tiles vanishing/reappearing
above ~765% zoom, docs/dev/rendering/tile-array-atlas-plan.md Phase 2
Findings): a boundary-straddling 2x2 tile grid on both image1 and image2
needs 8 co-resident tiles in the shared texture array, but
``_ARRAY_CAPACITY`` (derived from ``_TILE_CACHE_BUDGET_BYTES //
_ARRAY_LAYER_BYTES``) floored to 7 at the documented 2 GB budget and
LIVE_TILE_EXTENT=8192 -- one short. The 8th tile then spilled into a
second array texture, and ``build_array_draw_plan`` drops (rather than
draws wrong) any pair whose two sides land in different arrays -- so a
tile permanently failed to render until eviction/zoom-out freed enough
slots to consolidate everything back into one array.

A flat floor merely papered over the specific 2x2 case the bug was first
found at, then resurfaced at deeper zoom once the grid grew past 2x2 (the
user's follow-up report, "разные грани" -- wrong/neighboring tile content
briefly showing). This test pins the *formula*, not a magic number, so
raising LIVE_TILE_EXTENT (Phase 3) or the byte budget can't silently
regress capacity below the real worst case again.
"""

from tabs.image_compare.canvas.rhi_renderer.resources import (
    _ARRAY_CAPACITY,
    _LIVE_TILE_EXTENT,
    _MAX_EXPECTED_CANVAS_PX,
)


def test_array_capacity_covers_worst_case_canvas_both_sides_plus_diff():
    # Independently re-derive the worst case (not importing _MAX_TILES_PER_AXIS
    # itself) to actually pin the formula's *meaning*, not just its result.
    import math

    tiles_per_axis = math.ceil(2 * _MAX_EXPECTED_CANVAS_PX / _LIVE_TILE_EXTENT) + 1
    needed = 3 * tiles_per_axis * tiles_per_axis  # image1 + image2 + diff
    assert _ARRAY_CAPACITY >= needed


def test_array_capacity_covers_2x2_grid_on_both_sides():
    # image1 + image2 each fully covering a boundary-straddling 2x2 grid
    # (4 tiles/side) must fit in one array without spilling into a second.
    assert _ARRAY_CAPACITY >= 8
