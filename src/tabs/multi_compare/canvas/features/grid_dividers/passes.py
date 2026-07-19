"""QRhi render pass for multi_compare grid dividers (GPU quads, IC-style).

Geometry still comes from ``DividersOverlaySource`` (canvas gaps → framebuffer
rects). Drawing is solid-color triangle strips — no framebuffer-sized overlay
texture / SRB resize (the path that went dark after the UV-letterbox migrate).
"""

from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import (
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)

from tabs.multi_compare.scene.passes.dividers import DividersOverlaySource
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_VERTEX_STRIDE = 16
_VERTS_PER_DIVIDER = 4
_MAX_DIVIDERS = 64
_VERTEX_BUFFER_SIZE = _MAX_DIVIDERS * _VERTS_PER_DIVIDER * _VERTEX_STRIDE
# std140: mat4 mvp (64) + vec4 color (16) = 80
_UNIFORM_SIZE = 80


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid multi_compare grid_divider shader: {name}")
    return shader


def fb_rect_to_ndc_quad(rect: QRectF, fb_w: float, fb_h: float) -> bytes:
    """Pack one triangle-strip quad (TL, BL, TR, BR) in NDC for ``rect`` in FB px."""

    if fb_w <= 0.0 or fb_h <= 0.0 or rect.width() <= 0.0 or rect.height() <= 0.0:
        return b""
    x0 = float(rect.x())
    y0 = float(rect.y())
    x1 = x0 + float(rect.width())
    y1 = y0 + float(rect.height())
    # FB px (origin top-left) → NDC; Y flips so +y is up in clip space.
    def ndc(x: float, y: float) -> tuple[float, float]:
        return (2.0 * x / fb_w) - 1.0, 1.0 - (2.0 * y / fb_h)

    tl = ndc(x0, y0)
    bl = ndc(x0, y1)
    tr = ndc(x1, y0)
    br = ndc(x1, y1)
    return struct.pack(
        "<16f",
        tl[0],
        tl[1],
        0.0,
        0.0,
        bl[0],
        bl[1],
        0.0,
        1.0,
        tr[0],
        tr[1],
        1.0,
        0.0,
        br[0],
        br[1],
        1.0,
        1.0,
    )


class GridDividersPass(CanvasRenderPass):
    """Draw every N-way grid split as a GPU solid-color quad."""

    stack_role = CanvasStackRole.UNDERLAY_SPLIT

    def __init__(self) -> None:
        self.rhi = None
        self.pipeline = None
        self._render_pass_descriptor = None
        self._pipeline_sample_count: int | None = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.srb = None
        self._source = DividersOverlaySource()
        self._draw_count = 0

    def should_paint(self, ctx) -> bool:
        return self._source.should_paint(ctx.composition)

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
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("grid_divider.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("grid_divider.frag.qsb")
                ),
            ]
        )
        pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        pipeline.setSampleCount(sample_count)
        pipeline.setRenderPassDescriptor(descriptor)
        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        pipeline.setTargetBlends([blend])
        pipeline.setShaderResourceBindings(self.srb)
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
        pipeline.setVertexInputLayout(layout)
        if not pipeline.create():
            raise RuntimeError("Failed to create GridDividersPass QRhi pipeline")
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
            _VERTEX_BUFFER_SIZE,
        )
        if not self.vertex_buffer.create():
            raise RuntimeError("Failed to create GridDividersPass vertex buffer")
        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create GridDividersPass uniform buffer")
        self.srb = rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        self.srb.setBindings(
            [QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer)]
        )
        if not self.srb.create():
            raise RuntimeError("Failed to create GridDividersPass SRB")
        self._ensure_pipeline(target)

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._draw_count = 0
        composition = ctx.composition
        if not self._source.should_paint(composition):
            return
        fb_w, fb_h = ctx.framebuffer_size
        rects = self._source.projected_divider_rects(
            composition=composition,
            scale=ctx.scale,
            offset=ctx.offset,
            framebuffer_size=ctx.framebuffer_size,
        )
        ox, oy = ctx.offset
        canvas_clip = QRectF(
            ox, oy, composition.canvas_w * ctx.scale, composition.canvas_h * ctx.scale
        )
        packed = bytearray()
        for rect in rects[:_MAX_DIVIDERS]:
            clipped = rect.intersected(canvas_clip)
            quad = fb_rect_to_ndc_quad(clipped, float(fb_w), float(fb_h))
            if not quad:
                continue
            packed.extend(quad)
        if not packed:
            return
        self._draw_count = len(packed) // (_VERTS_PER_DIVIDER * _VERTEX_STRIDE)
        color = self._source._divider_color(widget, composition)
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, bytes(packed))
        resource_updates.updateDynamicBuffer(
            self.uniform_buffer,
            0,
            struct.pack(
                "<16f4f",
                *ctx.clip_matrix,
                color.redF(),
                color.greenF(),
                color.blueF(),
                color.alphaF(),
            ),
        )

    def record(self, command_buffer, widget, ctx) -> None:
        if self._draw_count <= 0 or self.pipeline is None:
            return
        fb_w, fb_h = ctx.framebuffer_size
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_w, fb_h))
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        for index in range(self._draw_count):
            command_buffer.draw(4, 1, index * _VERTS_PER_DIVIDER)

    def release(self) -> None:
        for res in (self.pipeline, self.srb, self.uniform_buffer, self.vertex_buffer):
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
        self.srb = None
        self._draw_count = 0


RENDER_PASSES: list[CanvasRenderPass] = [GridDividersPass()]
RENDER_PASSES = RENDER_PASSES
