"""Shared texture-array instanced-draw resource owner (docs/dev/rendering/
renderer-unification-plan.md Phase 2).

Extracted out of the compare tabs' independently-coded ``ArrayResources``
classes (single-pair and multi-pair), which were near-line-for-line identical
boilerplate (texture-array creation, instance-buffer growth, SRB caching,
pipeline/blend-state creation) with only the per-instance vertex layout,
shader pair, uniform block size, and sampler source differing -- those
differences are threaded through as constructor arguments instead of
assumed. Tile *residency decisions* (which tiles should be resident,
cropping) stay in each tab's own residency code; this class only owns the
GPU resources those decisions get realized against.
"""

from __future__ import annotations

from typing import Callable, Sequence

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhi,
    QRhiSampler,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiTextureSubresourceUploadDescription,
    QRhiTextureUploadDescription,
    QShader,
    QRhiTextureUploadEntry,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
)

from shared.rendering.tile_debug import log_tile_event, tile_dump_enabled
from shared.rendering.tile_texture_service import TileTextureService


class TileArrayResourcesBase:
    """Owns the shared texture array(s), the array graphics pipeline/SRB
    cache, and the per-instance/uniform buffers backing it -- one instance
    per renderer/pass."""

    def __init__(
        self,
        *,
        rhi_getter: Callable[[], QRhi | None],
        sampler_getter: Callable[[str], QRhiSampler | None],
        load_shader: Callable[[str], QShader],
        layer_px: int,
        array_capacity: int,
        name_prefix: str,
        instance_stride: int,
        uniform_block_size: int,
        instance_attributes: Sequence[QRhiVertexInputAttribute],
        vertex_shader_name: str,
        fragment_shader_name: str,
        default_sampler_name: str = "default",
        vertex_stride: int = 16,
    ) -> None:
        self._rhi_getter = rhi_getter
        self._sampler_getter = sampler_getter
        self._load_shader = load_shader
        self._layer_px = layer_px
        self._array_capacity = array_capacity
        self._name_prefix = name_prefix
        self._instance_stride = instance_stride
        self._uniform_block_size = uniform_block_size
        self._instance_attributes = list(instance_attributes)
        self._vertex_shader_name = vertex_shader_name
        self._fragment_shader_name = fragment_shader_name
        self._default_sampler_name = default_sampler_name
        self._vertex_stride = vertex_stride

        self.tile_arrays: list[QRhiTexture] = []
        self.array_pipeline: QRhiGraphicsPipeline | None = None
        self.array_srb: QRhiShaderResourceBindings | None = None
        self._array_srb_cache: dict[str, QRhiShaderResourceBindings] = {}
        self.array_uniform_buffer: QRhiBuffer | None = None
        self.array_instance_buffer: QRhiBuffer | None = None
        self._array_instance_capacity = 0
        self._array_render_pass_descriptor = None
        self._array_pipeline_sample_count: int | None = None

    @property
    def rhi(self) -> QRhi:
        rhi = self._rhi_getter()
        assert rhi is not None
        return rhi

    def release(self) -> None:
        resources = [
            self.array_pipeline,
            *self._array_srb_cache.values(),
            *(
                [self.array_srb]
                if self.array_srb is not None
                and not any(self.array_srb is s for s in self._array_srb_cache.values())
                else []
            ),
            self.array_uniform_buffer,
            self.array_instance_buffer,
            *self.tile_arrays,
        ]
        for resource in resources:
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.tile_arrays = []
        self.array_pipeline = None
        self.array_srb = None
        self._array_srb_cache = {}
        self.array_uniform_buffer = None
        self.array_instance_buffer = None
        self._array_instance_capacity = 0
        self._array_render_pass_descriptor = None
        self._array_pipeline_sample_count = None

    def upload_tile_to_array(
        self,
        tile_service: TileTextureService,
        source_key: object,
        index: tuple[int, int],
        image,
        updates,
        dirty_layers: dict[int, set[int]] | None = None,
    ) -> object:
        """Uploads one multi-tile-grid tile into the shared texture array
        instead of its own whole ``QRhiTexture``. ``image`` is uploaded 1:1,
        unresampled, into the top-left corner of its assigned layer. The
        tile's content-scale is recorded so the draw plan can tell the
        shader how much of that layer is real content. Returns the tile's
        key for the caller's own bookkeeping.

        ``generateMips`` is *not* called here -- see ``dirty_layers``:
        callers must add ``(array_index, layer)`` to it and call
        ``generate_all_dirty_mips`` once after all of this call's tile
        uploads are queued and submitted, instead of paying
        O(array capacity) whole-array mip regeneration per tile."""
        tile_key = tile_service.tile_key(source_key, *index)
        byte_size = image.width() * image.height() * 4
        content_size = (image.width(), image.height())
        tile_service.mark_resident(source_key, index, byte_size, content_size)
        array_index, layer = tile_service.slot_for(source_key, index)
        self._ensure_tile_array(array_index)
        tex = self.tile_arrays[array_index]
        entry = QRhiTextureUploadEntry(
            layer, 0, QRhiTextureSubresourceUploadDescription(image)
        )
        if tile_dump_enabled():
            row, col = index
            log_tile_event(
                "array.upload",
                source_key=str(source_key),
                row=row,
                col=col,
                row_parity=row % 2,
                col_parity=col % 2,
                array_index=array_index,
                layer=layer,
                byte_size=byte_size,
                content_size=content_size,
                image_w=image.width(),
                image_h=image.height(),
            )
        updates.uploadTexture(tex, QRhiTextureUploadDescription(entry))
        if dirty_layers is not None:
            dirty_layers.setdefault(array_index, set()).add(layer)
        else:
            updates.generateMips(tex)
        return tile_key

    def _ensure_tile_array(self, array_index: int) -> None:
        while len(self.tile_arrays) <= array_index:
            texture = self.rhi.newTextureArray(
                QRhiTexture.Format.RGBA8,
                self._array_capacity,
                QSize(self._layer_px, self._layer_px),
                1,
                QRhiTexture.Flag.MipMapped | QRhiTexture.Flag.UsedWithGenerateMips,
            )
            texture.setName(
                f"{self._name_prefix}-tile-array-{len(self.tile_arrays)}".encode()
            )
            if not texture.create():
                raise RuntimeError(f"Failed to create {self._name_prefix} tile array texture")
            self.tile_arrays.append(texture)

    def _ensure_array_uniform_buffer(self) -> None:
        if self.array_uniform_buffer is not None:
            return
        buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            self._uniform_block_size,
        )
        buffer.setName(f"{self._name_prefix}-array-uniforms".encode())
        if not buffer.create():
            raise RuntimeError(f"Failed to create {self._name_prefix} array uniform buffer")
        self.array_uniform_buffer = buffer

    def ensure_array_instance_capacity(self, instance_count: int) -> None:
        """Grows the per-instance vertex buffer to hold ``instance_count``
        entries. Growing this buffer does not invalidate ``array_srb`` --
        the SRB only references the (fixed) uniform buffer and tile array
        texture, never the instance buffer, which is bound as plain vertex
        input instead."""
        instance_count = max(1, instance_count)
        if instance_count <= self._array_instance_capacity:
            return
        new_buffer = self.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            self._instance_stride * instance_count,
        )
        new_buffer.setName(f"{self._name_prefix}-array-instances".encode())
        if not new_buffer.create():
            raise RuntimeError(f"Failed to grow {self._name_prefix} array instance buffer")
        if self.array_instance_buffer is not None:
            try:
                self.array_instance_buffer.destroy()
            except RuntimeError:
                pass
        self.array_instance_buffer = new_buffer
        self._array_instance_capacity = instance_count

    def ensure_array_srb(self, sampler_name: str | None = None):
        """Returns a ready-to-bind SRB for the array pipeline, cached per
        sampler name. This never needs to detect a stale binding and
        rebuild: the uniform buffer is created once and never
        replaced/grown, and ``tile_arrays[0]`` is likewise only ever
        appended to, never recreated."""
        if sampler_name is None:
            sampler_name = self._default_sampler_name
        self._ensure_array_uniform_buffer()
        self._ensure_tile_array(0)
        cached = self._array_srb_cache.get(sampler_name)
        if cached is not None:
            self.array_srb = cached
            return cached
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        sampler = self._sampler_getter(sampler_name)
        assert sampler is not None
        assert self.array_uniform_buffer is not None
        srb = self.rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(
                    0, stages, self.array_uniform_buffer
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self.tile_arrays[0], sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} array shader resource bindings"
            )
        self._array_srb_cache[sampler_name] = srb
        self.array_srb = srb
        return srb

    def ensure_array_pipeline(self, target) -> None:
        if target is None:
            return
        descriptor = target.renderPassDescriptor()
        sample_count = int(target.sampleCount())
        if (
            self.array_pipeline is not None
            and descriptor is self._array_render_pass_descriptor
            and sample_count == self._array_pipeline_sample_count
        ):
            return
        if self.array_pipeline is not None:
            try:
                self.array_pipeline.destroy()
            except RuntimeError:
                pass
            self.array_pipeline = None

        self.ensure_array_srb(self._default_sampler_name)
        pipeline = self.rhi.newGraphicsPipeline()
        pipeline.setName(f"{self._name_prefix}-array-pipeline".encode())
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    self._load_shader(self._vertex_shader_name),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    self._load_shader(self._fragment_shader_name),
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        assert self.array_srb is not None
        pipeline.setShaderResourceBindings(self.array_srb)
        pipeline.setRenderPassDescriptor(descriptor)

        input_layout = QRhiVertexInputLayout()
        input_layout.setBindings(
            [
                QRhiVertexInputBinding(self._vertex_stride),
                QRhiVertexInputBinding(
                    self._instance_stride,
                    QRhiVertexInputBinding.Classification.PerInstance,
                ),
            ]
        )
        input_layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
                *self._instance_attributes,
            ]
        )
        pipeline.setVertexInputLayout(input_layout)

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha  # type: ignore[assignment]  # PySide6 stub types BlendFactor fields as int
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        pipeline.setTargetBlends([blend])

        if not pipeline.create():
            raise RuntimeError(
                f"Failed to create {self._name_prefix} array graphics pipeline "
                "(often OpenGL < 3.3 / GLSL 120-130 with .qsb baked for 330+; "
                "on Windows use Settings -> Render Backend -> Direct3D 11)"
            )
        self.array_pipeline = pipeline
        self._array_render_pass_descriptor = descriptor
        self._array_pipeline_sample_count = sample_count
