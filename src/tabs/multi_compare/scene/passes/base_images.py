"""Base image tile QRhi pass for Multi Compare."""

from __future__ import annotations

import struct

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from tabs.multi_compare.scene.projection import build_screen_quad_vertices
from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    SLOT_UNIFORM_SIZE,
    load_shader,
    vertex_input_layout,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass


class BaseImagesPass(CanvasRenderPass):
    """Owns image textures, tile pipeline, uniforms, and draw recording.

    Core-owned, not a discoverable feature (see MULTI_COMPARE_QRHI_REFACTOR.md
    A6): wired directly by ``MultiCompareRhiRenderer``, never through
    ``get_canvas_render_passes()``, so it declares no ``stack_role`` — nothing
    ever resolves this pass's stacking order against the shared registry.
    """

    def __init__(self) -> None:
        self.pipeline = None
        self.slot_textures: dict[int, object] = {}
        self.slot_texture_sizes: dict[int, tuple[int, int]] = {}
        self.slot_vertex_buffers: list[object] = []
        self.slot_uniform_buffers: list[object] = []
        self.slot_srbs: list[object] = []
        self.slot_srb_texture_ids: list[int | None] = []
        self.pending_uploads: list[tuple[int, QImage]] = []
        self.pending_removes: list[int] = []

    def has_slot_texture(self, slot_id: int) -> bool:
        return int(slot_id) in self.slot_textures

    def slot_texture_ids(self) -> list[int]:
        return list(self.slot_textures)

    def queue_upload(self, slot_id: int, image: QImage) -> None:
        self.pending_uploads.append((int(slot_id), image))

    def queue_remove(self, slot_id: int) -> None:
        self.pending_removes.append(int(slot_id))

    def initialize(self, renderer, target) -> None:
        self.pipeline = renderer.rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, load_shader("multi_compare.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, load_shader("multi_compare.frag.qsb")
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        first_srb = self._build_slot_srb(renderer, renderer.placeholder, None)
        self.pipeline.setShaderResourceBindings(first_srb)
        self.pipeline.setVertexInputLayout(vertex_input_layout())
        if not self.pipeline.create():
            raise RuntimeError("Failed to create multi_compare slot pipeline")
        try:
            first_srb.destroy()
        except RuntimeError:
            pass

    def release(self) -> None:
        for res in (
            self.pipeline,
            *self.slot_vertex_buffers,
            *self.slot_uniform_buffers,
            *self.slot_srbs,
            *self.slot_textures.values(),
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.__init__()

    def apply_pending_texture_ops(self, renderer, updates) -> None:
        for sid in self.pending_removes:
            tex = self.slot_textures.pop(sid, None)
            if tex is not None:
                try:
                    tex.destroy()
                except RuntimeError:
                    pass
            self.slot_texture_sizes.pop(sid, None)
            self._invalidate_slot_srbs_for_texture(sid)
        self.pending_removes.clear()
        for sid, image in self.pending_uploads:
            size = (image.width(), image.height())
            existing = self.slot_textures.get(sid)
            if existing is None or self.slot_texture_sizes.get(sid) != size:
                if existing is not None:
                    try:
                        existing.destroy()
                    except RuntimeError:
                        pass
                self._invalidate_slot_srbs_for_texture(sid)
                tex = renderer.rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(*size))
                tex.create()
                self.slot_textures[sid] = tex
                self.slot_texture_sizes[sid] = size
            updates.uploadTexture(self.slot_textures[sid], image)
        self.pending_uploads.clear()

    def prepare(self, renderer, ctx, updates) -> None:
        fb_w, fb_h = ctx.framebuffer_size
        self._ensure_slot_resources(renderer, len(ctx.projected_layers))
        for index, layer in enumerate(ctx.projected_layers):
            vx, vy, vw, vh = layer.rect_fb
            block = struct.pack(
                "<16f 2f 2f f 3f",
                *ctx.clip_matrix,
                layer.pan_x,
                layer.pan_y,
                max(layer.fit_x, 1e-6),
                max(layer.fit_y, 1e-6),
                layer.zoom,
                0.0,
                0.0,
                0.0,
            )
            updates.updateDynamicBuffer(self.slot_uniform_buffers[index], 0, block)
            updates.updateDynamicBuffer(
                self.slot_vertex_buffers[index],
                0,
                build_screen_quad_vertices(QRectF(vx, vy, vw, vh), fb_w, fb_h),
            )
            self._ensure_slot_srb(renderer, index, int(layer.slot_id))

    def record(self, _renderer, ctx, command_buffer) -> None:
        if not ctx.projected_layers:
            return
        fb_w, fb_h = ctx.framebuffer_size
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        for index, _layer in enumerate(ctx.projected_layers):
            command_buffer.setVertexInput(0, [(self.slot_vertex_buffers[index], 0)])
            command_buffer.setShaderResources(self.slot_srbs[index])
            command_buffer.draw(4)

    def _build_slot_srb(self, renderer, texture, uniform):
        srb = renderer.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        bindings = []
        if uniform is not None:
            bindings.append(QRhiShaderResourceBinding.uniformBuffer(0, stages, uniform))
        else:
            placeholder_uniform = renderer.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                SLOT_UNIFORM_SIZE,
            )
            placeholder_uniform.create()
            self.slot_uniform_buffers.append(placeholder_uniform)
            bindings.append(
                QRhiShaderResourceBinding.uniformBuffer(0, stages, placeholder_uniform)
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

    def _ensure_slot_resources(self, renderer, count: int) -> None:
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
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
                SLOT_UNIFORM_SIZE,
            )
            buf.create()
            self.slot_uniform_buffers.append(buf)
        while len(self.slot_srbs) < count:
            index = len(self.slot_srbs)
            srb = renderer.rhi.newShaderResourceBindings()
            fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
            srb.setBindings(
                [
                    QRhiShaderResourceBinding.uniformBuffer(
                        0, stages, self.slot_uniform_buffers[index]
                    ),
                    QRhiShaderResourceBinding.sampledTexture(
                        1, fragment, renderer.placeholder, renderer.sampler
                    ),
                ]
            )
            srb.create()
            self.slot_srbs.append(srb)
            self.slot_srb_texture_ids.append(None)

    def _ensure_slot_srb(self, renderer, index: int, slot_id: int) -> None:
        if self.slot_srb_texture_ids[index] == slot_id:
            return
        texture = self.slot_textures[slot_id]
        old = self.slot_srbs[index]
        try:
            old.destroy()
        except RuntimeError:
            pass
        srb = renderer.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(
                    0, stages, self.slot_uniform_buffers[index]
                ),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, texture, renderer.sampler
                ),
            ]
        )
        srb.create()
        self.slot_srbs[index] = srb
        self.slot_srb_texture_ids[index] = slot_id

    def _invalidate_slot_srbs_for_texture(self, slot_id: int) -> None:
        for index, bound_slot_id in enumerate(self.slot_srb_texture_ids):
            if bound_slot_id == slot_id:
                self.slot_srb_texture_ids[index] = None
