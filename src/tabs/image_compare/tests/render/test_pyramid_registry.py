"""Pyramid registry lifecycle: uid keying, generation invalidation, build races."""

import numpy as np
import pytest
from PIL import Image

from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore


@pytest.fixture(autouse=True)
def _clean_registry():
    pyramid_registry.clear()
    yield
    pyramid_registry.clear()


def _store(width=2048, height=2048):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))


def test_ensure_returns_none_for_non_tiled_sources():
    assert pyramid_registry.ensure_pyramid(Image.new("RGBA", (64, 64))) is None
    assert pyramid_registry.ensure_pyramid(None) is None


def test_ensure_dedups_by_store_uid():
    store = _store()
    p1 = pyramid_registry.ensure_pyramid(store)
    p2 = pyramid_registry.ensure_pyramid(store)
    assert p1 is p2
    assert pyramid_registry.pyramid_for(store) is p1
    store.close()


def test_small_store_pyramid_is_already_complete():
    store = _store(512, 512)
    pyramid = pyramid_registry.ensure_pyramid(store)
    assert pyramid.is_complete()
    assert pyramid.level_count == 1
    store.close()


def test_closed_base_swept_on_access():
    store = _store()
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    derived = pyramid.level(1)
    store.close()
    assert pyramid_registry.pyramid_for(store) is None
    # Derived levels are closed with the entry; base is untouched (already closed).
    assert not derived.is_open
    assert pyramid_registry.ensure_pyramid(store) is None


def test_ensure_sweeps_stale_entries_of_other_stores():
    stale = _store()
    pyramid = pyramid_registry.ensure_pyramid(stale)
    pyramid.build_all()
    derived = pyramid.level(1)
    stale.close()

    fresh = _store(512, 512)
    pyramid_registry.ensure_pyramid(fresh)
    assert not derived.is_open
    fresh.close()


def test_reunification_task_id_aborts_build():
    from tabs._shared.pyramid import _pyramid_build_loop
    from tabs.image_compare.pipeline.abort import AbortSignal

    store = _store(4096, 4096)
    pyramid = pyramid_registry.ensure_pyramid(store)

    stale = AbortSignal()
    stale.abort()
    fresh = AbortSignal()
    _pyramid_build_loop(pyramid, stale.is_aborted, uid=0, total_levels=1)
    assert pyramid.level_count == 1  # stale signal: aborted before any level

    _pyramid_build_loop(pyramid, fresh.is_aborted, uid=0, total_levels=3)
    assert pyramid.is_complete()
    assert pyramid.level_count == 3
    store.close()


def test_build_task_reports_each_level():
    from tabs._shared.pyramid import _pyramid_build_loop
    from tabs.image_compare.pipeline.abort import AbortSignal

    store = _store(4096, 4096)
    pyramid = pyramid_registry.ensure_pyramid(store)
    levels = []
    sig = AbortSignal()
    _pyramid_build_loop(
        pyramid, sig.is_aborted, uid=0, total_levels=2, progress_callback=levels.append
    )
    assert len(levels) == 2
    store.close()
