"""Framebuffer overlay texture pass for Multi Compare."""

from __future__ import annotations

import struct

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from tabs.multi_compare.scene.resources import (
    FULLSCREEN_VERTICES,
    OVERLAY_UNIFORM_SIZE,
    load_shader,
    vertex_input_layout,
)


class OverlayTexturePass:
    """Draws the rasterized label/empty/drag overlay texture."""

    def __init__(self) -> None:
        self.pipeline = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.texture = None
        self.texture_size: QSize | None = None
        self.srb = None
        self.active = False

    def initialize(self, renderer, target, upload) -> None:
        self.vertex_buffer = renderer.rhi.newBuffer(
            QRhiBuffer.Type.Immutable,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        self.vertex_buffer.create()
        upload.uploadStaticBuffer(self.vertex_buffer, FULLSCREEN_VERTICES)

        self.uniform_buffer = renderer.rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            OVERLAY_UNIFORM_SIZE,
        )
        self.uniform_buffer.create()
        self.texture = renderer.rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        self.texture.create()
        self.texture_size = QSize(1, 1)
        ph = QImage(1, 1, QImage.Format.Format_RGBA8888)
        ph.fill(0)
        upload.uploadTexture(self.texture, ph)

        self.srb = self._build_srb(renderer)
        self.pipeline = renderer.rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, load_shader("overlay.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, load_shader("overlay.frag.qsb")
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.pipeline.setTargetBlends([blend])
        self.pipeline.setShaderResourceBindings(self.srb)
        self.pipeline.setVertexInputLayout(vertex_input_layout())
        if not self.pipeline.create():
            raise RuntimeError("Failed to create multi_compare overlay pipeline")

    def release(self) -> None:
        for res in (
            self.pipeline,
            self.vertex_buffer,
            self.uniform_buffer,
            self.texture,
            self.srb,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.__init__()

    def prepare(self, renderer, ctx, updates) -> None:
        fb_w, fb_h = ctx.framebuffer_size
        ox, oy = ctx.offset
        updates.updateDynamicBuffer(
            self.uniform_buffer,
            0,
            struct.pack("<16f", *ctx.clip_matrix),
        )
        self.active = False
        overlay_image = renderer.overlay_painter.build(
            ctx.composition,
            ctx.scale,
            ox,
            oy,
            int(fb_w),
            int(fb_h),
        )
        if overlay_image is None or overlay_image.isNull():
            return
        overlay_size = overlay_image.size()
        if self.texture_size != overlay_size:
            try:
                self.texture.destroy()
            except RuntimeError:
                pass
            self.texture = renderer.rhi.newTexture(
                QRhiTexture.Format.RGBA8, overlay_size
            )
            self.texture.create()
            self.texture_size = overlay_size
        try:
            self.srb.destroy()
        except RuntimeError:
            pass
        self.srb = self._build_srb(renderer)
        updates.uploadTexture(self.texture, overlay_image)
        self.active = True

    def record(self, _renderer, ctx, command_buffer) -> None:
        if not self.active:
            return
        fb_w, fb_h = ctx.framebuffer_size
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        command_buffer.draw(4)

    def _build_srb(self, renderer):
        srb = renderer.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1,
                    fragment,
                    self.texture or renderer.placeholder,
                    renderer.sampler,
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create multi_compare overlay SRB")
        return srb
