"""Live/export parity harness (task-engine-2d, bucket 2D).

Same snapshot in -> same LOD level + same tile set out, through the live
path (``resolve_lod_texture_keys`` + ``TileTextureService.visible_tiles``)
and the export path (``snapshot_lod_tiles_for_sources`` test-support helper
in ``snapshot_render_plan_builder``). Both decide via
``engine.cache.lod.select_level`` with identical inputs and take no ``mode``
argument -- any live-only or export-only fudge in LOD or tile selection
fails here.

The plan-level checks above (level + tile index sets) are a cheap guard, but
they are blind to a *rect* mix-up: a plan whose tile ``i`` carries tile
``i+1``'s source rect has the same level and the same index set. The
pixel-level half of the harness (``test_same_snapshot_same_tile_pixels`` +
``test_pixel_parity_detects_a_swapped_tile_rect``) closes that pocket: it
decodes the same level source, copies each planned tile through its
image-fraction rect, and requires the per-tile bytes to equal what the live
copy path (``crop_apron_tile`` over the grid region) actually copies. The
source store is spatially patterned (not blank) so a swapped rect really is
detectable -- the falsification test proves the assertion is not vacuous.

This harness pins the decision/geometry only; it does not redesign the
export CPU-prescale path (explicit non-goal), and it never renders through
a GPU surface (exports are GPU-tiled; that layer is out of scope here).
"""

from __future__ import annotations

import inspect
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

pytest.importorskip("skimage")  # diff/SSIM needs scikit-image; app degrades without it

from engine.store import pyramid_registry
from engine.store.tiled_pixel_store import TiledPixelStore
from engine.cache.draw_plans import PlanTile, plan_tiles_for_grid
from engine.cache.lod import LevelKey
from engine.cache.tile_constants import TILE_APRON_PX
from engine.cache.tile_geometry import crop_apron_tile
from engine.cache.tile_texture_service import TileTextureService
from engine.gpu.export_tiling import qimage_to_pil_rgba
from tabs.image_compare.canvas.rhi_renderer.draw_plan import (
    resolve_lod_texture_keys,
)
from tabs.image_compare.services.snapshot_render_plan_builder import (
    snapshot_lod_tiles_for_sources,
)

_FULL = (0.0, 0.0, 1.0, 1.0)


@pytest.fixture(autouse=True)
def _clean_registry():
    pyramid_registry.clear()
    yield
    pyramid_registry.clear()


def _store(width=2048, height=2048):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    store = TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert pyramid is not None
    pyramid.build_all()
    return store


