"""Magnifier multi-tile capture geometry (docs/dev/TILED_RENDERING_DESIGN.md Phase 4).

Pure-geometry regression tests for tabs/image_compare/canvas/features/magnifier/
tile_capture.py -- no GPU/QRhi available in this environment, so correctness is
verified at the tc-range/uv-rect math level, mirroring the existing Phase 2/3
tile geometry tests (test_tiled_rendering_phase2.py, test_diff_tiling_phase4.py).
"""

from __future__ import annotations

import pytest

from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
    build_tile_records,
    dual_source_tile_pairs,
    intersect_tc_rects,
    intersect_widget_rects,
    is_full_tc,
    remap_slice_uv_to_tc,
    restrict_tc_axis,
    tc_rect_to_widget_px,
    tile_uv_slices,
    uv_segment_to_tc_range,
)
from tabs.image_compare.canvas.rhi_renderer import _apron_rect, _TILE_APRON_PX
from shared.rendering.tile_texture_service import (
    TileTextureService,
)


def _grid_and_service(width=6000, height=4000, max_tile_extent=2048, source="img"):
    service = TileTextureService(max_tile_extent=max_tile_extent)
    grid = service.register_source(source, (width, height))
    return grid, service


def _slices_fn(service, source):
    def _fn(key, rect):
        grid = service.grid_for(key)
        return tile_uv_slices(
            grid,
            service.tile_key,
            key,
            rect,
            apron_px=_TILE_APRON_PX,
            apron_rect_fn=_apron_rect,
            visible_tiles_fn=(lambda r: service.visible_tiles(key, r)),
        )

    return _fn


def test_uv_segment_to_tc_range_full_overlap_is_identity():
    assert uv_segment_to_tc_range(0.0, 1.0, 0.0, 1.0) == pytest.approx((0.0, 1.0))


def test_uv_segment_to_tc_range_partial_overlap_clamped():
    result = uv_segment_to_tc_range(0.2, 0.6, 0.0, 0.4)
    # segment covers uv in [0.0, 0.4]; range is [0.2,0.6] -> tc = (uv-0.2)/0.4
    assert result == pytest.approx((0.0, 0.5))


def test_uv_segment_to_tc_range_no_overlap_returns_none():
    assert uv_segment_to_tc_range(0.5, 0.9, 0.0, 0.4) is None


def test_tile_uv_slices_non_tiled_source_is_passthrough():
    slices = tile_uv_slices(
        None, None, "img", (0.1, 0.2, 0.3, 0.4),
        apron_px=1, apron_rect_fn=_apron_rect, visible_tiles_fn=None,
    )
    assert slices == [
        {"tile_key": "img", "uv_rect": (0.1, 0.2, 0.3, 0.4), "tc_x": (0.0, 1.0), "tc_y": (0.0, 1.0)}
    ]


def test_tile_uv_slices_capture_spanning_two_tiles():
    grid, service = _grid_and_service()
    # tile grid is 2048px wide tiles over 6000px -> boundary at col 0/1 around x=2048/6000
    boundary_frac = 2048.0 / grid.total_width
    uv_rect = (boundary_frac - 0.01, 0.0, boundary_frac + 0.01, 0.1)

    slices = _slices_fn(service, "img")("img", uv_rect)

    tile_keys = {s["tile_key"] for s in slices}
    assert any(k[1:] == (0, 0) for k in tile_keys)
    assert any(k[1:] == (0, 1) for k in tile_keys)
    # tc ranges cover [0, 1] with apron overlap at the shared tile boundary
    # (mirrors the base-quad seam-overlap design, see _TILE_APRON_PX and
    # test_apron_rects_overlap_across_internal_tile_boundary in
    # test_tiled_rendering_phase2.py) -- no gap, and a small overlap.
    ranges = sorted(s["tc_x"] for s in slices)
    assert ranges[0][0] == pytest.approx(0.0)
    assert ranges[-1][1] == pytest.approx(1.0)
    assert ranges[0][1] >= ranges[1][0]


def test_tile_uv_slices_single_tile_capture_stays_one_slice():
    grid, service = _grid_and_service()
    slices = _slices_fn(service, "img")("img", (0.01, 0.01, 0.05, 0.05))
    assert len(slices) == 1
    assert is_full_tc(slices[0]["tc_x"], slices[0]["tc_y"])


def test_remap_slice_uv_to_tc_narrower_range_is_linear_subset():
    slice_ = {"uv_rect": (0.0, 0.0, 1.0, 1.0), "tc_x": (0.0, 1.0), "tc_y": (0.0, 1.0)}
    remapped = remap_slice_uv_to_tc(slice_, (0.25, 0.75), (0.0, 0.5))
    assert remapped == pytest.approx((0.25, 0.0, 0.75, 0.5))


