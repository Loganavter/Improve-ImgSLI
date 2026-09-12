"""Texture-array draw-plan builder (Phase 2 of
docs/dev/rendering/tile-array-atlas-plan.md) -- pure Python, no GPU.

Covers ``build_array_draw_plan``'s slot-lookup/cross-array-index-skip
behavior.
"""

from types import SimpleNamespace

import pytest

from shared.rendering.tile_texture_service import TileTextureService
from tabs.image_compare.canvas.rhi_renderer.draw_plan import (
    ArrayDrawItem,
    _covered_fraction,
    build_array_draw_plan,
    drop_covered_fallback_items,
)


def _base_image():
    return SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )


def test_build_array_draw_plan_skips_unresident_tiles():
    service = TileTextureService(max_tile_extent=1024)
    service.register_source("img1", (2048, 1024))  # columns=2, rows=1
    service.register_source("img2", (512, 512))
    # Only tile (0, 0) of img1 uploaded -- (0, 1) never marked resident, so
    # it has no slot yet and must not appear in the plan.
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(512, 512))

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        _base_image(),
        diff_key=None,
        sampler_name="linear",
    )
    assert len(items) == 1
    assert items[0].layer1 == 0
    assert items[0].layer2 == 1
    assert items[0].array_index == 0


def test_build_array_draw_plan_skips_cross_array_index_pairs():
    # max_array_size=2 forces a fresh array open every 2 allocations, so
    # img1's two tiles land in array 0 and img2's tile lands in array 1 --
    # the only way this mismatch is reachable in practice (_ARRAY_CAPACITY
    # far exceeds max_array_size normally).
    service = TileTextureService(max_tile_extent=1024, max_array_size=2)
    service.register_source("img1", (2048, 1024))  # columns=2, rows=1
    service.register_source("img2", (512, 512))
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img1", (0, 1), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(512, 512))

    assert service.slot_for("img1", (0, 0))[0] == 0
    assert service.slot_for("img1", (0, 1))[0] == 0
    assert service.slot_for("img2", (0, 0))[0] == 1

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        _base_image(),
        diff_key=None,
        sampler_name="linear",
    )
    assert items == []


def test_build_array_draw_plan_content_scale_reflects_uploaded_pixels():
    service = TileTextureService(max_tile_extent=1024)
    service.register_source("img1", (512, 512))
    service.register_source("img2", (512, 512))
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(1024, 512))

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        _base_image(),
        diff_key=None,
        sampler_name="linear",
    )
    assert len(items) == 1
    scale1_w, scale1_h, scale2_w, scale2_h = items[0].content_scale
    assert scale2_w == scale1_w  # same width upload as img1's tile
    assert scale2_h < scale1_h  # half-height upload leaves half the layer padded


def test_build_array_draw_plan_only_pairs_geometrically_overlapping_tiles():
    """A same-size-image 4x4/4x4 grid pairing corner tile (0, 0) against
    corner tile (3, 3) has no on-screen overlap even with
    ``_TILE_APRON_PX``'s 1px padding (negligible next to a 4096px grid) --
    that pair would be fully discarded by ``base_array.frag``'s per-pixel
    inTile1/inTile2 check anyway (found investigating a user report of tile
    content briefly showing the wrong facet -- docs/dev/rendering/
    tile-array-atlas-plan.md Phase 2 Findings). ``build_array_draw_plan``
    should filter it out itself rather than submit a doomed-to-discard draw
    instance. (Adjacent/diagonal *neighbor* tiles, e.g. a plain 2x2 grid,
    are deliberately not used here: apron overlap between neighbors is real
    and intentional -- see tile_geometry._apron_rect -- so same-size 2x2
    grids legitimately produce all 4x4=16 pairs, not 4.)"""
    service = TileTextureService(max_tile_extent=1024)
    service.register_source("img1", (4096, 4096))  # 4x4 grid
    service.register_source("img2", (4096, 4096))  # 4x4 grid, same layout
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img1", (3, 3), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(1024, 1024))
    service.mark_resident("img2", (3, 3), byte_size=100, content_size=(1024, 1024))

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        _base_image(),
        diff_key=None,
        sampler_name="linear",
    )
    assert len(items) == 2
    for item in items:
        assert item.rect1 == item.rect2


