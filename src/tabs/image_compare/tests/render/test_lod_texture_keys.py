"""LOD texture-key resolution: level substitution, passthrough, live/export parity."""

from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from shared.image_processing import pyramid_registry
from shared.image_processing.tiled_pixel_store import TiledPixelStore
from shared.rendering.lod import LevelKey
from tabs.image_compare.canvas.rhi_renderer.draw_plan import resolve_lod_texture_keys


@pytest.fixture(autouse=True)
def _clean_registry():
    pyramid_registry.clear()
    yield
    pyramid_registry.clear()


def _store(width, height):
    arr = np.zeros((height, width, 4), dtype=np.uint8)
    arr[:, :, 3] = 255
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))


def _base_image(zoom=1.0, letterbox=(0.0, 0.0, 1.0, 1.0)):
    return SimpleNamespace(zoom=zoom, letterbox1=letterbox, letterbox2=letterbox)


def test_pil_and_unregistered_sources_keep_bare_keys():
    store = _store(4096, 4096)  # no pyramid registered
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (Image.new("RGBA", (64, 64)), store),
        _base_image(),
        (1000.0, 1000.0),
    )
    assert keys == ("source_0", "source_1")
    store.close()


def test_fit_zoom_picks_coarse_level():
    store = _store(8192, 8192)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    assert pyramid.level_count == 4
    # 8192px source displayed at ~1000px: dest_scale ~0.122 -> level 3.
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store, store),
        _base_image(zoom=1.0),
        (1000.0, 1000.0),
    )
    assert keys == (LevelKey("source_0", 3), LevelKey("source_1", 3))
    store.close()


def test_deep_zoom_keeps_level_zero_bare_key():
    store = _store(8192, 8192)
    pyramid_registry.ensure_pyramid(store).build_all()
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store, store),
        _base_image(zoom=16.0),
        (1000.0, 1000.0),
    )
    assert keys == ("source_0", "source_1")
    store.close()


def test_partial_pyramid_clamps_to_built_levels():
    store = _store(8192, 8192)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_next_level()  # only level 1 available so far
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store, store),
        _base_image(zoom=1.0),
        (1000.0, 1000.0),
    )
    assert keys == (LevelKey("source_0", 1), LevelKey("source_1", 1))
    store.close()


def test_async_pyramid_build_desync_clamps_both_sides_to_slower_side():
    """Background pyramid builds finish per-side independently (one store's
    build_next_level can run before the other's), so at the same zoom/canvas
    the two sides can have different level_count when resolve_lod_texture_keys
    is called mid-zoom. Both sides must still resolve to the same level number
    -- draw_plan.py's tile-rect fractions are only comparable between sides
    when both grids have equal dimensions, which requires equal levels."""
    store_0 = _store(20000, 20000)
    store_1 = _store(20000, 20000)
    pyramid_0 = pyramid_registry.ensure_pyramid(store_0)
    pyramid_1 = pyramid_registry.ensure_pyramid(store_1)
    pyramid_1.build_next_level()  # store_1 has level 1 ready; store_0 does not
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store_0, store_1),
        _base_image(zoom=1.1),
        (1186.0, 645.0),
    )
    level_0 = keys[0].level if isinstance(keys[0], LevelKey) else 0
    level_1 = keys[1].level if isinstance(keys[1], LevelKey) else 0
    assert level_0 == level_1
    store_0.close()
    store_1.close()


def test_live_and_export_resolve_same_level_for_same_canvas():
    store = _store(8192, 8192)
    pyramid_registry.ensure_pyramid(store).build_all()
    args = (("source_0", "source_1"), (store, store), _base_image(zoom=1.5))
    live = resolve_lod_texture_keys(*args, (2000.0, 1400.0))
    export = resolve_lod_texture_keys(*args, (2000.0, 1400.0))
    assert live == export
    store.close()


def test_letterbox_fraction_shrinks_dest_scale():
    store = _store(8192, 8192)
    pyramid_registry.ensure_pyramid(store).build_all()
    # Full-canvas letterbox at 4000px -> dest_scale ~0.49 -> level 1;
    # half-width letterbox halves the displayed size -> level 2.
    full = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store, store),
        _base_image(letterbox=(0.0, 0.0, 1.0, 1.0)),
        (4000.0, 4000.0),
    )
    half = resolve_lod_texture_keys(
        ("source_0", "source_1"),
        (store, store),
        _base_image(letterbox=(0.25, 0.25, 0.5, 0.5)),
        (4000.0, 4000.0),
    )
    assert full == (LevelKey("source_0", 1), LevelKey("source_1", 1))
    assert half == (LevelKey("source_0", 2), LevelKey("source_1", 2))
    store.close()


def test_level_key_resolves_to_level_store_via_widget_lookup():
    from tabs.image_compare.canvas.rhi_renderer.residency import (
        _pil_image_for_texture_key,
    )

    store = _store(4096, 2048)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()

    widget = SimpleNamespace(
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        runtime_state=SimpleNamespace(
            _stored_pil_images=[None, None],
            _source_pil_images=[store, None],
            _diff_source_pil_image=None,
        ),
    )
    resolved = _pil_image_for_texture_key(widget, LevelKey("source_0", 1))
    assert resolved is pyramid.level(1)
    assert resolved.size == (2048, 1024)
    # Unbuilt level index and invalidated pyramid resolve to None.
    assert _pil_image_for_texture_key(widget, LevelKey("source_0", 5)) is None
    store.close()
    assert _pil_image_for_texture_key(widget, LevelKey("source_0", 1)) is None
