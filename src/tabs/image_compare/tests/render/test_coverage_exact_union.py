"""P2 canvas parity: exact union coverage has no sampler aliasing.

The shared 9x9 point sampler is biased toward "covered": a hole narrower
than a sample cell and sitting between sample points reports 1.0, so the
first-paint hold releases on a lie and gap detection stays silent.
``_coverage_union`` (exact rect subtraction, sampled fallback only when
fragmentation explodes) must report exactly 1.0 for full coverage however
misaligned the tile edges are, and below the 0.999 gap threshold for any
real hole however thin.
"""

from __future__ import annotations

from engine.cache.tile_coverage import covered_fraction
from tabs.image_compare.canvas.rhi_renderer.use_cases.coverage import (
    _coverage_union,
    _exact_covered_fraction,
)

FULL = (0.0, 0.0, 1.0, 1.0)


def test_full_coverage_misaligned_edges_is_exactly_one():
    tiles = [
        (0.0, 0.0, 0.37, 1.0),
        (0.37, 0.0, 0.33, 1.0),
        (0.70, 0.0, 0.30, 1.0),
    ]
    assert _coverage_union(FULL, tiles) == 1.0


def test_sliver_hole_between_samples_is_detected():
    tiles = [
        (0.0, 0.0, 0.45, 1.0),
        (0.47, 0.0, 0.53, 1.0),  # 0.02-wide hole holds no 9x9 center
    ]
    assert covered_fraction(FULL, tiles) >= 0.999  # pins the sampler blind spot
    assert _coverage_union(FULL, tiles) == 0.98
    assert _coverage_union(FULL, tiles) < 0.999


def test_empty_and_degenerate_inputs():
    assert _coverage_union(FULL, []) == 0.0
    assert _coverage_union((0.5, 0.5, 0.0, 0.0), [(0.0, 0.0, 1.0, 1.0)]) == 1.0
    assert _coverage_union(FULL, [(0.0, 0.0, -1.0, 1.0)]) == 0.0


def test_duplicate_rects_do_not_inflate_coverage():
    tiles = [(0.0, 0.0, 0.5, 1.0)] * 7 + [(0.5, 0.0, 0.5, 1.0)]
    assert _coverage_union(FULL, tiles) == 1.0
    partial = [(0.0, 0.0, 0.5, 1.0)] * 7
    assert _coverage_union(FULL, partial) == 0.5


def test_fragmentation_cap_falls_back_to_sampled_estimate():
    tiles = [(0.0, 0.0, 0.4, 1.0), (0.6, 0.0, 0.4, 1.0)]
    assert _exact_covered_fraction(FULL, tiles, max_pieces=0) is None
    # Default cap: exact path succeeds and is exact (0.8 covered), while the
    # sampler can only resolve ninths (8/9 here).
    assert _coverage_union(FULL, tiles) == 0.8
    assert covered_fraction(FULL, tiles) == 8 / 9


def test_overlapping_aprons_stay_exact():
    tiles = [
        (0.0, 0.0, 0.52, 1.0),
        (0.48, 0.0, 0.52, 1.0),  # apron overlap, no double-count
    ]
    assert _coverage_union(FULL, tiles) == 1.0