def test_build_array_draw_plan_splits_instances_per_diff_tile():
    """A coarse-LOD side1/side2 (1x1 grid each, e.g. a pyramid level picked
    while zoomed out) paired with a diff source at a finer grid (e.g. the
    SSIM map, always generated at full source resolution with no matching
    coarse level of its own) must produce one instance per diff tile
    actually covering the visible area, not a single "best overlap" pick --
    the latter would show only that one diff tile's content, stretched over
    the whole screen, instead of each screen region's own diff tile
    (docs/dev/rendering/qrhi-gotchas.md canvas SSIM display investigation)."""
    service = TileTextureService(max_tile_extent=512)
    service.register_source("img1", (512, 512))  # 1x1 grid
    service.register_source("img2", (512, 512))  # 1x1 grid
    service.register_source("diff", (1024, 1024))  # 2x2 grid, finer than img1/img2
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(512, 512))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(512, 512))
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("diff", index, byte_size=100, content_size=(512, 512))

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        _base_image(),
        diff_key="diff",
        sampler_name="linear",
    )

    assert len(items) == 4
    diff_layers = {item.layer_diff for item in items}
    assert len(diff_layers) == 4  # each diff tile's own distinct array layer
    for item in items:
        # img1/img2 only have one tile each -- unchanged across every split.
        assert item.rect1 == (0.0, 0.0, 1.0, 1.0)
        assert item.rect2 == (0.0, 0.0, 1.0, 1.0)
        # Each instance only covers its own diff tile's quarter of the
        # canvas, not the whole [0,1]x[0,1] pair footprint.
        _, _, bw, bh = item.bbox
        assert bw < 1.0 and bh < 1.0
    # Adjacent diff tiles' bboxes overlap slightly at their shared apron
    # (same intentional overlap side1/side2 neighbors get -- see
    # test_build_array_draw_plan_only_pairs_geometrically_overlapping_tiles's
    # docstring), so this sums to a bit over 1.0 rather than exactly 1.0.
    total_bbox_area = sum(item.bbox[2] * item.bbox[3] for item in items)
    assert 1.0 <= total_bbox_area < 1.05


def test_build_array_draw_plan_diff_split_rect_diff_stays_in_raw_image_space():
    """``rect_diff`` feeds ``base_array.frag``'s ``sampleUV - vRectDiff.xy``,
    and ``sampleUV`` is in the same raw-image-fraction space as
    rect1/rect2 (post-letterbox-division, *not* common/canvas space) --
    unlike ``bbox``, which *is* common-space. A non-trivial but overlapping
    letterbox (both sides pillarboxed identically -- the normal case for a
    split comparison, split via ``splitPosition`` at shader level rather
    than via disjoint letterboxes) distinguishes the two: conflating them
    (previously ``rect_diff`` was built via ``_to_common_space``, the same
    helper ``bbox`` uses) squeezed every rect_diff into the pillarboxed
    sub-range instead of diff's own full [0,1] tile-fraction range,
    stretching each tile's sampled content (docs/dev/rendering/
    qrhi-gotchas.md #ssim-diff-blocky-mosaic-at-coarse-lod follow-up)."""
    base_image = SimpleNamespace(
        zoom=1.0,
        pan_offset_x=0.0,
        pan_offset_y=0.0,
        letterbox1=(0.1, 0.0, 0.8, 1.0),  # pillarboxed 10% each side
        letterbox2=(0.1, 0.0, 0.8, 1.0),
    )
    service = TileTextureService(max_tile_extent=512)
    service.register_source("img1", (512, 512))  # 1x1 grid
    service.register_source("img2", (512, 512))  # 1x1 grid
    service.register_source("diff", (1024, 1024))  # 2x2 grid
    service.mark_resident("img1", (0, 0), byte_size=100, content_size=(512, 512))
    service.mark_resident("img2", (0, 0), byte_size=100, content_size=(512, 512))
    for index in ((0, 0), (0, 1), (1, 0), (1, 1)):
        service.mark_resident("diff", index, byte_size=100, content_size=(512, 512))

    items = build_array_draw_plan(
        service,
        ("img1", "img2"),
        base_image,
        diff_key="diff",
        sampler_name="linear",
    )

    assert len(items) == 4
    for item in items:
        # diff's own tile-fraction rect spans up to 1.0 in each axis (a 2x2
        # grid), regardless of the 0.5-wide letterbox -- common-space values
        # would top out at 0.5 (letterbox1's own width) instead.
        rx, ry, rw, rh = item.rect_diff
        assert rx + rw <= 1.0 + 1e-6
        assert ry + rh <= 1.0 + 1e-6
        assert rw > 0.5 - 1e-6  # each tile is half of diff's full 2x2 extent
        assert rh > 0.5 - 1e-6


