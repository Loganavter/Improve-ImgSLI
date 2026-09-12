"""Direct tests for MC drop_covered_fallback_tiles (W5 gap: ZERO tests).

Inv: double-draw/z-fighting prevention - fallback tiles fully covered by current must be dropped.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tabs.multi_compare.scene.tile_geometry import SlotArrayTile, drop_covered_fallback_tiles


def _tile(rect):
    return SlotArrayTile(tile_rect=rect, index=(0, 0))


def test_drop_covered_removes_fully_covered():
    fallback = [_tile((0.0, 0.0, 1.0, 1.0))]
    current = [_tile((0.0, 0.0, 1.0, 1.0))]
    kept = drop_covered_fallback_tiles(fallback, current)
    assert kept == []


def test_keep_when_current_empty():
    fallback = [_tile((0.0, 0.0, 0.5, 0.5)), _tile((0.5, 0.5, 0.5, 0.5))]
    kept = drop_covered_fallback_tiles(fallback, [])
    assert kept == fallback


def test_partial_coverage_keeps_tile():
    # Only 25% covered -> below 0.98 threshold -> kept
    fallback = [_tile((0.0, 0.0, 1.0, 1.0))]
    current = [_tile((0.0, 0.0, 0.5, 0.5))]
    kept = drop_covered_fallback_tiles(fallback, current)
    assert len(kept) == 1


def test_union_coverage_drops_when_combined_covers():
    # Fallback 0..1; two current halves together cover fully -> drop
    fallback = [_tile((0.0, 0.0, 1.0, 1.0))]
    current = [_tile((0.0, 0.0, 0.5, 1.0)), _tile((0.5, 0.0, 0.5, 1.0))]
    kept = drop_covered_fallback_tiles(fallback, current)
    assert kept == []


def test_mixed_tiles_some_kept_some_dropped():
    fallback = [_tile((0.0, 0.0, 0.5, 0.5)), _tile((0.5, 0.5, 0.5, 0.5))]
    # Only first fallback covered
    current = [_tile((0.0, 0.0, 0.5, 0.5))]
    kept = drop_covered_fallback_tiles(fallback, current)
    assert len(kept) == 1
    assert kept[0].tile_rect == (0.5, 0.5, 0.5, 0.5)


def test_threshold_is_near_total():
    # 0.8 covers 72/81=0.888 <0.98 -> keep; 0.99 covers all 81/81=1.0 >0.98 -> drop
    fallback = [_tile((0.0, 0.0, 1.0, 1.0))]
    current_keep = [_tile((0.0, 0.0, 0.8, 1.0))]
    kept = drop_covered_fallback_tiles(fallback, current_keep)
    assert len(kept) == 1, "0.8 coverage should be kept (below 0.98)"
    current_drop = [_tile((0.0, 0.0, 0.99, 1.0))]
    kept2 = drop_covered_fallback_tiles(fallback, current_drop)
    assert kept2 == []
