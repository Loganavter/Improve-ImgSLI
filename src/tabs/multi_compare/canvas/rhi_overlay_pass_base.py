"""Shared QRhi fullscreen textured-overlay pass base for Multi Compare features.

``layer_labels`` and ``drag_drop_overlay`` rasterize into an independent
framebuffer-sized ``QImage`` and draw it as one alpha-blended textured quad —
shared QRhi plumbing (pipeline, texture, SRB, blend); subclasses implement
``_raster``. Grid dividers use a dedicated GPU quad pass instead (no FB-sized
overlay texture). Split out per MULTI_COMPARE_QRHI_REFACTOR.md Phase B3.
"""

from __future__ import annotations

import logging
import struct

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
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
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass

logger = logging.getLogger("ImproveImgSLI")


class FullscreenOverlayTexturePass(CanvasRenderPass):
    """Rasterize-to-texture, draw-as-fullscreen-quad QRhi pass base."""

    def __init__(self) -> None:
        self.rhi = None
        self.pipeline = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count: int | None = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.sampler = None
        self.texture = None
        self.texture_size: QSize | None = None
        self.srb = None
        self.active = False

    def _raster(self, widget, ctx) -> QImage | None:
        """Return the framebuffer-sized overlay image for this frame, or
        ``None``/a null image if this pass has nothing to draw."""
        raise NotImplementedError

    def _ensure_pipeline(self, target, *, force: bool = False) -> bool:
        """Recreate overlay pipeline if the swapchain render-pass descriptor changed."""
        if self.rhi is None or target is None or self.srb is None:
            return False
        descriptor = target.renderPassDescriptor()
        sample_count = int(target.sampleCount())
        if (
            not force
            and self.pipeline is not None
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

        pipeline = self.rhi.newGraphicsPipeline()
        pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, load_shader("overlay.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, load_shader("overlay.frag.qsb")
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        pipeline.setRenderPassDescriptor(descriptor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        pipeline.setTargetBlends([blend])
        pipeline.setShaderResourceBindings(self.srb)
        pipeline.setVertexInputLayout(vertex_input_layout())
        if not pipeline.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} QRhi pipeline")
        self.pipeline = pipeline
        self._render_pass_descriptor = descriptor
        self._pipeline_sample_count = sample_count
        return True

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi

        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} vertex buffer")

        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            OVERLAY_UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} uniform buffer")

        self.sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} sampler")

        self.texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        if not self.texture.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} placeholder texture")
        self.texture_size = QSize(1, 1)

        self.srb = self._build_srb()
        self._ensure_pipeline(target)

    def _build_srb(self):
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(
                    1, fragment, self.texture, self.sampler
                ),
            ]
        )
        if not srb.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} SRB")
        return srb

    def prepare(self, widget, ctx, resource_updates) -> None:
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, FULLSCREEN_VERTICES)
        resource_updates.updateDynamicBuffer(
            self.uniform_buffer,
            0,
            struct.pack("<16f", *ctx.clip_matrix),
        )
        self.active = False
        overlay_image = self._raster(widget, ctx)
        if overlay_image is None or overlay_image.isNull():
            if getattr(widget, "_mc_overlay_debug", False):
                logger.info(
                    "[mc-overlay-debug] %s.prepare: no overlay image (None=%s)",
                    type(self).__name__,
                    overlay_image is None,
                )
            return
        overlay_size = overlay_image.size()
        if self.texture_size != overlay_size:
            try:
                self.texture.destroy()
            except RuntimeError:
                pass
            self.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, overlay_size)
            if not self.texture.create():
                raise RuntimeError(f"Failed to resize {type(self).__name__} texture")
            self.texture_size = overlay_size
            try:
                self.srb.destroy()
            except RuntimeError:
                pass
            self.srb = self._build_srb()
            # Pipeline was created against the previous SRB; rebuild so the
            # layout binding stays valid after texture resize (Vulkan).
            try:
                rt = widget.renderTarget() if widget is not None else None
            except Exception:
                rt = None
            if rt is not None:
                self._ensure_pipeline(rt, force=True)
        resource_updates.uploadTexture(self.texture, overlay_image)
        self.active = True
        if getattr(widget, "_mc_overlay_debug", False):
            logger.info(
                "[mc-overlay-debug] %s.prepare: uploaded texture size=%s active=%s",
                type(self).__name__,
                overlay_size,
                self.active,
            )

    def record(self, command_buffer, widget, ctx) -> None:
        if getattr(widget, "_mc_overlay_debug", False):
            logger.info(
                "[mc-overlay-debug] %s.record: active=%s pipeline=%s",
                type(self).__name__,
                self.active,
                self.pipeline is not None,
            )
        if not self.active or self.pipeline is None:
            return
        fb_w, fb_h = ctx.framebuffer_size
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        command_buffer.draw(4)

    def release(self) -> None:
        for res in (self.pipeline, self.srb, self.texture, self.uniform_buffer, self.vertex_buffer, self.sampler):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.rhi = None
        self.pipeline = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.sampler = None
        self.texture = None
        self.texture_size = None
        self.srb = None
        self.active = False
