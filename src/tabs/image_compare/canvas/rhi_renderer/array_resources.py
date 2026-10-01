"""Texture-array instanced-draw resources for the image_compare base-image
renderer (docs/dev/rendering/tile-array-atlas-plan.md).

Split out of ``RhiResources`` -- owns the tile-array textures, the array
pipeline/SRB cache, and the per-instance/uniform buffers used to draw the
whole multi-tile scene in one instanced draw call. Tile *residency
decisions* (which tiles should be resident, cropping, uploading) stay in
``RhiResources``/``realize_tile_plan``; this class only owns the GPU
resources those decisions get realized against.

The GPU-resource boilerplate itself (texture-array creation, instance
buffer growth, SRB cache, pipeline/blend state) lives in
``shared.rendering.array_resources.TileArrayResourcesBase`` -- see
docs/dev/rendering/renderer-unification-plan.md Phase 2; this subclass
only supplies image_compare's own instance layout/shaders/uniform size.
"""

from __future__ import annotations

from engine.gpu.array_draw import (
    ARRAY_INSTANCE_ATTRIBUTES as _ARRAY_INSTANCE_ATTRIBUTES,
    ARRAY_INSTANCE_STRIDE as _ARRAY_INSTANCE_STRIDE,
)
from engine.gpu.array_resources import TileArrayResourcesBase

from .uniforms import _ARRAY_UNIFORM_BLOCK_SIZE


class ArrayResources(TileArrayResourcesBase):
    def __init__(self, *, rhi_getter, sampler_getter, load_shader, layer_px, array_capacity, name_prefix) -> None:
        super().__init__(
            rhi_getter=rhi_getter,
            sampler_getter=sampler_getter,
            load_shader=load_shader,
            layer_px=layer_px,
            array_capacity=array_capacity,
            name_prefix=name_prefix,
            instance_stride=_ARRAY_INSTANCE_STRIDE,
            uniform_block_size=_ARRAY_UNIFORM_BLOCK_SIZE,
            instance_attributes=_ARRAY_INSTANCE_ATTRIBUTES,
            vertex_shader_name="base_array.vert.qsb",
            fragment_shader_name="base_array.frag.qsb",
            default_sampler_name="linear",
        )
