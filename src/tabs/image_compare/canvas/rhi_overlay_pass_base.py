"""Shared QRhi fullscreen textured-overlay pass base for Image Compare features.

Mirrors ``tabs.multi_compare.canvas.rhi_overlay_pass_base`` for image_compare:
rasterize into a framebuffer-sized QImage and draw it as one alpha-blended
textured quad — shared QRhi plumbing (pipeline, texture, SRB, blend);
subclasses implement ``_raster``.
"""

from __future__ import annotations

import logging
import struct
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QImage,
    QRhiBuffer,
    QRhi,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderResourceBindings,
    QRhiShaderStage,
    QRhiTexture,
    QRhiViewport,
)

from ui.canvas_infra.scene.pass_contract import CanvasRenderPass

logger = logging.getLogger("ImproveImgSLI")

# Shared shader dir — overlay shaders are generic fullscreen textured quad.
# Prefer local image_compare copy if present, else reuse multi_compare's.
_LOCAL_SHADER_DIR = Path(__file__).resolve().parent / "shaders" / "overlay"
_MC_SHADER_DIR = Path(__file__).resolve().parents[2] / "multi_compare" / "shaders" / "qrhi"

FULLSCREEN_VERTICES = struct.pack(
    "<16f",
    -1.0,
    1.0,
    0.0,
    0.0,
    -1.0,
    -1.0,
    0.0,
    1.0,
    1.0,
    1.0,
    1.0,
    0.0,
    1.0,
    -1.0,
    1.0,
    1.0,
)
OVERLAY_UNIFORM_SIZE = 64


def _shader_dir() -> Path:
    if _LOCAL_SHADER_DIR.is_dir():
        return _LOCAL_SHADER_DIR
    return _MC_SHADER_DIR


def _load_shader(name: str):
    from PySide6.QtGui import QShader

    data = (_shader_dir() / name).read_bytes()
    shader = QShader.fromSerialized(data)
    if not shader.isValid():
        raise RuntimeError(f"Invalid overlay shader: {name}")
    return shader


def _vertex_input_layout():
    from PySide6.QtGui import QRhiVertexInputAttribute, QRhiVertexInputBinding, QRhiVertexInputLayout

    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(16)])
    layout.setAttributes(
        [
            QRhiVertexInputAttribute(0, 0, QRhiVertexInputAttribute.Format.Float2, 0),
            QRhiVertexInputAttribute(0, 1, QRhiVertexInputAttribute.Format.Float2, 8),
        ]
    )
    return layout


class FullscreenOverlayTexturePass(CanvasRenderPass):
    """Rasterize-to-texture, draw-as-fullscreen-quad QRhi pass base."""

    def __init__(self) -> None:
        self.rhi: QRhi | None = None
        self.pipeline: QRhiGraphicsPipeline | None = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count: int | None = None
        self.vertex_buffer: QRhiBuffer | None = None
        self.uniform_buffer: QRhiBuffer | None = None
        self.sampler: QRhiSampler | None = None
        self.texture: QRhiTexture | None = None
        self.texture_size: QSize | None = None
        self.srb: QRhiShaderResourceBindings | None = None
        self.active = False

    def _raster(self, widget, ctx) -> QImage | None:
        raise NotImplementedError

    def _ensure_pipeline(self, target, *, force: bool = False) -> bool:
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
                QRhiShaderStage(QRhiShaderStage.Type.Vertex, _load_shader("overlay.vert.qsb")),
                QRhiShaderStage(QRhiShaderStage.Type.Fragment, _load_shader("overlay.frag.qsb")),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        pipeline.setRenderPassDescriptor(descriptor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One  # type: ignore[assignment]
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha  # type: ignore[assignment]
        pipeline.setTargetBlends([blend])
        pipeline.setShaderResourceBindings(self.srb)
        pipeline.setVertexInputLayout(_vertex_input_layout())
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
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.VertexBuffer, len(FULLSCREEN_VERTICES)
        )
        if not self.vertex_buffer.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} vertex buffer")
        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic, QRhiBuffer.UsageFlag.UniformBuffer, OVERLAY_UNIFORM_SIZE
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
        assert self.rhi is not None
        srb = self.rhi.newShaderResourceBindings()
        stages = QRhiShaderResourceBinding.StageFlag.VertexStage | QRhiShaderResourceBinding.StageFlag.FragmentStage
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(1, fragment, self.texture, self.sampler),
            ]
        )
        if not srb.create():
            raise RuntimeError(f"Failed to create {type(self).__name__} SRB")
        return srb

    def prepare(self, widget, ctx, resource_updates) -> None:
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, FULLSCREEN_VERTICES)
        # ctx.clip_matrix may not exist for image_compare; fallback to identity.
        clip_matrix = getattr(ctx, "clip_matrix", None)
        if clip_matrix is None:
            # identity mat4
            clip_matrix = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
        resource_updates.updateDynamicBuffer(self.uniform_buffer, 0, struct.pack("<16f", *clip_matrix))
        self.active = False
        overlay_image = self._raster(widget, ctx)
        if overlay_image is None or overlay_image.isNull():
            return
        overlay_size = overlay_image.size()
        if self.texture_size != overlay_size:
            try:
                if self.texture is not None:
                    self.texture.destroy()
            except RuntimeError:
                pass
            assert self.rhi is not None
            self.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, overlay_size)
            if not self.texture.create():
                raise RuntimeError(f"Failed to resize {type(self).__name__} texture")
            self.texture_size = overlay_size
            try:
                if self.srb is not None:
                    self.srb.destroy()
            except RuntimeError:
                pass
            self.srb = self._build_srb()
            try:
                rt = widget.renderTarget() if widget is not None else None
            except Exception:
                rt = None
            if rt is not None:
                self._ensure_pipeline(rt, force=True)
        resource_updates.uploadTexture(self.texture, overlay_image)
        self.active = True

    def record(self, command_buffer, widget, ctx) -> None:
        if not self.active or self.pipeline is None:
            return
        # ctx.framebuffer_size may not exist; fallback to width/height
        fb = getattr(ctx, "framebuffer_size", None)
        if fb is None:
            fb = (int(getattr(ctx, "width", 0)), int(getattr(ctx, "height", 0)))
        fb_w, fb_h = fb
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, float(fb_w), float(fb_h)))
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