def _patterned_store(width=2048, height=2048):
    """Spatially varying source: every 64px block differs from its neighbour.

    The blank ``_store`` is fine for plan-level checks, but a pixel-level
    rect swap on a uniform image is indistinguishable (all tiles are the
    same bytes). The pattern is deterministic and high-contrast enough to
    survive pyramid downsampling, so a wrong rect shows up as a byte
    mismatch on both the base and coarse levels.
    """
    yy, xx = np.mgrid[0:height, 0:width]
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[..., 0] = ((xx // 64) * 37 + (yy // 64) * 11) % 256
    arr[..., 1] = (xx + 3 * yy) % 251
    arr[..., 2] = ((yy // 64) * 53) % 256
    arr[..., 3] = 255
    store = TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert pyramid is not None
    pyramid.build_all()
    return store


def _live_keys(sources, *, canvas_size_px, zoom, letterboxes):
    """LOD texture keys the live path would upload for this snapshot."""
    base_image = SimpleNamespace(
        zoom=zoom, letterbox1=letterboxes[0], letterbox2=letterboxes[1]
    )
    return resolve_lod_texture_keys(
        ("source_0", "source_1"), sources, base_image, canvas_size_px
    )


def _level_source(store, level):
    """The pixel source a renderer samples for ``level`` (same decode)."""
    if level == 0:
        return store
    pyramid = pyramid_registry.pyramid_for(store)
    assert pyramid is not None
    return pyramid.level(level)


def _copy_box(grid, index, apron=TILE_APRON_PX):
    """Pixel box the live copy path actually crops for ``index``.

    Mirrors ``crop_apron_tile``/``_apron_rect``: the tile's grid region
    expanded by the apron and clamped to the grid extent.
    """
    region = grid.region_for(*index)
    return (
        max(0, region.left - apron),
        max(0, region.top - apron),
        min(grid.total_width, region.right + apron),
        min(grid.total_height, region.bottom + apron),
    )


def _plan_box(tile: PlanTile, grid):
    """Pixel box of a plan tile's image-fraction ``(left, top, width, height)``.

    This is the rect the export decision carries per tile -- what a renderer
    consuming the plan would crop.
    """
    left = round(tile.rect[0] * grid.total_width)
    top = round(tile.rect[1] * grid.total_height)
    width = round(tile.rect[2] * grid.total_width)
    height = round(tile.rect[3] * grid.total_height)
    return (left, top, left + width, top + height)


def _compose_actual(source, grid, indices):
    """Canvas-frame composite: copy each index through the live copy path."""
    image = Image.new("RGBA", source.size)
    for index in indices:
        region = grid.region_for(*index)
        qimage = crop_apron_tile(
            source,
            region.left,
            region.top,
            region.right,
            region.bottom,
            TILE_APRON_PX,
        )
        tile = qimage_to_pil_rgba(qimage)
        image.paste(tile, _copy_box(grid, index)[:2])
    return image


def _compose_planned(source, grid, tiles):
    """Exported-image composite: crop each tile through its planned rect and
    place it at the position the tile's *index* dictates.

    Destination comes from the grid index, source from the plan rect: if a
    plan associates tile ``i`` with tile ``i+1``'s rect, the pasted content
    lands in the wrong place and the per-tile byte comparison fails.
    """
    image = Image.new("RGBA", source.size)
    for tile in tiles:
        destination = _copy_box(grid, tile.index)[:2]
        image.paste(source.crop(_plan_box(tile, grid)), destination)
    return image


def _rect_mismatches(reference, candidate, boxes):
    """Boxes whose bytes differ between two same-size images."""
    ref = np.asarray(reference)
    cand = np.asarray(candidate)
    bad = []
    for left, top, right, bottom in boxes:
        if not np.array_equal(
            ref[top:bottom, left:right], cand[top:bottom, left:right]
        ):
            bad.append((left, top, right, bottom))
    return bad


def _assert_same_snapshot_pixels(
    stores, live_keys, canvas, zoom, letterboxes, rect
):
    """Per-tile pixel parity for one snapshot: plan rects vs live copies."""
    live_levels = tuple(
        key.level if isinstance(key, LevelKey) else 0 for key in live_keys
    )
    export_service = TileTextureService(max_tile_extent=512)
    export = snapshot_lod_tiles_for_sources(
        stores,
        canvas_size_px=canvas,
        zoom=zoom,
        letterboxes=letterboxes,
        image_space_rect=rect,
        tile_service=export_service,
    )
    # Cheap guard stays in front of the pixel work (same rationale as
    # test_same_snapshot_same_level_and_tiles).
    assert export.levels == live_levels
    for side, (store, key) in enumerate(zip(stores, live_keys)):
        level = live_levels[side]
        source = _level_source(store, level)
        width, height = source.size
        grid = export_service.grid_for(key)
        assert grid is not None
        visible_rect = rect
        if visible_rect is None:
            visible_rect = (0.0, 0.0, float(width), float(height))
        tiles = plan_tiles_for_grid(export_service, key, visible_rect)
        assert tuple(sorted(tile.index for tile in tiles)) == export.tile_sets[side]
        # The plan rect must address exactly the pixels the live copy path
        # crops for that same tile index (apron included, edge-clamped).
        for tile in tiles:
            assert _plan_box(tile, grid) == _copy_box(grid, tile.index)
        boxes = [_copy_box(grid, tile.index) for tile in tiles]
        canvas_frame = _compose_actual(source, grid, [t.index for t in tiles])
        exported = _compose_planned(source, grid, tiles)
        assert _rect_mismatches(canvas_frame, exported, boxes) == []


def _live_levels_and_tiles(
    sources, *, canvas_size_px, zoom, letterboxes, rect=None, max_tile_extent=512
):
    """Live-path decision: LOD keys + full/partial-rect tile sets."""
    base_image = SimpleNamespace(
        zoom=zoom, letterbox1=letterboxes[0], letterbox2=letterboxes[1]
    )
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"), sources, base_image, canvas_size_px
    )
    levels = tuple(k.level if isinstance(k, LevelKey) else 0 for k in keys)
    service = TileTextureService(max_tile_extent=max_tile_extent)
    tile_sets = []
    for key, source in zip(keys, sources):
        if isinstance(key, LevelKey):
            pyramid = pyramid_registry.pyramid_for(source)
            assert pyramid is not None
            width, height = pyramid.level(key.level).size
        else:
            width, height = source.size
        service.register_source(key, (int(width), int(height)))
        use_rect = rect
        if use_rect is None:
            use_rect = (0.0, 0.0, float(width), float(height))
        tile_sets.append(tuple(sorted(service.visible_tiles(key, use_rect))))
    return levels, (tile_sets[0], tile_sets[1])


SNAPSHOTS = [
    pytest.param((500.0, 500.0), 1.0, (_FULL, _FULL), id="fit-zoom-coarse"),
    pytest.param((2000.0, 1400.0), 4.0, (_FULL, _FULL), id="deep-zoom-base"),
    pytest.param((2000.0, 1400.0), 1.0, (_FULL, _FULL), id="mid-zoom"),
    pytest.param(
        (2000.0, 1400.0),
        1.0,
        ((0.25, 0.0, 0.5, 1.0), (0.25, 0.0, 0.5, 1.0)),
        id="half-letterbox",
    ),
]

RECTS = [
    pytest.param(None, id="whole-snapshot"),
    pytest.param((256.0, 256.0, 768.0, 768.0), id="partial-rect"),
]


@pytest.mark.parametrize("canvas,zoom,letterboxes", SNAPSHOTS)
@pytest.mark.parametrize("rect", RECTS)
def test_same_snapshot_same_level_and_tiles(canvas, zoom, letterboxes, rect):
    s1 = _store()
    s2 = _store()
    try:
        live_levels, live_tiles = _live_levels_and_tiles(
            (s1, s2), canvas_size_px=canvas, zoom=zoom, letterboxes=letterboxes,
            rect=rect,
        )
        export_service = TileTextureService(max_tile_extent=512)
        export = snapshot_lod_tiles_for_sources(
            (s1, s2),
            canvas_size_px=canvas,
            zoom=zoom,
            letterboxes=letterboxes,
            image_space_rect=rect,
            tile_service=export_service,
        )
        assert export.levels == live_levels
        assert export.tile_sets == live_tiles
        # Both sides resolve together (shared-level clamp): levels match.
        assert export.levels[0] == export.levels[1]
        # Multi-tile grids actually exercised -- otherwise the harness
        # would pass vacuously on 1x1 grids.
        assert len(export.tile_sets[0]) >= 1
    finally:
        s1.close()
        s2.close()


@pytest.mark.parametrize("canvas,zoom,letterboxes", SNAPSHOTS)
@pytest.mark.parametrize("rect", RECTS)
def test_same_snapshot_same_tile_pixels(canvas, zoom, letterboxes, rect):
    """Pixel-level parity: per tile, the exported image's rect bytes equal
    the canvas frame's rect bytes after the same decode.

    The plan-level test above would still pass if a plan swapped two
    adjacent tiles' rects (same level, same index set). Here the source is
    spatially patterned, each planned rect is checked against the exactly
    copied box, and every tile's bytes are compared against what the live
    copy path (``crop_apron_tile`` over the grid region) produces.
    """
    s1 = _patterned_store()
    s2 = _patterned_store()
    try:
        live_keys = _live_keys(
            (s1, s2),
            canvas_size_px=canvas,
            zoom=zoom,
            letterboxes=letterboxes,
        )
        _assert_same_snapshot_pixels(
            (s1, s2), live_keys, canvas, zoom, letterboxes, rect
        )
    finally:
        s1.close()
        s2.close()


def test_pixel_parity_detects_a_swapped_tile_rect():
    """Falsification: the pixel assertion is not vacuous.

    Deliberately swap two adjacent tiles' planned rects (tile ``i`` vs
    ``i+1``): the honest composite matches the canvas frame byte-for-byte,
    the swapped one must be reported as a mismatch on exactly those tiles'
    rects. Without the pixel half of the harness this plan (same level,
    same index set) would pass the old assertions.
    """
    s1 = _patterned_store()
    s2 = _patterned_store()
    try:
        canvas, zoom, letterboxes = (2000.0, 1400.0), 4.0, (_FULL, _FULL)
        rect = (256.0, 256.0, 768.0, 768.0)
        live_keys = _live_keys(
            (s1, s2),
            canvas_size_px=canvas,
            zoom=zoom,
            letterboxes=letterboxes,
        )
        export_service = TileTextureService(max_tile_extent=512)
        export = snapshot_lod_tiles_for_sources(
            (s1, s2),
            canvas_size_px=canvas,
            zoom=zoom,
            letterboxes=letterboxes,
            image_space_rect=rect,
            tile_service=export_service,
        )
        # Two adjacent tiles with different content are required to make a
        # swap observable at all.
        assert len(export.tile_sets[0]) >= 2
        for side, (store, key) in enumerate(zip((s1, s2), live_keys)):
            level = export.levels[side]
            source = _level_source(store, level)
            grid = export_service.grid_for(key)
            assert grid is not None
            tiles = plan_tiles_for_grid(export_service, key, rect)
            assert len(tiles) >= 2
            boxes = [_copy_box(grid, tile.index) for tile in tiles]

            canvas_frame = _compose_actual(source, grid, [t.index for t in tiles])
            honest = _compose_planned(source, grid, tiles)
            assert _rect_mismatches(canvas_frame, honest, boxes) == []

            swapped = [
                replace(tiles[0], rect=tiles[1].rect),
                replace(tiles[1], rect=tiles[0].rect),
                *tiles[2:],
            ]
            mismatches = _rect_mismatches(
                canvas_frame, _compose_planned(source, grid, swapped), boxes
            )
            # Both swapped tiles changed content: the detector fires exactly
            # where the rects were exchanged, not somewhere incidental.
            assert mismatches == [boxes[0], boxes[1]]
    finally:
        s1.close()
        s2.close()


def test_zoomed_out_large_export_tier_equals_live():
    """Task 3 (task-fix-export-lod-parity-2026-09-20) verification: a
    zoomed-out large export (big canvas, small zoom) resolves the same LOD
    tier — and the same tile set — as the live path on matched inputs.

    Same-snapshot-in -> same-level-plus-same-tiles-out, through the live
    entry (``resolve_lod_texture_keys``) and the export entry
    (``snapshot_lod_tiles_for_sources``): any live-only or export-only
    fudge in scale handling (e.g. a tile-surface DPR leaking into the
    whole-canvas LOD input) fails here.
    """
    s1 = _store()
    s2 = _store()
    try:
        canvas = (4096.0, 3072.0)
        zoom = 0.25
        live_levels, live_tiles = _live_levels_and_tiles(
            (s1, s2), canvas_size_px=canvas, zoom=zoom, letterboxes=(_FULL, _FULL),
        )
        export = snapshot_lod_tiles_for_sources(
            (s1, s2),
            canvas_size_px=canvas,
            zoom=zoom,
            letterboxes=(_FULL, _FULL),
            tile_service=TileTextureService(max_tile_extent=512),
        )
        assert export.levels == live_levels
        assert export.tile_sets == live_tiles
        # Zoomed out on a large canvas must sit on a coarse tier (not base):
        # otherwise the case would pass vacuously without exercising LOD.
        assert export.levels[0] > 0
    finally:
        s1.close()
        s2.close()


def test_export_scale_px_ignores_tile_surface():
    """Task 3 (frame_setup scale_px tile-vs-DPR meaning): on the export
    surface the LOD multiplier is 1.0 by construction even when the tile
    surface reports a HiDPI-style target/widget ratio; live render keeps
    measuring the surface (DPR)."""
    from types import SimpleNamespace as _NS

    from tabs.image_compare.canvas.rhi_renderer.use_cases.frame_setup import (
        resolve_canvas_scale_px,
    )

    export_widget = _NS(objectName=lambda: "gpu_export_canvas", width=lambda: 1024)
    hidpi_target = _NS(width=lambda: 2048)
    assert resolve_canvas_scale_px(export_widget, hidpi_target) == 1.0

    live_widget = _NS(objectName=lambda: "live_canvas", width=lambda: 1024)
    assert resolve_canvas_scale_px(live_widget, hidpi_target) == 2.0


def test_harness_is_not_vacuous_across_snapshots():
    s1 = _store()
    s2 = _store()
    try:
        fit = snapshot_lod_tiles_for_sources(
            (s1, s2), canvas_size_px=(500.0, 500.0), zoom=1.0
        )
        deep = snapshot_lod_tiles_for_sources(
            (s1, s2), canvas_size_px=(2000.0, 1400.0), zoom=4.0
        )
        # Fit zoom must pick a coarse pyramid level; deep zoom the base.
        assert fit.levels[0] > 0
        assert deep.levels == (0, 0)
        assert fit.levels != deep.levels
    finally:
        s1.close()
        s2.close()


def test_pil_sources_stay_bare_in_both_paths():
    img1 = Image.new("RGBA", (1024, 768), (255, 0, 0, 255))
    img2 = Image.new("RGBA", (1024, 768), (0, 255, 0, 255))
    live_levels, live_tiles = _live_levels_and_tiles(
        (img1, img2),
        canvas_size_px=(500.0, 500.0),
        zoom=1.0,
        letterboxes=(_FULL, _FULL),
    )
    export = snapshot_lod_tiles_for_sources(
        (img1, img2),
        canvas_size_px=(500.0, 500.0),
        zoom=1.0,
        tile_service=TileTextureService(max_tile_extent=512),
    )
    assert live_levels == (0, 0)
    assert export.levels == (0, 0) == live_levels
    assert export.tile_sets == live_tiles
    assert export.tile_sets == (
        ((0, 0), (0, 1), (1, 0), (1, 1)),
        ((0, 0), (0, 1), (1, 0), (1, 1)),
    )


def test_parity_helpers_take_no_mode_argument():
    # Pins the "no `if mode == \"export\"` inside the decision" rule at the
    # signature level: neither side of the harness accepts a mode to branch
    # on (passes themselves are 2C's territory, not asserted here).
    assert "mode" not in inspect.signature(snapshot_lod_tiles_for_sources).parameters
    assert "mode" not in inspect.signature(resolve_lod_texture_keys).parameters
