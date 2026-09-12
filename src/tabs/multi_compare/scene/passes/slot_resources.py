"""Per-slot plain-texture pipeline/SRB/texture resources for Multi
Compare's base-image pass.

Split out of ``BaseImagesPass`` -- owns the non-array draw path: one
``QRhiTexture`` per (still-1x1) tile, the shared graphics pipeline that
draws them, per-slot vertex/uniform buffers, and the per-(slot-index,
tile-key) SRB cache. The texture-array instanced-draw path (multi-tile
slots) lives in ``array_resources.py`` instead; tile *residency decisions*
stay in ``BaseImagesPass._realize_tile_residency``, which calls into
whichever of the two owns the tile actually being uploaded.
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhi,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiRenderPassDescriptor,
    QRhiShaderResourceBindings,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
)

from shared.rendering.lod import LevelKey
from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    SLOT_UNIFORM_SIZE,
    load_shader,
    vertex_input_layout,
)


def _tile_key_slot_id(tile_key: object) -> object:
    if isinstance(tile_key, LevelKey):
        return _tile_key_slot_id(tile_key.base)
    if isinstance(tile_key, tuple):
        return _tile_key_slot_id(tile_key[0])
    return tile_key


class SlotResources:
    """Owns the plain per-slot pipeline, textures, vertex/uniform buffers,
    and tile SRB cache -- one instance per ``BaseImagesPass``."""

    def __init__(self, *, uniform_size: int) -> None:
        self.pipeline: QRhiGraphicsPipeline | None = None
        self._render_pass_descriptor: QRhiRenderPassDescriptor | None = None
        self._pipeline_sample_count: int | None = None
        self.slot_textures: dict[object, QRhiTexture] = {}
        self.slot_texture_sizes: dict[object, tuple[int, int]] = {}
        self.slot_vertex_buffers: list[QRhiBuffer] = []
        self.slot_uniform_buffers: list[QRhiBuffer] = []
        self._slot_uniform_capacity: list[int] = []
        self._slot_uniform_stride = uniform_size
        self._tile_srbs: dict[tuple[int, object], tuple[QRhiShaderResourceBindings, QRhiTexture]] = {}

    def release(self) -> None:
        for res in (
            self.pipeline,
            *self.slot_vertex_buffers,
            *self.slot_uniform_buffers,
            *(srb for srb, _texture in self._tile_srbs.values()),
            *self.slot_textures.values(),
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count = None
        self.slot_textures = {}
        self.slot_texture_sizes = {}
        self.slot_vertex_buffers = []
        self.slot_uniform_buffers = []
        self._slot_uniform_capacity = []
        self._tile_srbs = {}

    def set_uniform_stride(self, stride: int) -> None:
        self._slot_uniform_stride = stride

    def ensure_pipeline(self, renderer, target) -> bool:
        """Recreate the graphics pipeline when the swapchain RT descriptor
        changes. Mirrors image_compare's ``RhiCanvasResources.ensure_pipeline``:
        a Qt.Popup parented to the QRhiWidget can restack the color buffer;
        keeping a stale ``renderPassDescriptor``/``sampleCount`` produces a
        present that looks like a zoom nudge even when uniforms stay
        identical."""
        if target is None:
            return False
        descriptor = target.renderPassDescriptor()
        sample_count = int(target.sampleCount())
        if (
            self.pipeline is not None
            and descriptor is self._render_pass_descriptor
            and sample_count == self._pipeline_sample_count
        ):
            return False
        if self.pipeline is not None:
            try:
                self.pipeline.destroy()
            except RuntimeError:
                pass
            self.pipeline = None

        pipeline = renderer.rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, load_shader("multi_compare.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, load_shader("multi_compare.frag.qsb")
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        pipeline.setRenderPassDescriptor(descriptor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha  # type: ignore[assignment]  # PySide6 stub types BlendFactor fields as int
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        pipeline.setTargetBlends([blend])
        first_srb = self._build_slot_srb(renderer, renderer.placeholder, None)
        pipeline.setShaderResourceBindings(first_srb)
        pipeline.setVertexInputLayout(vertex_input_layout())
        if not pipeline.create():
            raise RuntimeError("Failed to create multi_compare slot pipeline")
        try:
            first_srb.destroy()
        except RuntimeError:
            pass
        self.pipeline = pipeline
        self._render_pass_descriptor = descriptor
        self._pipeline_sample_count = sample_count
        return True

    def _build_slot_srb(self, renderer, texture, uniform):
        srb = renderer.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = []
        if uniform is not None:
            bindings.append(
                QRhiShaderResourceBinding.uniformBufferWithDynamicOffset(
                    0, stages, uniform, SLOT_UNIFORM_SIZE
                )
            )
        else:
            placeholder_uniform = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                self._slot_uniform_stride,
            )
            placeholder_uniform.create()
            self.slot_uniform_buffers.append(placeholder_uniform)
            self._slot_uniform_capacity.append(1)
            bindings.append(
                QRhiShaderResourceBinding.uniformBufferWithDynamicOffset(
                    0, stages, placeholder_uniform, SLOT_UNIFORM_SIZE
                )
            )
        bindings.append(
            QRhiShaderResourceBinding.sampledTexture(
                1, fragment, texture, renderer.sampler
            )
        )
        srb.setBindings(bindings)
        if not srb.create():
            raise RuntimeError("Failed to create multi_compare slot SRB")
        return srb

    def ensure_slot_resources(self, renderer, count: int) -> None:
        while len(self.slot_vertex_buffers) < count:
            buf = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                len(FULLSCREEN_VERTICES),
            )
            buf.create()
            self.slot_vertex_buffers.append(buf)
        while len(self.slot_uniform_buffers) < count:
            buf = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                self._slot_uniform_stride,
            )
            buf.create()
            self.slot_uniform_buffers.append(buf)
            self._slot_uniform_capacity.append(1)

    def ensure_slot_uniform_capacity(self, renderer, index: int, slot_count: int) -> None:
        """Grow ``slot_uniform_buffers[index]`` to hold ``slot_count``
        per-tile uniform blocks at stride-spaced offsets, mirroring
        image_compare's ``RhiResources.ensure_uniform_capacity``. Lets every
        tile item in a multi-tile slot get its own uniform slot written into
        the single pre-pass ``updates`` batch instead of a mid-pass
        ``resourceUpdate()`` per draw call -- the pattern that caused the
        tile desync/blank-tile bug in image_compare (see docs/dev/rendering/
        investigations/multitile-uniform-desync.md). Must be called before
        beginPass: growing recreates the buffer object, which invalidates
        every cached tile SRB bound to it."""
        slot_count = max(1, slot_count)
        if index >= len(self._slot_uniform_capacity):
            return
        if slot_count <= self._slot_uniform_capacity[index]:
            return
        new_buffer = renderer.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            self._slot_uniform_stride * slot_count,
        )
        if not new_buffer.create():
            raise RuntimeError("Failed to grow multi_compare slot uniform buffer")
        old_buffer = self.slot_uniform_buffers[index]
        self.slot_uniform_buffers[index] = new_buffer
        self._slot_uniform_capacity[index] = slot_count
        self._purge_tile_srbs_for_index(index)
        if old_buffer is not None:
            try:
                old_buffer.destroy()
            except RuntimeError:
                pass

    def ensure_tile_srb(self, renderer, index: int, tile_key: object, texture):
        cache_key = (index, tile_key)
        cached = self._tile_srbs.get(cache_key)
        if cached is not None and cached[1] is texture:
            return cached[0]
        if cached is not None:
            try:
                cached[0].destroy()
            except RuntimeError:
                pass
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb = renderer.rhi.newShaderResourceBindings()
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBufferWithDynamicOffset(
                    0, stages, self.slot_uniform_buffers[index], SLOT_UNIFORM_SIZE
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, texture, renderer.sampler
                ),
            ]
        )
        srb.create()
        self._tile_srbs[cache_key] = (srb, texture)
        return srb

    def upload_tile(self, renderer, tile_key: object, image, updates) -> None:
        size = (image.width(), image.height())
        existing = self.slot_textures.get(tile_key)
        if existing is None or self.slot_texture_sizes.get(tile_key) != size:
            if existing is not None:
                try:
                    existing.destroy()
                except RuntimeError:
                    pass
            tex = renderer.rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(*size))
            tex.create()
            self.slot_textures[tile_key] = tex
            self.slot_texture_sizes[tile_key] = size
        updates.uploadTexture(self.slot_textures[tile_key], image)

    def destroy_slot_textures(self, sid: int, *, keep: frozenset | set) -> None:
        stale = [
            key
            for key in self.slot_textures
            if _tile_key_slot_id(key) == sid and key not in keep
        ]
        for key in stale:
            texture = self.slot_textures.pop(key, None)
            if texture is not None:
                try:
                    texture.destroy()
                except RuntimeError:
                    pass
            self.slot_texture_sizes.pop(key, None)

    def _purge_tile_srbs_for_index(self, index: int) -> None:
        stale = [cache_key for cache_key in self._tile_srbs if cache_key[0] == index]
        for cache_key in stale:
            srb, _texture = self._tile_srbs.pop(cache_key)
            try:
                srb.destroy()
            except RuntimeError:
                pass

    def purge_tile_srbs_for_slot(self, sid: int) -> None:
        stale = [
            cache_key
            for cache_key in self._tile_srbs
            if _tile_key_slot_id(cache_key[1]) == sid
        ]
        for cache_key in stale:
            srb, _texture = self._tile_srbs.pop(cache_key)
            try:
                srb.destroy()
            except RuntimeError:
                pass

    def purge_tile_srb_entry(self, tile_key: object) -> None:
        stale = [cache_key for cache_key in self._tile_srbs if cache_key[1] == tile_key]
        for cache_key in stale:
            srb, _texture = self._tile_srbs.pop(cache_key)
            try:
                srb.destroy()
            except RuntimeError:
                pass