def test_expand_uv_rect_to_absolute_tc_is_identity_on_full_domain():
    from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
        expand_uv_rect_to_absolute_tc,
    )

    uv = (0.1, 0.2, 0.3, 0.4)
    assert expand_uv_rect_to_absolute_tc(uv, (0.0, 1.0), (0.0, 1.0)) == pytest.approx(uv)


def test_expand_uv_rect_to_absolute_tc_preserves_endpoint_samples():
    """mix(expanded, t) at the scissor endpoints recovers the local uv."""
    from tabs.image_compare.canvas.features.magnifier.render.tile_capture import (
        expand_uv_rect_to_absolute_tc,
    )

    local = (0.2, 0.1, 0.8, 0.9)
    tc_x, tc_y = (0.0, 0.5), (0.25, 0.75)
    expanded = expand_uv_rect_to_absolute_tc(local, tc_x, tc_y)
    u0, v0, u1, v1 = expanded

    def mix(a, b, t):
        return a + (b - a) * t

    assert mix(u0, u1, tc_x[0]) == pytest.approx(local[0])
    assert mix(u0, u1, tc_x[1]) == pytest.approx(local[2])
    assert mix(v0, v1, tc_y[0]) == pytest.approx(local[1])
    assert mix(v0, v1, tc_y[1]) == pytest.approx(local[3])


def test_restrict_tc_axis_x_splits_correctly():
    result = restrict_tc_axis((0.0, 1.0), (0.0, 1.0), "x", 0.0, 0.5)
    assert result == ((0.0, 0.5), (0.0, 1.0))


def test_restrict_tc_axis_disjoint_returns_none():
    assert restrict_tc_axis((0.0, 0.3), (0.0, 1.0), "x", 0.5, 1.0) is None


def test_intersect_tc_rects_overlap_and_disjoint():
    assert intersect_tc_rects((0.0, 0.6), (0.0, 1.0), (0.4, 1.0), (0.0, 1.0)) == (
        (0.4, 0.6),
        (0.0, 1.0),
    )
    assert intersect_tc_rects((0.0, 0.3), (0.0, 1.0), (0.5, 1.0), (0.0, 1.0)) is None


def test_dual_source_tile_pairs_cross_join_intersects_tc():
    slices1 = [
        {"tile_key": "a0", "uv_rect": (0.0, 0.0, 1.0, 1.0), "tc_x": (0.0, 0.5), "tc_y": (0.0, 1.0)},
        {"tile_key": "a1", "uv_rect": (0.0, 0.0, 1.0, 1.0), "tc_x": (0.5, 1.0), "tc_y": (0.0, 1.0)},
    ]
    slices2 = [
        {"tile_key": "b0", "uv_rect": (0.0, 0.0, 1.0, 1.0), "tc_x": (0.0, 1.0), "tc_y": (0.0, 1.0)},
    ]
    pairs = dual_source_tile_pairs(slices1, slices2)
    assert len(pairs) == 2
    assert {p["tile_key1"] for p in pairs} == {"a0", "a1"}
    assert all(p["tile_key2"] == "b0" for p in pairs)


def test_tc_rect_to_widget_px_full_range_matches_quad_bounds():
    rect = tc_rect_to_widget_px(100.0, 200.0, 50.0, (0.0, 1.0), (0.0, 1.0))
    assert rect == pytest.approx((50.0, 150.0, 100.0, 100.0))


def test_tc_rect_to_widget_px_y_is_flipped_relative_to_tc():
    # per mag.vert: tc.y=1 -> screen top (smaller pixel y), tc.y=0 -> screen bottom
    top_half = tc_rect_to_widget_px(100.0, 200.0, 50.0, (0.0, 1.0), (0.5, 1.0))
    bottom_half = tc_rect_to_widget_px(100.0, 200.0, 50.0, (0.0, 1.0), (0.0, 0.5))
    assert top_half[1] < bottom_half[1]


def test_intersect_widget_rects_basic():
    result = intersect_widget_rects((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 10.0, 10.0))
    assert result == (5.0, 5.0, 5.0, 5.0)


def test_intersect_widget_rects_disjoint_gives_zero_area():
    result = intersect_widget_rects((0.0, 0.0, 5.0, 5.0), (10.0, 10.0, 5.0, 5.0))
    assert result[2] == 0.0 and result[3] == 0.0


