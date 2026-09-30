"""Demand-level engine API: ensure_level + invalidate_levels (lazy E1).

GIMP-style pull over PyramidPixelStore: build only the levels the current
view needs, drop superseded ones on damage, fail open everywhere. The QL
pilot (tabs/image_gallery/.../preview_canvas _ql_needed_level/_ql_abort_fn)
consumes these shapes via the coordinator in E2 — signatures here are
frozen: ensure_level(pyramid, k, should_abort=None) -> bool,
invalidate_levels(pyramid, from_k=None) -> int, select_level reused
untouched from engine.cache.lod.
"""

import numpy as np
import pytest
from PIL import Image

from engine.cache.lod import select_level
from engine.store import pyramid_registry
from engine.store.pyramid_pixel_store import (
    ensure_level,
    estimate_total_levels,
    invalidate_levels,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    pyramid_registry.clear()
    yield
    pyramid_registry.clear()


def _store(width, height, color=(10, 20, 30)):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 0] = color[0]
    arr[:, :, 1] = color[1]
    arr[:, :, 2] = color[2]
    arr[:, :, 3] = 255
    return TiledPixelStore_from_pil(arr)


def TiledPixelStore_from_pil(arr):
    from engine.store.tiled_pixel_store import TiledPixelStore

    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))


def _big_store():
    # 8192px edge -> estimate_total_levels == 4 (levels 0..3), so a demand
    # build of k=1 must stop at 2 levels and never run the full pyramid.
    return _store(8192, 8192)


def test_demand_builds_exactly_needed_levels_never_full():
    store = _big_store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert estimate_total_levels(8192, 8192) > 2  # full pyramid is bigger
    calls = []

    orig = pyramid.build_next_level

    def _spy(should_abort=None):
        calls.append(1)
        return orig(should_abort=should_abort)

    pyramid.build_next_level = _spy  # type: ignore[method-assign]
    try:
        assert ensure_level(pyramid, 1) is True
    finally:
        pyramid.build_next_level = orig  # type: ignore[method-assign]
    assert pyramid.level_count == 2  # base + level 1, nothing past k
    assert len(calls) <= 2
    assert pyramid.is_level_built(1) is True
    assert pyramid.is_level_built(2) is False
    # Already built -> True with zero further builds.
    calls.clear()
    pyramid.build_next_level = _spy  # type: ignore[method-assign]
    try:
        assert ensure_level(pyramid, 1) is True
    finally:
        pyramid.build_next_level = orig  # type: ignore[method-assign]
    assert calls == []
    assert pyramid.level_count == 2
    store.close()


def test_best_pixels_on_unbuilt_level_gaps():
    store = _big_store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert pyramid.is_level_built(1) is False
    # Unbuilt world: sampling through the built-clamped level must gap
    # rather than serve a neighbor's bytes.
    assert pyramid.level_if_built(1) is None
    assert pyramid.best_pixels((0, 0, 8192, 8192), 0.1) is not None  # level 0 serves
    # Simulate a deeper need than built: best_level_for_scale over the FULL
    # count disagrees with the built clamp — the sampler must not invent it.
    need = select_level(0.1, estimate_total_levels(8192, 8192))
    assert need > 0
    assert pyramid.level_if_built(need) is None
    store.close()


def test_damage_drops_and_rebuilds_on_demand():
    store = _big_store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert ensure_level(pyramid, 2) is True
    assert pyramid.level_count == 3
    dropped = invalidate_levels(pyramid, from_k=1)
    assert dropped == 2
    assert pyramid.level_count == 1
    assert pyramid.is_level_built(1) is False
    assert pyramid.level_if_built(1) is None
    # Generations stay consistent: the pyramid is still valid against its base.
    assert pyramid.valid is True
    assert pyramid.generation == store.generation
    # Rebuild on demand lands exactly level 1 again.
    assert ensure_level(pyramid, 1) is True
    assert pyramid.level_count == 2
    assert pyramid.is_level_built(1) is True
    store.close()


def test_damage_default_drops_all_but_base():
    store = _big_store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert ensure_level(pyramid, 2) is True
    dropped = invalidate_levels(pyramid)
    assert dropped == 2
    assert pyramid.level_count == 1
    assert pyramid.is_level_built(0) is True
    # Empty damage is a no-op zero.
    assert invalidate_levels(pyramid) == 0
    assert invalidate_levels(pyramid, from_k=99) == 0
    store.close()


def test_abort_mid_build_leaves_consistent_state():
    store = _big_store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    before = pyramid.level_count
    # Abort immediately: nothing built, no exception, level stays unbuilt.
    assert ensure_level(pyramid, 1, should_abort=lambda: True) is False
    assert pyramid.level_count == before
    assert pyramid.is_level_built(1) is False
    assert pyramid.valid is True
    # Abort mid-build (after the first strip check): the partial level is
    # discarded by build_next_level, so the pyramid is still consistent.
    ticks = []

    def _abort_mid():
        ticks.append(1)
        return len(ticks) > 2

    assert ensure_level(pyramid, 2, should_abort=_abort_mid) is False
    assert pyramid.is_level_built(2) is False
    assert pyramid.valid is True
    # Recovery: a clean demand build still lands afterwards.
    assert ensure_level(pyramid, 1) is True
    assert pyramid.is_level_built(1) is True
    store.close()


def test_invalid_k_fail_open_false_never_raises():
    store = _store(512, 512)
    pyramid = pyramid_registry.ensure_pyramid(store)
    for bad in (-1, True, False, "1", None, 1.5, (1,)):
        assert ensure_level(pyramid, bad) is False  # type: ignore[arg-type]
    assert ensure_level(None, 1) is False  # type: ignore[arg-type]
    assert ensure_level(object(), 1) is False  # type: ignore[arg-type]
    # Unreachable level on a complete pyramid: False, never raises, and no
    # phantom level appears.
    assert pyramid.is_complete() is True  # 512px edge: base only
    assert ensure_level(pyramid, 99) is False
    assert pyramid.level_count == 1
    # Invalid damage input: fail-open no-op zero.
    assert invalidate_levels(None) == 0  # type: ignore[arg-type]
    assert invalidate_levels(pyramid, from_k=True) == 0  # type: ignore[arg-type]
    assert invalidate_levels(pyramid, from_k="x") == 0  # type: ignore[arg-type]
    store.close()
