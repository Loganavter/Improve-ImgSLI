"""Texture-array instanced-draw resources for Multi Compare's base-image
pass (docs/dev/rendering/tile-array-atlas-plan.md Phase 4).

Split out of ``BaseImagesPass`` -- owns the shared tile-array texture(s),
the array pipeline/SRB, and the per-instance/uniform buffers used to draw
every visible slot's tiles in one instanced draw call. The per-instance
layout and the shader are the engine's shared slot-array pass
(``engine.gpu.array_draw.SLOT_INSTANCE_*`` / ``slot_array.*``) -- the same
one Quick Look uses for its single full-canvas slot, so Multi Compare no
longer carries its own layout/shader copy.

Tile *residency decisions* stay in ``passes/residency.py::realize`` (spec
resolution) plus ``engine.cache.residency.TileResidencyRealizerBase.realize_specs``
(the per-key target/protect/budget/upload loop); this class only owns the
GPU resources those decisions get realized against.
"""

from __future__ import annotations

from engine.gpu.array_draw import (
    SLOT_INSTANCE_ATTRIBUTES,
    SLOT_INSTANCE_STRIDE,
    SLOT_UNIFORM_BLOCK_SIZE,
)
from engine.gpu.array_resources import TileArrayResourcesBase


class ArrayResources(TileArrayResourcesBase):
    def __init__(self, *, rhi_getter, sampler_getter, load_shader, layer_px, array_capacity, name_prefix) -> None:
        super().__init__(
            rhi_getter=rhi_getter,
            sampler_getter=sampler_getter,
            load_shader=load_shader,
            layer_px=layer_px,
            array_capacity=array_capacity,
            name_prefix=name_prefix,
            instance_stride=SLOT_INSTANCE_STRIDE,
            uniform_block_size=SLOT_UNIFORM_BLOCK_SIZE,
            instance_attributes=SLOT_INSTANCE_ATTRIBUTES,
            vertex_shader_name="slot_array.vert.qsb",
            fragment_shader_name="slot_array.frag.qsb",
            default_sampler_name="default",
        )