def _fake_item(rect1: tuple[float, float, float, float]) -> ArrayDrawItem:
    return ArrayDrawItem(
        rect1=rect1,
        rect2=rect1,
        content_scale=(1.0, 1.0, 1.0, 1.0),
        content_scale_diff=(1.0, 1.0),
        layer1=0,
        layer2=0,
        layer_diff=0,
        array_index=0,
        sampler_name="linear",
        bbox=rect1,
    )


def test_drop_covered_fallback_items_removes_overlapping_regions():
    # Current level already covers the left half of the screen; only the
    # fallback tile over the still-uncovered right half should survive.
    fallback_items = [
        _fake_item((0.0, 0.0, 0.5, 1.0)),
        _fake_item((0.5, 0.0, 0.5, 1.0)),
    ]
    current_items = [_fake_item((0.0, 0.0, 0.5, 1.0))]

    kept = drop_covered_fallback_items(fallback_items, current_items, _base_image())

    assert kept == [fallback_items[1]]


def test_drop_covered_fallback_items_keeps_everything_when_current_is_empty():
    fallback_items = [_fake_item((0.0, 0.0, 1.0, 1.0))]

    kept = drop_covered_fallback_items(fallback_items, [], _base_image())

    assert kept == fallback_items


def test_covered_fraction_not_fooled_by_duplicate_overlapping_rects():
    """docs/dev/rendering/tile-array-atlas-plan.md Phase 11: a live user
    capture showed only 11 of 25 needed tiles resident on one side
    (``TIME_DEADLINE ... uploaded=11/25``), yet ``GAP_DETECTED`` never
    fired even though the user visually confirmed a hole on screen --
    because those 11 tiles were each paired against several tiles on the
    fully-resident other side (apron overlap), producing many duplicate
    copies of the same covered rect in the ``others`` list. The left half
    here stands in for that already-covered, duplicate-heavy region (10
    copies of the same rect -- summing per-rect areas would report 10x the
    left half's actual area, i.e. way past 100% of the *whole* rect); the
    right half stands in for the still-missing 14 tiles (no coverage at
    all). A sum-of-areas check reports the whole rect as covered (0.5 real
    + 10x0.5 double-counted overshoot, clamped only by luck); point
    sampling must not."""
    rect = (0.0, 0.0, 1.0, 1.0)
    others = [(0.0, 0.0, 0.5, 1.0)] * 10

    covered = _covered_fraction(rect, others)

    # Exactly half the rect is covered; the 9x9 sample grid's discretization
    # rounds that to 5/9 (~0.556) rather than a mathematically exact 0.5 --
    # the assertion only needs to rule out the naive area-sum bug's ~10x
    # overshoot, not match floating-point-exact coverage.
    assert covered <= 0.6


def test_covered_fraction_detects_full_coverage_without_duplicates():
    rect = (0.0, 0.0, 1.0, 1.0)
    others = [(0.0, 0.0, 0.5, 1.0), (0.5, 0.0, 0.5, 1.0)]

    covered = _covered_fraction(rect, others)

    assert covered >= 0.99