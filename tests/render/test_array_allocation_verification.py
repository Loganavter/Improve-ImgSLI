"""The tile array must be verified, not trusted: ``create()`` can lie.

Red-before: on the pre-change tree ``ArrayResources._ensure_tile_array``
appended whatever ``newTextureArray().create()`` returned, with no
allocation probe and no capacity sink. Mesa returns True for an array it
cannot back, every render target attached to it then fails
``GL_FRAMEBUFFER_INCOMPLETE_ATTACHMENT``, and Image Compare's mip probe
(``MipCascadeNotReady``) never recovers -- black canvas at 2032 layers /
~2.9 GB on integrated Intel (2026-10-28), while the identical code renders
on a discrete GPU. These tests drive that failure through a fake RHI whose
``create()`` always succeeds but whose targets only attach below a limit.
"""

from __future__ import annotations

import pytest

from engine.cache.tile_texture_service import TileTextureService
from engine.gpu.array_budget import (
    MIN_ARRAY_LAYERS,
    array_layer_bytes,
    forget_verified_capacities,
    plan_array_capacity,
    shrink_capacity,
)
from engine.gpu.array_resources import TileArrayResourcesBase

PX = 514
PLANNED = 2032  # IC's pre-change capacity: ~2.9 GB with the mip chain


@pytest.fixture(autouse=True)
def _fresh_capacity_memory():
    forget_verified_capacities()
    yield
    forget_verified_capacities()


class _FakeTexture:
    def __init__(self, layers: int) -> None:
        self.layers = int(layers)
        self.destroyed = False

    def setName(self, _name) -> None:  # noqa: N802 - QRhiTexture API
        pass

    def create(self) -> bool:
        return True

    def destroy(self) -> None:
        self.destroyed = True


class _FakeRhi:
    """``newTextureArray`` always "succeeds"; only targets carry a limit."""

    def __init__(self) -> None:
        self.created_layers: list[int] = []

    def newTextureArray(self, _fmt, layers, _size, _samples, _flags):  # noqa: N802
        self.created_layers.append(int(layers))
        return _FakeTexture(layers)

    def backendName(self) -> str:  # noqa: N802 - QRhi API
        return "OpenGL"


def _resources(rhi: _FakeRhi, capacity: int = PLANNED) -> TileArrayResourcesBase:
    return TileArrayResourcesBase(
        rhi_getter=lambda: rhi,
        sampler_getter=lambda _name: object(),
        load_shader=lambda _name: object(),
        layer_px=PX,
        array_capacity=capacity,
        name_prefix="test",
        instance_stride=16,
        uniform_block_size=64,
        instance_attributes=[],
        vertex_shader_name="v.qsb",
        fragment_shader_name="f.qsb",
    )


def test_capacity_planner_respects_byte_cap_and_demand_floor():
    # No demand: one array should stay under the byte cap.
    roomy = plan_array_capacity(layer_px=PX)
    assert roomy == (512 * 1024 * 1024) // array_layer_bytes(PX)
    assert roomy * array_layer_bytes(PX) <= 512 * 1024 * 1024

    # Demand (the visible set one SRB-bound array must hold) is a floor.
    assert plan_array_capacity(layer_px=PX, demand_layers=867) == 867

    # Never past the backend layer limit.
    assert plan_array_capacity(layer_px=PX, demand_layers=99999) == 2048


def test_shrink_halves_down_to_the_floor_and_then_stops():
    assert shrink_capacity(2032) == 1016
    assert shrink_capacity(16) == MIN_ARRAY_LAYERS
    assert shrink_capacity(MIN_ARRAY_LAYERS) == MIN_ARRAY_LAYERS


def test_unusable_allocation_is_halved_until_the_driver_accepts_it():
    rhi = _FakeRhi()
    resources = _resources(rhi)
    adopted: list[int] = []
    resources.set_capacity_sink(adopted.append)
    # The driver "creates" every size but only backs <= 600 layers.
    resources._probe_array_target = lambda texture: texture.layers <= 600

    resources._ensure_tile_array(0)

    assert rhi.created_layers == [2032, 1016, 508]
    assert resources.array_capacity == 508
    assert adopted == [508], "the slot allocator must follow the real capacity"
    assert len(resources.tile_arrays) == 1
    assert resources.tile_arrays[0].layers == 508


def test_verification_is_the_only_shrink_trigger():
    """A verified allocation is used as planned -- no gratuitous halving."""
    rhi = _FakeRhi()
    resources = _resources(rhi)
    resources._probe_array_target = lambda _texture: True

    resources._ensure_tile_array(0)

    assert rhi.created_layers == [PLANNED]
    assert resources.array_capacity == PLANNED


def test_rebuild_on_the_same_backend_skips_the_refused_size():
    """A second resources object must not pay the failed 2.9 GB attempt again.

    Measured on the integrated-Intel repro: every canvas rebuild re-created
    the refused array, ~2 s each, because 'what this driver accepts' lived only
    on the discarded object.
    """
    first_rhi = _FakeRhi()
    first = _resources(first_rhi)
    first._probe_array_target = lambda texture: texture.layers <= 600
    first._ensure_tile_array(0)
    assert first_rhi.created_layers == [2032, 1016, 508]

    second_rhi = _FakeRhi()
    second = _resources(second_rhi)
    second._probe_array_target = lambda texture: texture.layers <= 600
    second._ensure_tile_array(0)

    assert second_rhi.created_layers == [508], "remembered capacity must be tried first"
    assert second.array_capacity == 508


def test_allocator_follows_the_verified_capacity():
    service = TileTextureService(max_array_size=PLANNED)

    assert service.set_max_array_size(508) is True
    assert service._slot_allocator.max_array_size == 508

    # A live layer above the new cap must refuse the shrink (aliasing guard).
    service._slot_allocator._slot_for_key["live"] = (0, 900)
    assert service.set_max_array_size(256) is False
    assert service._slot_allocator.max_array_size == 508


def test_unbacked_even_at_the_floor_raises_instead_of_black_rendering():
    rhi = _FakeRhi()
    resources = _resources(rhi)
    resources._probe_array_target = lambda _texture: False

    with pytest.raises(RuntimeError, match="even at"):
        resources._ensure_tile_array(0)
    assert resources.tile_arrays == []
