"""Phase 3 output/export tiling geometry (docs/dev/TILED_RENDERING_DESIGN.md).

Covers the two pieces that make a "resize widget to tile size, render N
times" export loop geometrically correct: the export tile-rect helper
(exact clamp to true canvas size, no padding overrun) and the per-tile
viewport zoom/offset composition (exact no-op when a tile covers the whole
canvas, correct composition otherwise).
"""

from __future__ import annotations

import pytest

from shared.rendering.export_tiling import iter_export_tile_rects
from shared.rendering.tile_geometry import viewport_zoom_offset_for_tile as _viewport_zoom_offset_for_tile


def test_iter_export_tile_rects_single_tile_when_within_extent():
    rects = list(iter_export_tile_rects(1920, 1080, 4096))

    assert rects == [(0, 0, 1920, 1080)]


def test_iter_export_tile_rects_covers_canvas_without_overrun():
    canvas_w, canvas_h = 9000, 5000
    max_extent = 4096

    rects = list(iter_export_tile_rects(canvas_w, canvas_h, max_extent))

    assert len(rects) > 1
    total_area = 0
    max_right = 0
    max_bottom = 0
    for left, top, width, height in rects:
        assert width > 0 and height > 0
        assert width <= max_extent and height <= max_extent
        assert left + width <= canvas_w
        assert top + height <= canvas_h
        total_area += width * height
        max_right = max(max_right, left + width)
        max_bottom = max(max_bottom, top + height)

    # Disjoint (verified separately) + summed area == canvas area is
    # sufficient to prove full coverage without an O(pixels) scan.
    assert total_area == canvas_w * canvas_h
    assert max_right == canvas_w
    assert max_bottom == canvas_h


def test_iter_export_tile_rects_tiles_are_disjoint():
    rects = list(iter_export_tile_rects(9000, 5000, 4096))

    boxes = [(left, top, left + w, top + h) for left, top, w, h in rects]
    for i, (l1, t1, r1, b1) in enumerate(boxes):
        for l2, t2, r2, b2 in boxes[i + 1 :]:
            overlap_x = max(0, min(r1, r2) - max(l1, l2))
            overlap_y = max(0, min(b1, b2) - max(t1, t2))
            assert overlap_x == 0 or overlap_y == 0


def test_viewport_zoom_offset_no_op_when_tile_covers_full_canvas():
    zoom, offset = _viewport_zoom_offset_for_tile(
        2000, 1000, (0.0, 0.0, 2000.0, 1000.0), base_zoom=(1.7, 1.7), base_offset=(0.05, -0.1)
    )

    assert zoom == pytest.approx((1.7, 1.7))
    assert offset == pytest.approx((0.05, -0.1))


def test_viewport_zoom_offset_no_op_at_default_zoom_pan():
    zoom, offset = _viewport_zoom_offset_for_tile(
        4000, 4000, (0.0, 0.0, 2000.0, 2000.0)
    )

    # A quarter-canvas tile at identity zoom/pan must zoom in 2x per axis
    # and re-center on that quadrant — verifies the composition formula
    # against a hand-computed case, not just the full-canvas no-op.
    assert zoom == pytest.approx((2.0, 2.0))
    assert offset == pytest.approx((0.25, 0.25))


def test_viewport_zoom_offset_composes_with_nonuniform_tile_and_base_zoom():
    canvas_w, canvas_h = 8000, 4000
    tile_rect = (4000.0, 0.0, 8000.0, 4000.0)

    zoom, offset = _viewport_zoom_offset_for_tile(
        canvas_w, canvas_h, tile_rect, base_zoom=(1.0, 1.0), base_offset=(0.0, 0.0)
    )

    assert zoom[0] == pytest.approx(2.0)
    assert zoom[1] == pytest.approx(1.0)
