"""E1 core tests for the engine single-image tiled view.

Non-blind by construction: the residency path is spied through
``TileResidencyRealizerBase.realize_specs``, the draw is spied through
``engine.gpu.tiled_image_view.record_array_draw``, and the per-index identity
assertions would fail if an instance sampled a neighbour's layer or if
``covered`` degenerated to "at least one tile resident".

A tiny PIL image is used as the pixel source (``crop_apron_tile`` accepts any
``.size``/``.crop()`` source), and ``_LIVE_TILE_EXTENT`` is shrunk so an 8x8
image yields a 2x2 tile grid without touching the GPU.
"""

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import engine.gpu.tiled_image_view as tiv
from engine.cache.draw_plans import build_slot_plan_tiles
from engine.cache.residency import TileResidencyRealizerBase
from engine.gpu.tiled_image_view import (
    _UNIFORM_BLOCK_SIZE,
    LodPolicy,
    SingleImageTiledView,
    TiledImageSource,
    TiledImageView,
    TiledViewHooks,
    contain_fit_scale,
    pack_tiled_image_view_uniforms,
)

_KEY = "src"


class _FakeCommandBuffer:
    def __init__(self) -> None:
        self.updates: list = []

    def resourceUpdate(self, batch) -> None:
        self.updates.append(batch)


class _NoPrefetch:
    def warm(self, *args, **kwargs) -> bool:
        return False


def _make_view(monkeypatch, extent: int = 4):
    monkeypatch.setattr(tiv, "_LIVE_TILE_EXTENT", extent)
    rhi = SimpleNamespace(
        clipSpaceCorrMatrix=lambda: SimpleNamespace(data=lambda: [1.0] * 16),
        nextResourceUpdateBatch=lambda: object(),
    )
    view = SingleImageTiledView(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda name: None,
        load_shader=lambda name: None,
        name_prefix="test",
    )
    # No live RHI: skip real buffer creation, and disable background warm
    # workers that would otherwise touch the PIL source off-thread.
    view._vertex_buffer = object()
    view._realizer._prefetcher = _NoPrefetch()
    return view, rhi


def _install_upload_stub(view, allowed=None):
    uploaded: list = []

    def stub(tile_service, key, index, tile_image, updates, dirty_layers, region):
        if allowed is not None and index not in allowed:
            return
        tile_service.mark_resident(key, index, byte_size=16, content_size=(2, 2))
        uploaded.append(index)

    view._realizer._upload_tile = stub
    return uploaded


def _install_draw_spy(monkeypatch):
    calls: list = []

    def spy(command_buffer, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(tiv, "record_array_draw", spy)
    return calls


def _install_realize_spy(monkeypatch):
    calls: list = []
    original = TileResidencyRealizerBase.realize_specs

    def spy(self, tile_service, specs, updates, **kwargs):
        calls.append(specs)
        return original(self, tile_service, specs, updates, **kwargs)

    monkeypatch.setattr(TileResidencyRealizerBase, "realize_specs", spy)
    return calls


# --- E2: LOD policy + fallback-under-tiles ---------------------------------

_LEVEL1_KEY = "src1"


def _multi_source() -> TiledImageSource:
    """16x16 base (level 0, 4x4 grid at extent 4) + 8x8 level 1 (2x2 grid).

    ``levels`` is coarsest-first/finest-last; the last entry is level 0 and
    reuses the base key so the finest level is the single-level key.
    """
    store0 = Image.new("RGBA", (16, 16))
    store1 = Image.new("RGBA", (8, 8))
    return TiledImageSource(
        key="src0",
        store=store0,
        levels=((_LEVEL1_KEY, store1), ("src0", store0)),
    )


def _install_keyed_upload_stub(view, *, allow=None, on_upload=None):
    uploaded: list = []

    def stub(tile_service, key, index, tile_image, updates, dirty_layers, region):
        if allow is not None and not allow(key, index):
            return
        tile_service.mark_resident(key, index, byte_size=16, content_size=(2, 2))
        uploaded.append((key, index))
        if on_upload is not None:
            on_upload(key, index, dirty_layers)

    view._realizer._upload_tile = stub
    return uploaded


def _layers_for(view, key) -> set:
    service = view.tile_service
    return {service.slot_for(key, index)[1] for index in service.resident_tiles(key)}


def _render_at(view, zoom, policy=None):
    return view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=TiledImageView(zoom=zoom, pan=(0.0, 0.0), fb_size=(16, 16)),
        hooks=TiledViewHooks(lods=policy),
    )


