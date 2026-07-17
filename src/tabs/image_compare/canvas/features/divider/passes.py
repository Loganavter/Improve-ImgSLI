from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import (
    QColor,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
    QShader,
)

from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from tabs.image_compare.canvas.render_config import (
    get_view_transformed_content_rect_widget_px,
)
from tabs.image_compare.canvas.rhi_feature_common import scissor_from_widget_rect

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_VERTICES = struct.pack(
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
# std140: mat4(64) + vec2(8) + 2 floats(8) + vec4 color(16) + vec4 clip(16)
# + int(4) + pad(12) = 128
_UNIFORM_SIZE = 128


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid divider shader: {name}")
    return shader


def _content_split_visual(ctx) -> float:
    scene = getattr(ctx, "scene_frame", None)
    raw = getattr(scene, "split_position_visual", 0.5)
    if getattr(scene, "split_override", None) is not None:
        raw = scene.split_override
    return max(0.0, min(1.0, float(raw if raw is not None else 0.5)))


class DividerPass(CanvasRenderPass):
    stack_role = CanvasStackRole.UNDERLAY_SPLIT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.rhi = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.srb = None
        self.pipeline = None

    @staticmethod
    def _resolve_divider_state(widget, ctx):
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        show_divider = bool(payloads.get("show_divider", False))
        thickness_px = float(payloads.get("divider_thickness", 0) or 0)
        color = QColor(payloads.get("divider_color", QColor(255, 255, 255, 255)))
        is_horizontal = bool(getattr(ctx.scene_frame, "is_horizontal", False))
        spit = _content_split_visual(ctx)

        # Position + clip from the letterbox *after* the same zoom/pan as
        # base.frag. See docs/dev/rendering/investigations/divider-zoom-pan-detach.md.
        clip = get_view_transformed_content_rect_widget_px(widget)
        if clip is None:
            clip = (0.0, 0.0, float(ctx.canvas_width), float(ctx.canvas_height))
        cx, cy, cw, ch = (float(v) for v in clip)
        if is_horizontal:
            position_px = cy + ch * spit - float(ctx.canvas_offset_y)
        else:
            position_px = cx + cw * spit - float(ctx.canvas_offset_x)

        return show_divider, position_px, thickness_px, is_horizontal, color, (cx, cy, cw, ch)

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(_VERTICES),
        )
        self.vertex_buffer.create()
        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        self.uniform_buffer.create()
        self.srb = rhi.newShaderResourceBindings()
        stages = (
            QRhiShaderResourceBinding.StageFlag.VertexStage
            | QRhiShaderResourceBinding.StageFlag.FragmentStage
        )
        self.srb.setBindings(
            [QRhiShaderResourceBinding.uniformBuffer(0, stages, self.uniform_buffer)]
        )
        self.srb.create()

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex, _load_shader("divider.vert.qsb")
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment, _load_shader("divider.frag.qsb")
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setShaderResourceBindings(self.srb)
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())
        self.pipeline.setFlags(QRhiGraphicsPipeline.Flag.UsesScissor)
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
        self.pipeline.setVertexInputLayout(layout)
        if not self.pipeline.create():
            raise RuntimeError("Failed to create divider QRhi pipeline")

    def should_paint(self, ctx) -> bool:
        show, _position, thickness, _horizontal, _color, _clip = self._resolve_divider_state(
            ctx.widget, ctx
        )
        if is_single_image_preview_scene(ctx):
            return False
        images_uploaded = list(getattr(ctx, "images_uploaded", ()) or ())
        content_rect = getattr(ctx.scene_frame, "content_rect_px", None)
        return bool(
            show
            and thickness > 0.0
            and len(images_uploaded) >= 2
            and images_uploaded[0]
            and images_uploaded[1]
            and content_rect is not None
            and len(content_rect) >= 4
            and content_rect[2] > 0
            and content_rect[3] > 0
        )

    def prepare(self, widget, ctx, resource_updates) -> None:
        _show, position, thickness, horizontal, color, clip = self._resolve_divider_state(
            widget, ctx
        )
        matrix = tuple(float(value) for value in self.rhi.clipSpaceCorrMatrix().data())
        cx, cy, cw, ch = clip
        block = struct.pack(
            "<24f4fi3f",
            *matrix,
            float(ctx.width),
            float(ctx.height),
            position,
            thickness * 0.5,
            color.redF(),
            color.greenF(),
            color.blueF(),
            color.alphaF(),
            cx,
            cy,
            cw,
            ch,
            int(horizontal),
            0.0,
            0.0,
            0.0,
        )
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, _VERTICES)
        resource_updates.updateDynamicBuffer(self.uniform_buffer, 0, block)

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        target_size = widget.renderTarget().pixelSize()
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(
            QRhiViewport(
                0.0, 0.0, float(target_size.width()), float(target_size.height())
            )
        )
        # Full-target scissor only — content clip lives in the fragment shader
        # (docs/dev/rendering/investigations/divider-zoom-pan-detach.md).
        command_buffer.setScissor(
            scissor_from_widget_rect(
                widget, self.rhi, ctx, 0.0, 0.0, float(ctx.width), float(ctx.height)
            )
        )
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        command_buffer.draw(4)

    def release(self) -> None:
        for resource in (
            self.pipeline,
            self.srb,
            self.uniform_buffer,
            self.vertex_buffer,
        ):
            if resource is not None:
                try:
                    resource.destroy()
                except RuntimeError:
                    pass
        self.pipeline = None
        self.srb = None
        self.uniform_buffer = None
        self.vertex_buffer = None
        self.rhi = None


RENDER_PASSES: list[CanvasRenderPass] = [DividerPass()]
RENDER_PASSES = RENDER_PASSES
