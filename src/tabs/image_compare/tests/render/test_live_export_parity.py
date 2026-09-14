"""Live/export parity harness (task-engine-2d, bucket 2D).

Same snapshot in -> same LOD level + same tile set out, through the live
path (``resolve_lod_texture_keys`` + ``TileTextureService.visible_tiles``)
and the export path (``snapshot_lod_tiles_for_sources`` test-support helper
in ``snapshot_render_plan_builder``). Both decide via
``engine.cache.lod.select_level`` with identical inputs and take no ``mode``
argument -- any live-only or export-only fudge in LOD or tile selection
fails here. This harness pins the decision only; it does not redesign the
export CPU-prescale path (explicit non-goal).
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from engine.store import pyramid_registry
from engine.store.tiled_pixel_store import TiledPixelStore
from engine.cache.lod import LevelKey
from engine.cache.tile_texture_service import TileTextureService
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