def test_multi_level_immediate_picks_level_for_zoom(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    _install_keyed_upload_stub(view)
    draw_calls = _install_draw_spy(monkeypatch)

    near = _render_at(view, 1.0, LodPolicy("immediate"))
    service = view.tile_service
    assert service.resident_tiles(_LEVEL1_KEY) == set()
    assert near.covered is True
    assert {inst.layer for inst in draw_calls[-1]["instances"]} == _layers_for(
        view, "src0"
    )

    far = _render_at(view, 0.25, LodPolicy("immediate"))
    assert len(service.resident_tiles(_LEVEL1_KEY)) == 4
    assert {inst.layer for inst in draw_calls[-1]["instances"]} == _layers_for(
        view, _LEVEL1_KEY
    )
    assert far.covered is True


def test_multi_level_settle_holds_until_target_resident(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    allowed = {"src0"}
    _install_keyed_upload_stub(view, allow=lambda key, index: key in allowed)
    draw_calls = _install_draw_spy(monkeypatch)
    policy = LodPolicy("settle", 0)

    _render_at(view, 1.0, policy)
    held = _render_at(view, 0.25, policy)

    service = view.tile_service
    assert service.resident_tiles(_LEVEL1_KEY) == set()
    assert {inst.layer for inst in draw_calls[-1]["instances"]} <= _layers_for(
        view, "src0"
    )
    assert held.covered is False  # target (level 1) not resident -> held level

    allowed.add(_LEVEL1_KEY)
    settled = _render_at(view, 0.25, policy)
    assert len(service.resident_tiles(_LEVEL1_KEY)) == 4
    assert {inst.layer for inst in draw_calls[-1]["instances"]} == _layers_for(
        view, _LEVEL1_KEY
    )
    assert settled.covered is True


def test_multi_level_fallback_under_incomplete_target(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    # Level 1's (1, 1) tile can never upload -> target stays incomplete.
    _install_keyed_upload_stub(
        view,
        allow=lambda key, index: key != _LEVEL1_KEY or index != (1, 1),
    )
    draw_calls = _install_draw_spy(monkeypatch)

    _render_at(view, 1.0, LodPolicy("immediate"))
    partial = _render_at(view, 0.25, LodPolicy("immediate"))

    service = view.tile_service
    assert len(service.resident_tiles(_LEVEL1_KEY)) == 3
    drawn_layers = {inst.layer for inst in draw_calls[-1]["instances"]}
    assert drawn_layers & _layers_for(view, _LEVEL1_KEY)  # partial target
    assert drawn_layers & _layers_for(view, "src0")  # fallback underneath
    assert partial.drawn is True
    assert partial.covered is False


def test_settle_ms_debounces_target_promotion(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    _install_keyed_upload_stub(view)
    _install_draw_spy(monkeypatch)

    clock = {"seconds": 1000.0}
    monkeypatch.setattr(tiv.time, "perf_counter", lambda: clock["seconds"])

    policy = LodPolicy("settle", 50)
    _render_at(view, 1.0, policy)
    assert view._render_level == 0

    held = _render_at(view, 0.25, policy)  # target resident, debounce not met
    assert held.covered is False
    assert view._render_level == 0

    clock["seconds"] += 0.06  # > 50 ms
    settled = _render_at(view, 0.25, policy)
    assert settled.covered is True
    assert view._render_level == 1


def test_multi_level_realizes_target_and_fallback_in_one_call(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    _install_keyed_upload_stub(
        view,
        allow=lambda key, index: key != _LEVEL1_KEY or index != (1, 1),
    )
    _install_draw_spy(monkeypatch)
    realize_calls = _install_realize_spy(monkeypatch)

    _render_at(view, 1.0, LodPolicy("immediate"))
    _render_at(view, 0.25, LodPolicy("immediate"))

    assert len(realize_calls) == 2
    assert {spec.key for spec in realize_calls[1]} == {"src0", _LEVEL1_KEY}
    assert len(realize_calls[1]) == 2

    source = Path(tiv.__file__).read_text(encoding="utf-8")
    assert "time.monotonic" not in source
    assert "select_upload_batch" not in source
    assert "_upload_visible_tiles" not in source


def test_multi_level_promotion_requires_cascade_drained(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(_multi_source())
    _install_keyed_upload_stub(
        view,
        on_upload=lambda key, index, dirty_layers: dirty_layers.setdefault(
            0, set()
        ).add(0),
    )
    _install_draw_spy(monkeypatch)

    state = {"deferred": True}

    def fake_mips(command_buffer, vertex_buffer, dirty_layers, budget):
        return {0: {0}} if state["deferred"] else {}

    monkeypatch.setattr(
        view._mip_cascade, "generate_all_dirty_mips", fake_mips
    )

    # Level 0 uploads with deferred mips -> cascade pending -> not covered,
    # no baseline promoted yet.
    assert _render_at(view, 1.0, LodPolicy("immediate")).covered is False
    assert view._fallback_level is None

    state["deferred"] = False
    assert _render_at(view, 1.0, LodPolicy("immediate")).covered is True
    assert view._fallback_level == 0

    # Target level 1 fully resident but its mips deferred -> must NOT promote
    # the baseline and must not report covered.
    state["deferred"] = True
    deferred = _render_at(view, 0.25, LodPolicy("immediate"))
    assert deferred.covered is False
    assert view._fallback_level == 0

    state["deferred"] = False
    promoted = _render_at(view, 0.25, LodPolicy("immediate"))
    assert promoted.covered is True
    assert view._fallback_level == 1


def test_render_one_instance_per_visible_tile_and_one_draw(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(TiledImageSource(key=_KEY, store=Image.new("RGBA", (8, 8))))
    _install_upload_stub(view)
    draw_calls = _install_draw_spy(monkeypatch)

    result = view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=TiledImageView(zoom=1.0, pan=(0.0, 0.0), fb_size=(8, 8)),
    )

    assert result.drawn is True
    assert result.instances == 4
    assert result.covered is True
    assert len(draw_calls) == 1
    assert len(draw_calls[0]["instances"]) == 4


def test_residency_routes_through_realize_specs_not_a_private_loop(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(TiledImageSource(key=_KEY, store=Image.new("RGBA", (8, 8))))
    _install_upload_stub(view)
    _install_draw_spy(monkeypatch)
    realize_calls = _install_realize_spy(monkeypatch)

    view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=TiledImageView(zoom=1.0, pan=(0.0, 0.0), fb_size=(8, 8)),
    )

    assert len(realize_calls) == 1
    assert [spec.key for spec in realize_calls[0]] == [_KEY]

    # The module must not carry its own upload loop/batch selection: the
    # shared realizer owns that. A private loop would need one of these.
    source = Path(tiv.__file__).read_text(encoding="utf-8")
    assert "time.monotonic" not in source
    assert "select_upload_batch" not in source
    assert "_upload_visible_tiles" not in source


def test_instance_for_index_uses_its_own_layer_never_a_neighbour(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(TiledImageSource(key=_KEY, store=Image.new("RGBA", (8, 8))))
    uploaded = _install_upload_stub(view)
    draw_calls = _install_draw_spy(monkeypatch)

    view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=TiledImageView(zoom=1.0, pan=(0.0, 0.0), fb_size=(8, 8)),
    )

    service = view.tile_service
    layer_by_index = {index: service.slot_for(_KEY, index)[1] for index in uploaded}
    assert len(set(layer_by_index.values())) == 4

    plan = build_slot_plan_tiles(service, _KEY, (0.0, 0.0), (1.0, 1.0), 1.0)
    index_by_rect = {tuple(round(v, 9) for v in tile.rect): tile.index for tile in plan}

    instances = draw_calls[0]["instances"]
    assert len(instances) == len(plan)
    seen_layers: set[int] = set()
    for instance in instances:
        index = index_by_rect[tuple(round(v, 9) for v in instance.tile_rect)]
        assert instance.layer == layer_by_index[index]
        seen_layers.add(instance.layer)
    # Bijection: every instance carries a distinct own-tile layer.
    assert seen_layers == set(layer_by_index.values())


def test_covered_false_when_any_visible_tile_missing(monkeypatch):
    view, _ = _make_view(monkeypatch)
    view.set_source(TiledImageSource(key=_KEY, store=Image.new("RGBA", (8, 8))))
    # (1, 1) is refused by the stub, so it can never become resident.
    _install_upload_stub(view, allowed={(0, 0), (0, 1), (1, 0)})
    _install_draw_spy(monkeypatch)
    render_view = TiledImageView(zoom=1.0, pan=(0.0, 0.0), fb_size=(8, 8))

    partial = view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=render_view,
    )
    assert partial.drawn is True
    assert partial.instances == 3
    assert partial.covered is False

    _install_upload_stub(view, allowed=None)
    complete = view.render(
        _FakeCommandBuffer(),
        updates=object(),
        target=object(),
        clear_color=None,
        view=render_view,
    )
    assert complete.instances == 4
    assert complete.covered is True


def test_pack_uniforms_layout():
    view = TiledImageView(zoom=2.0, pan=(0.25, -0.5), fb_size=(100, 50), fit=(0.5, 1.0))
    blob = pack_tiled_image_view_uniforms(view, letterbox=(0.1, 0.2, 0.8, 0.6))

    # Slot-pass UBuf is mat4 mvp + vec4 letterbox (80 bytes); the per-tile
    # pan/fit/zoom live in the instance layout, not the uniform.
    assert len(blob) == _UNIFORM_BLOCK_SIZE == 80
    assert struct.unpack_from("<16f", blob, 0) == tiv._IDENTITY_MATRIX16
    assert struct.unpack_from("<4f", blob, 64) == pytest.approx((0.1, 0.2, 0.8, 0.6))

    patched = pack_tiled_image_view_uniforms(view, clip_matrix=[2.0] + [0.0] * 15)
    assert struct.unpack_from("<f", patched, 0)[0] == 2.0

    with pytest.raises(ValueError):
        pack_tiled_image_view_uniforms(view, clip_matrix=[1.0] * 15)


def test_contain_fit_scale_matches_reference():
    assert contain_fit_scale((1000, 500), 800, 800) == (1.0, 0.5)
    assert contain_fit_scale((500, 1000), 800, 800) == (0.5, 1.0)
    assert contain_fit_scale((0, 0), 800, 800) == (1.0, 1.0)
    assert contain_fit_scale((800, 800), 800, 800) == (1.0, 1.0)
