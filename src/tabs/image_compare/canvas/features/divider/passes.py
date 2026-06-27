from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import (
    QColor,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiScissor,
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
from ui.canvas_infra.viewport.state import get_display_split_position
from ui.widgets.canvas.render_common import widget_px_to_screen_px

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
_UNIFORM_SIZE = 112


def _load_shader(name: str) -> QShader:
    shader = QShader.fromSerialized((_SHADER_DIR / name).read_bytes())
    if not shader.isValid():
        raise RuntimeError(f"Invalid divider shader: {name}")
    return shader


def _divider_clip_rect_px(widget) -> tuple[int, int, int, int] | None:
    state = widget.runtime_state
    content_rect = state._content_rect_px
    if not content_rect:
        return None

    x, y, width, height = content_rect
    scene = state._render_scene
    clip_rect = getattr(scene, "overlay_clip_rect", None)
    image = state._stored_pil_images[0] if state._stored_pil_images else None
    if (
        clip_rect
        and image is not None
        and getattr(image, "width", 0) > 0
        and getattr(image, "height", 0) > 0
    ):
        clip_x, clip_y, clip_width, clip_height = clip_rect
        x += int(round((clip_x / float(image.width)) * width))
        y += int(round((clip_y / float(image.height)) * height))
        width = int(round((clip_width / float(image.width)) * width))
        height = int(round((clip_height / float(image.height)) * height))

    x0, y0 = widget_px_to_screen_px(widget, x, y)
    x1, y1 = widget_px_to_screen_px(widget, x + width, y + height)
    return (
        int(round(min(x0, x1))),
        int(round(min(y0, y1))),
        max(0, int(round(abs(x1 - x0)))),
        max(0, int(round(abs(y1 - y0)))),
    )


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
    def _resolve_divider_state(widget, ctx) -> tuple[bool, float, float, bool, QColor]:
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        show_divider = bool(payloads.get("show_divider", False))
        thickness_px = float(payloads.get("divider_thickness", 0) or 0)
        color = QColor(payloads.get("divider_color", QColor(255, 255, 255, 255)))
        is_horizontal = bool(getattr(ctx.scene_frame, "is_horizontal", False))
        display_split = float(get_display_split_position(widget) or 0.5)
        position_px = (
            float(widget.height()) * display_split
            if is_horizontal
            else float(widget.width()) * display_split
        )
        return show_divider, position_px, thickness_px, is_horizontal, color

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
        show, _position, thickness, _horizontal, _color = self._resolve_divider_state(
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
        _show, position, thickness, horizontal, color = self._resolve_divider_state(
            widget, ctx
        )
        matrix = tuple(float(value) for value in self.rhi.clipSpaceCorrMatrix().data())
        block = struct.pack(
            "<24fi3f",
            *matrix,
            float(ctx.width),
            float(ctx.height),
            position,
            thickness * 0.5,
            color.redF(),
            color.greenF(),
            color.blueF(),
            color.alphaF(),
            int(horizontal),
            0.0,
            0.0,
            0.0,
        )
        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, _VERTICES)
        resource_updates.updateDynamicBuffer(self.uniform_buffer, 0, block)

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        clip = _divider_clip_rect_px(widget)
        if clip is None:
            return
        x, y, width, height = clip
        if width <= 0 or height <= 0:
            return
        if self.rhi.isYUpInFramebuffer():
            y = max(0, int(ctx.height) - (y + height))
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(
            QRhiViewport(0.0, 0.0, float(ctx.width), float(ctx.height))
        )
        command_buffer.setScissor(QRhiScissor(x, y, width, height))
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
