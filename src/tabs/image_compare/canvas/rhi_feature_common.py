from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QRhiBuffer,
    QRhiGraphicsPipeline,
    QRhiScissor,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QShader,
)

from .render_config import get_content_rect_screen_px

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


def load_qshader(path: Path) -> QShader:
    shader = QShader.fromSerialized(path.read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid compiled shader: {path}")
    return shader


def content_clip_rect_widget_px(
    widget, ctx, *, clip_to_content: bool
) -> tuple[int, int, int, int]:
    """The content-clip rect (widget-px, pre-DPR/pre-Y-flip) that
    ``resolve_rhi_scissor`` used to compute inline. Split out so per-tile
    scissors (magnifier multi-tile capture, docs/dev/
    TILED_RENDERING_DESIGN.md Phase 4) can intersect a tile's own
    widget-px rect against this same content clip before converting to a
    device scissor via ``scissor_from_widget_rect``."""
    rect = get_content_rect_screen_px(widget) if clip_to_content else None
    if rect is None:
        return 0, 0, int(ctx.width), int(ctx.height)
    x, y, width, height = rect
    left = max(0, x)
    top = max(0, y)
    right = min(int(ctx.width), x + width)
    bottom = min(int(ctx.height), y + height)
    return left, top, max(0, right - left), max(0, bottom - top)


def scissor_from_widget_rect(
    widget, rhi, ctx, x: float, y: float, width: float, height: float
) -> QRhiScissor:
    dpr = max(1.0, float(widget.devicePixelRatioF()))
    px_x = int(round(x * dpr))
    px_y = int(round(y * dpr))
    px_width = int(round(width * dpr))
    px_height = int(round(height * dpr))
    y_up = rhi.isYUpInFramebuffer()
    # QRhiWidget always renders into an offscreen texture; for widgets that are
    # actually shown, Qt's QPainter compositing step (backing store blit) silently
    # absorbs a Y convention mismatch, so isYUpInFramebuffer() alone is correct.
    # Widgets that are never shown (WA_DontShowOnScreen, used for grabFramebuffer()-only
    # rendering such as the GPU export/preview canvas) skip that compositing step, so the
    # raw scissor Y must be flipped regardless of what isYUpInFramebuffer() reports.
    never_shown = widget.testAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen)
    if y_up or never_shown:
        framebuffer_height = int(round(float(ctx.height) * dpr))
        px_y = max(0, framebuffer_height - (px_y + px_height))
    return QRhiScissor(px_x, px_y, px_width, px_height)


def resolve_rhi_scissor(widget, rhi, ctx, *, clip_to_content: bool) -> QRhiScissor:
    x, y, width, height = content_clip_rect_widget_px(
        widget, ctx, clip_to_content=clip_to_content
    )
    return scissor_from_widget_rect(widget, rhi, ctx, x, y, width, height)


def build_fullscreen_quad_pipeline(
    rhi, target, shader_dir: Path, shader_stem: str
) -> QRhiGraphicsPipeline:
    """Graphics pipeline for a fullscreen-quad pass: standard 2xFloat2 vertex
    layout (matches ``FULLSCREEN_VERTICES``) and the alpha-preserving blend
    every blending pass must use (see docs/dev/QRHI_CANVAS_FEATURES.md,
    "Alpha / Blending Contract"). Shared by ``FullscreenUniformPassResources``
    and any pass that draws a fullscreen quad but needs a different shader
    resource layout (e.g. texture-sampling passes, which still fill their own
    SRBs after this call) — don't hand-roll this setup a second time."""
    pipeline = rhi.newGraphicsPipeline()
    pipeline.setShaderStages(
        [
            QRhiShaderStage(
                QRhiShaderStage.Type.Vertex,
                load_qshader(shader_dir / f"{shader_stem}.vert.qsb"),
            ),
            QRhiShaderStage(
                QRhiShaderStage.Type.Fragment,
                load_qshader(shader_dir / f"{shader_stem}.frag.qsb"),
            ),
        ]
    )
    pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
    pipeline.setSampleCount(target.sampleCount())
    pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
    pipeline.setFlags(QRhiGraphicsPipeline.Flag.UsesScissor)
    blend = QRhiGraphicsPipeline.TargetBlend()
    blend.enable = True
    blend.srcColor = QRhiGraphicsPipeline.BlendFactor.SrcAlpha
    blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
    blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
    blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
    pipeline.setTargetBlends([blend])
    layout = QRhiVertexInputLayout()
    layout.setBindings([QRhiVertexInputBinding(16)])
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
    return pipeline


class FullscreenUniformPassResources:
    def __init__(self, uniform_size: int) -> None:
        self.uniform_size = uniform_size
        self.rhi = None
        self.vertex_buffer = None
        self.pipeline = None
        self.uniform_buffers: list[object] = []
        self.srbs: list[object] = []
        self.pipeline_created = False

    def initialize(self, rhi, target, shader_dir: Path, shader_stem: str) -> None:
        self.release()
        self.rhi = rhi
        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError(f"Failed to create {shader_stem} vertex buffer")

        self.pipeline = build_fullscreen_quad_pipeline(
            rhi, target, shader_dir, shader_stem
        )

    def ensure_items(self, count: int) -> None:
        stage = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        while len(self.uniform_buffers) < count:
            buffer = self.rhi.newBuffer(
                QRhiBuffer.Type.Dynamic,
                QRhiBuffer.UsageFlag.UniformBuffer,
                self.uniform_size,
            )
            if not buffer.create():
                raise RuntimeError("Failed to create feature uniform buffer")
            srb = self.rhi.newShaderResourceBindings()
            srb.setBindings([QRhiShaderResourceBinding.uniformBuffer(0, stage, buffer)])
            if not srb.create():
                raise RuntimeError("Failed to create feature SRB")
            self.uniform_buffers.append(buffer)
            self.srbs.append(srb)
        if not self.pipeline_created and self.srbs:
            self.pipeline.setShaderResourceBindings(self.srbs[0])
            if not self.pipeline.create():
                raise RuntimeError("Failed to create feature pipeline")
            self.pipeline_created = True

    def prepare_vertex_buffer(self, resource_updates) -> None:
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, FULLSCREEN_VERTICES)

    def release(self) -> None:
        for resource in (
            self.pipeline,
            *self.srbs,
            *self.uniform_buffers,
            self.vertex_buffer,
        ):
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.rhi = None
        self.vertex_buffer = None
        self.pipeline = None
        self.uniform_buffers = []
        self.srbs = []
        self.pipeline_created = False