def test_build_tile_records_single_source_non_tiled_is_one_full_record():
    grid, service = _grid_and_service(width=100, height=100, max_tile_extent=2048)
    records = build_tile_records(
        source_slices_fn=_slices_fn(service, "img"),
        combined=False,
        source_mode=0,
        diff_mode=0,
        uv_rect1=(0.1, 0.1, 0.3, 0.3),
        uv_rect2=(0.0, 0.0, 1.0, 1.0),
        tex_key_1="img",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    assert len(records) == 1
    rec = records[0]
    assert is_full_tc(rec["tc_x"], rec["tc_y"])
    assert rec["tex1_key"] == "img"
    assert rec["tex2_key"] is None
    assert rec["texd_key"] is None
    assert rec["uv_rect1"] == pytest.approx((0.1, 0.1, 0.3, 0.3))


def test_build_tile_records_single_source_tiled_spans_two_tiles():
    grid, service = _grid_and_service()
    boundary_frac = 2048.0 / grid.total_width
    uv_rect = (boundary_frac - 0.01, 0.0, boundary_frac + 0.01, 0.1)
    records = build_tile_records(
        source_slices_fn=_slices_fn(service, "img"),
        combined=False,
        source_mode=0,
        diff_mode=0,
        uv_rect1=uv_rect,
        uv_rect2=(0.0, 0.0, 1.0, 1.0),
        tex_key_1="img",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    assert len(records) == 2
    assert all(r["tex1_key"] is not None and r["tex2_key"] is None for r in records)
    assert all(r["uv_rect2"] == pytest.approx((0.0, 0.0, 1.0, 1.0)) for r in records)


def test_build_tile_records_combined_mode_splits_into_two_source_halves():
    grid1, service1 = _grid_and_service(width=100, height=100, source="img1")
    service1.register_source("img2", (100, 100))
    capture = (0.1, 0.2, 0.7, 0.8)
    records = build_tile_records(
        source_slices_fn=_slices_fn(service1, "img1"),
        combined=True,
        source_mode=0,
        diff_mode=0,
        uv_rect1=capture,
        uv_rect2=capture,
        tex_key_1="img1",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    # Untiled capture → one dual-texture draw (no half scissors).
    assert len(records) == 1
    rec = records[0]
    assert is_full_tc(rec["tc_x"], rec["tc_y"])
    assert rec["tex1_key"] == "img1"
    assert rec["tex2_key"] == "img2"
    assert rec["uv_rect1"] == pytest.approx(capture)
    assert rec["uv_rect2"] == pytest.approx(capture)


def test_build_tile_records_combined_tiled_uses_half_scissors():
    grid, service = _grid_and_service()
    service.register_source("img2", (6000, 4000))
    boundary_frac = 2048.0 / grid.total_width
    # Capture spans a tile boundary → multi-slice path with half scissors.
    uv_rect = (boundary_frac - 0.01, 0.0, boundary_frac + 0.01, 0.1)

    def source_slices_fn(key, rect):
        return tile_uv_slices(
            service.grid_for(key),
            service.tile_key,
            key,
            rect,
            apron_px=_TILE_APRON_PX,
            apron_rect_fn=_apron_rect,
            visible_tiles_fn=(lambda r: service.visible_tiles(key, r)),
        )

    records = build_tile_records(
        source_slices_fn=source_slices_fn,
        combined=True,
        source_mode=0,
        diff_mode=0,
        uv_rect1=uv_rect,
        uv_rect2=uv_rect,
        tex_key_1="img",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    assert len(records) >= 2
    assert all(not is_full_tc(r["tc_x"], r["tc_y"]) for r in records)
    assert any(r["tex1_key"] is not None for r in records)
    assert any(r["tex2_key"] is not None for r in records)


def test_build_tile_records_dual_source_diff_mode_cross_joins_tiles():
    grid, service = _grid_and_service()
    service.register_source("img2", (6000, 4000))
    boundary_frac = 2048.0 / grid.total_width
    uv_rect = (boundary_frac - 0.01, 0.0, boundary_frac + 0.01, 0.1)

    def source_slices_fn(key, rect):
        return tile_uv_slices(
            service.grid_for(key),
            service.tile_key,
            key,
            rect,
            apron_px=_TILE_APRON_PX,
            apron_rect_fn=_apron_rect,
            visible_tiles_fn=(lambda r: service.visible_tiles(key, r)),
        )

    records = build_tile_records(
        source_slices_fn=source_slices_fn,
        combined=False,
        source_mode=2,
        diff_mode=1,
        uv_rect1=uv_rect,
        uv_rect2=uv_rect,
        tex_key_1="img",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    assert len(records) == 4  # 2 tiles on each side, cross-joined
    assert all(r["tex1_key"] is not None and r["tex2_key"] is not None for r in records)
    assert all(r["texd_key"] is None for r in records)


def test_build_tile_records_diff_edges_mode_uses_only_source_one():
    grid, service = _grid_and_service()
    boundary_frac = 2048.0 / grid.total_width
    uv_rect = (boundary_frac - 0.01, 0.0, boundary_frac + 0.01, 0.1)
    records = build_tile_records(
        source_slices_fn=_slices_fn(service, "img"),
        combined=False,
        source_mode=2,
        diff_mode=3,
        uv_rect1=uv_rect,
        uv_rect2=uv_rect,
        tex_key_1="img",
        tex_key_2="img2",
        diff_key="diff",
        internal_split=0.5,
        comb_horizontal=False,
    )
    assert len(records) == 2
    assert all(r["tex1_key"] is not None and r["tex2_key"] is None and r["texd_key"] is None for r in records)
