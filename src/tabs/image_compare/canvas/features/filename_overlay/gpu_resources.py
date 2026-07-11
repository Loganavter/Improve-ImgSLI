from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import (
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
)

from tabs.image_compare.canvas.rhi_feature_common import load_qshader

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_SIZE = 64
_VERTEX_STRIDE = 16
_VERTEX_BUFFER_SIZE = _VERTEX_STRIDE * 4


class LabelSlot:
    def __init__(self) -> None:
        self.vertex_buffer = None
        self.texture = None
        self.texture_size: QSize | None = None
        self.srb_nearest = None
        self.srb_linear = None
        self.content_key: object = None
        self.active: bool = False
        self.smooth: bool = False
        self.vertices: bytes | None = None

    def release(self) -> None:
        for res in (
            self.srb_nearest,
            self.srb_linear,
            self.texture,
            self.vertex_buffer,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.vertex_buffer = None
        self.texture = None
        self.texture_size = None
        self.srb_nearest = None
        self.srb_linear = None
        self.content_key = None
        self.active = False
        self.vertices = None


class FilenameOverlayGpuResources:
    """Owns the QRhi pipeline/buffers/samplers for the filename_overlay pass.

    Split out of ``FilenameOverlayPass`` so the pass class itself only holds
    the should_paint/prepare/record orchestration; resource lifecycle
    (create in ``initialize()``, resize on demand, destroy in ``release()``)
    lives here instead.
    """

    def __init__(self) -> None:
        self.rhi = None
        self.uniform_buffer = None
        self.sampler_nearest = None
        self.sampler_linear = None
        self.pipeline = None
        self.slots: list[LabelSlot] = [LabelSlot(), LabelSlot()]

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi

        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create filename_overlay uniform buffer")

        self.sampler_nearest = rhi.newSampler(
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.Nearest,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_nearest.create():
            raise RuntimeError("Failed to create filename_overlay nearest sampler")

        self.sampler_linear = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler_linear.create():
            raise RuntimeError("Failed to create filename_overlay linear sampler")

        for slot in self.slots:
            slot.vertex_buffer = rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.VertexBuffer,
                _VERTEX_BUFFER_SIZE,
            )
            if not slot.vertex_buffer.create():
                raise RuntimeError("Failed to create filename_overlay vertex buffer")
            slot.texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
            if not slot.texture.create():
                raise RuntimeError(
                    "Failed to create filename_overlay placeholder texture"
                )
            slot.texture_size = QSize(1, 1)
            slot.srb_nearest = self._build_srb(slot.texture, self.sampler_nearest)
            slot.srb_linear = self._build_srb(slot.texture, self.sampler_linear)

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "filename_overlay.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "filename_overlay.frag.qsb"),
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setShaderResourceBindings(self.slots[0].srb_linear)
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.pipeline.setTargetBlends([blend])

        layout = QRhiVertexInputLayout()
        layout.setBindings([QRhiVertexInputBinding(_VERTEX_STRIDE)])
        layout.setAttributes(
            [
                QRhiVertexInputAttribute(
                    0, 0, QRhiVertexInputAttribute.Format.Float2, 0
                ),
                QRhiVertexInputAttribute(
                    0, 1, QRhiVertexInputAttribute.Format.Float2, 8
                ),
            ]
        )
        self.pipeline.setVertexInputLayout(layout)
        if not self.pipeline.create():
            raise RuntimeError("Failed to create filename_overlay QRhi pipeline")

    def _build_srb(self, texture, sampler):
        srb = self.rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        fragment = QRhiShaderResourceBinding.StageFlag.FragmentStage
        srb.setBindings(
            [
                QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer),
                QRhiShaderResourceBinding.sampledTexture(1, fragment, texture, sampler),
            ]
        )
        if not srb.create():
            raise RuntimeError("Failed to create filename_overlay SRB")
        return srb

    def ensure_slot_texture(self, slot: LabelSlot, size: QSize) -> None:
        if slot.texture_size == size:
            return
        if slot.texture is not None:
            try:
                slot.texture.destroy()
            except RuntimeError:
                pass
        slot.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, size)
        if not slot.texture.create():
            raise RuntimeError("Failed to resize filename_overlay texture")
        slot.texture_size = size
        for srb_attr, sampler in (
            ("srb_nearest", self.sampler_nearest),
            ("srb_linear", self.sampler_linear),
        ):
            srb = getattr(slot, srb_attr)
            if srb is not None:
                try:
                    srb.destroy()
                except RuntimeError:
                    pass
            setattr(slot, srb_attr, self._build_srb(slot.texture, sampler))

    def release(self) -> None:
        for slot in self.slots:
            slot.release()
        for res in (
            self.pipeline,
            self.sampler_linear,
            self.sampler_nearest,
            self.uniform_buffer,
        ):
            if res is not None:
                try:
                    res.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self.sampler_linear = None
        self.sampler_nearest = None
        self.uniform_buffer = None
        self.rhi = None
