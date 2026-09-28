"""Stale-guard at LOD-resolve + fallback call sites (pyramid wave-A2).

Every test asserts *identity* (which bytes/store a key samples), never
mere presence: an unbuilt, evicted or stale level must resolve to a gap
(``None`` / native fallback), never to a neighbor level's payload, and a
reunified base (fresh generation) must never alias live entries.
"""

from types import SimpleNamespace

import time

import numpy as np
import pytest
from PIL import Image

from engine.cache.lod import LevelKey
from engine.store import pyramid_registry
from engine.store.tiled_pixel_store import TiledPixelStore


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
    return TiledPixelStore.from_pil(Image.fromarray(arr, mode="RGBA"))


def _ic_widget(source_0, source_1=None):
    return SimpleNamespace(
        texture_ids=["stored_0", "stored_1"],
        _source_texture_ids=["source_0", "source_1"],
        _diff_source_texture_id="diff",
        runtime_state=SimpleNamespace(
            _stored_pil_images=[None, None],
            _source_pil_images=[source_0, source_1],
            _diff_source_pil_image=None,
        ),
    )


def test_level_if_built_fails_closed_no_raise():
    """Out-of-range and closed levels collapse to None (gap), never raise."""
    store = _store(4096, 2048)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    assert pyramid.level_if_built(99) is None
    assert pyramid.level_if_built(-1) is None
    assert pyramid.level_if_built(True) is None  # type: ignore[arg-type]
    # Evict a middle level: sampling it must gap, not serve a neighbor.
    pyramid.level(1).close()
    assert pyramid.is_level_built(1) is False
    assert pyramid.level_if_built(1) is None
    # Closing the base invalidates the whole pyramid: sampling must gap,
    # never serve bytes from a dead level.
    store.close()
    assert pyramid.valid is False
    assert pyramid.best_pixels((0, 0, 4096, 2048), 0.1) is None


def test_ic_sample_guard_generation_mismatch_gaps():
    """A LevelKey from a previous base generation samples nothing live."""
    from tabs.image_compare.canvas.rhi_renderer.residency import (
        _pil_image_for_texture_key,
    )

    store = _store(4096, 2048)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    widget = _ic_widget(store)
    live = _pil_image_for_texture_key(widget, LevelKey("source_0", 1, 0))
    assert live is pyramid.level_if_built(1)
    # Same (base, level), foreign generation: gap, and specifically not
    # any live level store (no aliasing, no neighbor payload).
    stale = _pil_image_for_texture_key(widget, LevelKey("source_0", 1, 999))
    assert stale is None
    for k in range(pyramid.level_count):
        assert stale is not pyramid.level_if_built(k)
    store.close()


def test_ic_resolve_use_race_closed_level_gaps_no_raise():
    """Level closed between pick and sample: gap, no raise, no neighbor."""
    from tabs.image_compare.canvas.rhi_renderer.residency import (
        _pil_image_for_texture_key,
        resolve_lod_texture_keys,
    )

    store = _store(8192, 8192)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    base_image = SimpleNamespace(
        zoom=1.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )
    keys = resolve_lod_texture_keys(
        ("source_0", "source_1"), (store, store), base_image, (1000.0, 1000.0)
    )
    assert isinstance(keys[0], LevelKey) and keys[0].level == 3
    assert keys[0].generation == pyramid.generation
    # The race: the picked level dies before the sample lands.
    pyramid.level(3).close()
    widget = _ic_widget(store)
    assert _pil_image_for_texture_key(widget, keys[0]) is None
    # Resolve itself now falls back to a *built* level key, never the dead
    # level and never a neighbor's content under the dead level's identity.
    retry = resolve_lod_texture_keys(
        ("source_0", "source_1"), (store, store), base_image, (1000.0, 1000.0)
    )
    if isinstance(retry[0], LevelKey):
        assert retry[0].level != 3
        assert _pil_image_for_texture_key(widget, retry[0]) is pyramid.level_if_built(
            retry[0].level
        )
    else:
        assert retry[0] == "source_0"
    store.close()


def test_ic_commit_drops_stale_baseline_immediately():
    """A committed key with a dead generation re-commits fresh, no settle wait."""
    from tabs.image_compare.canvas.rhi_renderer.use_cases.lod_commit import (
        commit_lod_keys,
    )
    from engine.cache.image_identity import image_uid

    store_a = _store(8192, 8192, color=(10, 20, 30))
    store_b = _store(8192, 8192, color=(200, 100, 50))
    pyramid_registry.ensure_pyramid(store_a).build_all()
    pyramid_registry.ensure_pyramid(store_b).build_all()
    sources = (store_a, store_b)
    renderer = SimpleNamespace(
        _lod_pending_keys=None,
        _lod_pending_since=0.0,
        # Stale baseline: right (base, level), dead generation.
        _lod_committed_keys=(LevelKey("a", 3, 999), LevelKey("b", 3, 999)),
        _lod_committed_source_ids=(image_uid(store_a), image_uid(store_b)),
    )
    base_image = SimpleNamespace(
        zoom=1.0,
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
        use_hires=False,
    )
    # Fresh pending timestamp: the settle window alone would hold the stale
    # baseline; only the stale verdict may force the commit.
    renderer._lod_pending_since = time.monotonic()
    committed, source_changed = commit_lod_keys(
        renderer, ("a", "b"), sources, base_image, (1000.0, 1000.0)
    )
    assert source_changed is False
    assert committed[0].generation == pyramid_registry.pyramid_for(store_a).generation
    assert committed[0] != LevelKey("a", 3, 999)
    store_a.close()
    store_b.close()


