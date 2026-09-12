"""Texture-array instanced-draw resources for Multi Compare's base-image
pass (docs/dev/rendering/tile-array-atlas-plan.md Phase 4).

Split out of ``BaseImagesPass`` -- owns the shared tile-array texture(s),
the array pipeline/SRB, and the per-instance/uniform buffers used to draw
every visible slot's tiles in one instanced draw call. Mirrors
image_compare's ``rhi_renderer/array_resources.py`` -- both are now thin
subclasses of ``shared.rendering.array_resources.TileArrayResourcesBase``
(docs/dev/rendering/renderer-unification-plan.md Phase 2), supplying only
this tab's own per-instance vertex layout/shaders/uniform size (no
cross-image pairing here, so one instance is a single (layer, tile) pair
instead of an image1/image2/diff triple). Tile *residency decisions*
(which tiles should be resident, cropping, marking resident) stay in
``BaseImagesPass._realize_tile_residency``; this class only owns the GPU
resources those decisions get realized against.
"""

from __future__ import annotations

from PySide6.QtGui import QRhiVertexInputAttribute

from shared.rendering.array_resources import TileArrayResourcesBase

# Per-instance vertex layout for the array pipeline
# (multi_compare_array.vert): iPanFit(vec4,16) + iZoom(float,4) +
# iTileRect(vec4,16) + iSlotRect(vec4,16) + iContentScale(vec2,8) +
# iLayer(int,4) + iBBox(vec4,16) = 80 bytes. iBBox added by the
# docs/dev/rendering/tile-array-atlas-plan.md Phase 10 port (see
# base_images.py's ``_instance_bbox``) -- clips each instance's geometry to
# its own tile's on-screen footprint instead of emitting a shared
# full-framebuffer quad for every instance and relying entirely on
# base_array.frag-style discard, mirroring image_compare's identical fix.
_ARRAY_INSTANCE_STRIDE = 80
# std140 layout of multi_compare_array.frag/vert's UBuf: mat4 mvp(64) +
# vec4 letterbox(16) = 80. Frame-constant across every instance.
_ARRAY_UNIFORM_BLOCK_SIZE = 80

_ARRAY_INSTANCE_ATTRIBUTES = (
    QRhiVertexInputAttribute(1, 2, QRhiVertexInputAttribute.Format.Float4, 0),
    QRhiVertexInputAttribute(1, 3, QRhiVertexInputAttribute.Format.Float, 16),
    QRhiVertexInputAttribute(1, 4, QRhiVertexInputAttribute.Format.Float4, 20),
    QRhiVertexInputAttribute(1, 5, QRhiVertexInputAttribute.Format.Float4, 36),
    QRhiVertexInputAttribute(1, 6, QRhiVertexInputAttribute.Format.Float2, 52),
    QRhiVertexInputAttribute(1, 7, QRhiVertexInputAttribute.Format.SInt, 60),
    QRhiVertexInputAttribute(1, 8, QRhiVertexInputAttribute.Format.Float4, 64),
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
            vertex_shader_name="multi_compare_array.vert.qsb",
            fragment_shader_name="multi_compare_array.frag.qsb",
            default_sampler_name="default",
        )
