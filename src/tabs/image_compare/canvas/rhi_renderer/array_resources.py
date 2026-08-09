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

from PySide6.QtGui import QRhiVertexInputAttribute

from shared.rendering.array_resources import TileArrayResourcesBase

from .uniforms import _ARRAY_UNIFORM_BLOCK_SIZE

# Per-instance vertex layout for the array pipeline (base_array.vert):
# iRect1(vec4,16) + iRect2(vec4,16) + iContentScale(vec4,16) +
# iContentScaleDiff(vec2,8) + iLayers(ivec3,12) + iBBox(vec4,16) +
# iRectDiff(vec4,16) = 100 bytes. Keep byte-for-byte in sync with
# ``rhi_renderer/resources.py``'s own copy of this same layout
# (``_ARRAY_INSTANCE_STRIDE``/``_ARRAY_INSTANCE_FMT``/``pack_array_instance``)
# -- these two files duplicate the layout on either side of the
# shared/image_compare split, nothing currently asserts they match.
_ARRAY_INSTANCE_STRIDE = 100

_ARRAY_INSTANCE_ATTRIBUTES = (
    QRhiVertexInputAttribute(1, 2, QRhiVertexInputAttribute.Format.Float4, 0),
    QRhiVertexInputAttribute(1, 3, QRhiVertexInputAttribute.Format.Float4, 16),
    QRhiVertexInputAttribute(1, 4, QRhiVertexInputAttribute.Format.Float4, 32),
    QRhiVertexInputAttribute(1, 5, QRhiVertexInputAttribute.Format.Float2, 48),
    QRhiVertexInputAttribute(1, 6, QRhiVertexInputAttribute.Format.SInt3, 56),
    QRhiVertexInputAttribute(1, 7, QRhiVertexInputAttribute.Format.Float4, 68),
    QRhiVertexInputAttribute(1, 8, QRhiVertexInputAttribute.Format.Float4, 84),
)


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