def test_ic_rekeyed_lookup_preserves_generation(monkeypatch):
    """Fallback rekey mapping keeps the key's generation (no live-alias gap)."""
    import tabs.image_compare.canvas.rhi_renderer.use_cases.fallback as fallback_mod

    captured = {}

    def _fake_build(tile_service, texture_keys, base_image, **kwargs):
        captured["keys"] = texture_keys
        return []

    monkeypatch.setattr(
        fallback_mod, "build_array_draw_plan", _fake_build
    )
    renderer = SimpleNamespace(
        _last_good_texture_keys=("stored_0", "stored_1"),
        _last_good_diff_key=None,
        _prev_sources_is_same=None,
        _content_swap_active=False,
        resources=SimpleNamespace(
            residency=SimpleNamespace(last_uploaded_count=0)
        ),
    )
    base_image = SimpleNamespace(
        letterbox1=(0.0, 0.0, 1.0, 1.0),
        letterbox2=(0.0, 0.0, 1.0, 1.0),
    )
    tile_service = SimpleNamespace(grid_for=lambda key: None)
    current = [SimpleNamespace(rect1=(0, 0, 4, 4), rect2=(0, 0, 4, 4))]
    new_last_good, _plan = fallback_mod.resolve_fallback_plan(
        renderer,
        tile_service=tile_service,
        texture_keys=(LevelKey("stored_0", 1, 7), "stored_1"),
        diff_source_key=None,
        base_image=base_image,
        sampler_name="sampler",
        viewport_zoom=None,
        viewport_offset=None,
        main_more_pending=True,
        current_array_plan=current,
        source_changed=False,
        rekeyed={"stored_0": ("_prev_content", "stored_0", 0)},
    )
    prior = captured["keys"]
    assert prior[0].base == ("_prev_content", "stored_0", 0)
    assert prior[0].level == 1
    assert prior[0].generation == 7
    assert new_last_good[0][0] == prior[0]
    assert renderer._content_swap_active is False


def _mc_layer(zoom):
    return SimpleNamespace(
        rect_fb=(0, 0, 800, 600), fit_x=1.0, fit_y=1.0, zoom=zoom
    )


def test_mc_lod_unbuilt_level_falls_back_native_never_neighbor():
    """MC resolve of a dead level returns the native base, not another level."""
    from tabs.multi_compare.scene.passes.residency import lod_key_and_source

    store = _store(8192, 8192)
    pyramid_registry.ensure_pyramid(store).build_all()
    slot_lod_keys: dict = {}
    key, source = lod_key_and_source(4, store, _mc_layer(1.0), slot_lod_keys)
    assert key == LevelKey(4, 3, 0)
    assert source is pyramid_registry.pyramid_for(store).level_if_built(3)
    # The picked level dies before use: fall back to native, never sideways.
    pyramid_registry.pyramid_for(store).level(3).close()
    key2, source2 = lod_key_and_source(4, store, _mc_layer(1.0), slot_lod_keys)
    assert key2 == 4
    assert source2 is store
    store.close()


def test_mc_zoom_remap_reresolve_no_cross_binding():
    """Two zooms resolve two levels; each key samples exactly its own level."""
    from tabs.multi_compare.scene.passes.residency import lod_key_and_source

    store = _store(8192, 8192)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    slot_lod_keys: dict = {}
    key_far, src_far = lod_key_and_source(4, store, _mc_layer(1.0), slot_lod_keys)
    key_near, src_near = lod_key_and_source(4, store, _mc_layer(4.0), slot_lod_keys)
    assert isinstance(key_far, LevelKey) and isinstance(key_near, LevelKey)
    assert key_far.level != key_near.level
    assert key_far.generation == key_near.generation == pyramid.generation
    assert src_far is pyramid.level_if_built(key_far.level)
    assert src_near is pyramid.level_if_built(key_near.level)
    assert src_far is not src_near
    assert src_far.size == pyramid.level_if_built(key_far.level).size
    assert src_near.size == pyramid.level_if_built(key_near.level).size
    store.close()


def test_mc_stale_key_verdict_no_aliasing():
    """Generation bump / swept pyramid / unbuilt level all verdict stale."""
    from tabs.multi_compare.scene.passes.residency import is_lod_key_stale

    store = _store(8192, 8192)
    pyramid = pyramid_registry.ensure_pyramid(store)
    pyramid.build_all()
    live_gen = pyramid.generation
    assert is_lod_key_stale(LevelKey(4, 1, live_gen), store) is False
    assert is_lod_key_stale(4, store) is False  # bare native key never stale
    assert is_lod_key_stale(LevelKey(4, 1, live_gen + 1), store) is True
    assert is_lod_key_stale(LevelKey(4, 99, live_gen), store) is True
    assert is_lod_key_stale(LevelKey(4, 1, live_gen), Image.new("RGBA", (8, 8))) is True
    # Base closed -> pyramid swept -> any level key for it is stale (gap,
    # never an alias onto whatever reuses the slot next).
    stale_key = LevelKey(4, 1, live_gen)
    store.close()
    assert pyramid_registry.pyramid_for(store) is None
    assert is_lod_key_stale(stale_key, store) is True
