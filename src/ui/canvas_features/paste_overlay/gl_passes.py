from __future__ import annotations

import logging
import struct
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QPainter,
    QPen,
    QRhiBuffer,
    QRhiCommandBuffer,
    QRhiGraphicsPipeline,
    QRhiSampler,
    QRhiShaderResourceBinding,
    QRhiShaderStage,
    QRhiTexture,
    QRhiVertexInputAttribute,
    QRhiVertexInputBinding,
    QRhiVertexInputLayout,
    QRhiViewport,
)

from ui.canvas_infra.scene.gl_pass_contract import CanvasRenderPass, SceneVisibility
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.gl_canvas.render_common import new_overlay_image
from ui.widgets.gl_canvas.render_metrics import resolve_screen_px
from ui.widgets.gl_canvas.rhi_feature_common import FULLSCREEN_VERTICES, load_qshader
from ui.widgets.gl_canvas.style_tokens import DEFAULT_CANVAS_STYLE_TOKENS

_log = logging.getLogger("ImproveImgSLI.paste_overlay")

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_SIZE = 64

def _draw_paste_button(
    painter: QPainter,
    rect: QRectF,
    text: str,
    hovered: bool,
    metrics,
) -> None:
    visual_width = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_width_du,
        metrics,
    )
    visual_height = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_visual_height_du,
        metrics,
    )
    radius = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_radius_du,
        metrics,
    )
    border_width = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_hover_du
        if hovered
        else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_border_du,
        metrics,
    )
    center = rect.center()
    visual_rect = QRectF(
        center.x() - (visual_width / 2.0),
        center.y() - (visual_height / 2.0),
        visual_width,
        visual_height,
    )

    if hovered:
        bg_color = QColor(255, 255, 255, 22)
        text_color = QColor(255, 255, 255)
        border_color = QColor(100, 150, 255)
    else:
        bg_color = QColor(255, 255, 255, 10)
        text_color = QColor(248, 248, 248)
        border_color = QColor(255, 255, 255, 96)

    painter.setPen(QPen(border_color, border_width))
    painter.setBrush(bg_color)
    painter.drawRoundedRect(visual_rect, radius, radius)

    font = QFont(painter.font())
    font.setPixelSize(max(
        1,
        int(round(resolve_screen_px(
            DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_hover_base_du
            if hovered
            else DEFAULT_CANVAS_STYLE_TOKENS.overlay_button_font_base_du,
            metrics,
        )))
    ))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    font.setBold(hovered)
    painter.setFont(font)
    painter.setPen(text_color)
    painter.drawText(visual_rect, Qt.AlignmentFlag.AlignCenter, text)

def _draw_paste_overlay(painter: QPainter, widget, metrics) -> None:
    state = widget.runtime_state
    width = widget.width()
    height = widget.height()
    if width <= 0 or height <= 0:
        return

    backdrop_alpha = max(
        0,
        min(
            255,
            int(round(DEFAULT_CANVAS_STYLE_TOKENS.overlay_backdrop_alpha)),
        ),
    )
    painter.fillRect(0, 0, width, height, QColor(0, 0, 0, backdrop_alpha))

    buttons = []
    texts = state._paste_overlay_texts
    rects = state._paste_overlay_rects
    if not rects["up"].isNull():
        buttons.append(("up", rects["up"], texts.get("up", "")))
    if not rects["down"].isNull():
        buttons.append(("down", rects["down"], texts.get("down", "")))
    if not rects["left"].isNull():
        buttons.append(("left", rects["left"], texts.get("left", "")))
    if not rects["right"].isNull():
        buttons.append(("right", rects["right"], texts.get("right", "")))

    for direction, rect, text in buttons:
        _draw_paste_button(
            painter,
            rect,
            text,
            state._paste_overlay_hovered_button == direction,
            metrics,
        )

    cancel_rect = rects["cancel"]
    if cancel_rect.isNull():
        return
    is_cancel_hovered = state._paste_overlay_hovered_button == "cancel"
    cancel_stroke = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_stroke_du,
        metrics,
    )
    cancel_icon = resolve_screen_px(
        DEFAULT_CANVAS_STYLE_TOKENS.overlay_cancel_icon_du,
        metrics,
    )
    cancel_bg = (
        QColor(220, 220, 220, 200)
        if is_cancel_hovered
        else QColor(180, 180, 180, 150)
    )
    painter.setPen(QPen(QColor(100, 100, 100), cancel_stroke))
    painter.setBrush(cancel_bg)
    painter.drawEllipse(cancel_rect)

    painter.setPen(QPen(QColor(80, 80, 80), cancel_stroke))
    center = cancel_rect.center()
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() - cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() + cancel_icon),
    )
    painter.drawLine(
        int(center.x() - cancel_icon),
        int(center.y() + cancel_icon),
        int(center.x() + cancel_icon),
        int(center.y() - cancel_icon),
    )

def build_ui_overlay_image(widget, metrics) -> QImage | None:
    state = widget.runtime_state
    width = int(widget.width())
    height = int(widget.height())
    if width <= 0 or height <= 0:
        return None
    if not state._paste_overlay_visible:
        return None

    dpr = max(1.0, float(widget.devicePixelRatioF()))
    image = new_overlay_image(max(1, int(round(width * dpr))), max(1, int(round(height * dpr))))
    painter = QPainter(image)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.scale(dpr, dpr)
        _draw_paste_overlay(painter, widget, metrics)
    finally:
        painter.end()
    return image


class PasteOverlayPass(CanvasRenderPass):
    stack_role = CanvasStackRole.TRANSIENT_PREVIEW
    visibility = SceneVisibility.INTERACTIVE

    def __init__(self) -> None:
        self.rhi = None
        self.vertex_buffer = None
        self.uniform_buffer = None
        self.sampler = None
        self.texture = None
        self.srb = None
        self.pipeline = None
        self._target = None
        self._texture_size: QSize | None = None
        self._pending_image: QImage | None = None

    def initialize(self, rhi, target) -> None:
        self.release()
        self.rhi = rhi
        self._target = target

        self.vertex_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.VertexBuffer,
            len(FULLSCREEN_VERTICES),
        )
        if not self.vertex_buffer.create():
            raise RuntimeError("Failed to create paste_overlay vertex buffer")

        self.uniform_buffer = rhi.newBuffer(
            QRhiBuffer.Type.Dynamic,
            QRhiBuffer.UsageFlag.UniformBuffer,
            _UNIFORM_SIZE,
        )
        if not self.uniform_buffer.create():
            raise RuntimeError("Failed to create paste_overlay uniform buffer")

        self.sampler = rhi.newSampler(
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.Linear,
            QRhiSampler.Filter.None_,
            QRhiSampler.AddressMode.ClampToEdge,
            QRhiSampler.AddressMode.ClampToEdge,
        )
        if not self.sampler.create():
            raise RuntimeError("Failed to create paste_overlay sampler")

        self.texture = rhi.newTexture(QRhiTexture.Format.RGBA8, QSize(1, 1))
        if not self.texture.create():
            raise RuntimeError("Failed to create paste_overlay placeholder texture")
        self._texture_size = QSize(1, 1)

        self.srb = self._build_srb()

        self.pipeline = rhi.newGraphicsPipeline()
        self.pipeline.setShaderStages(
            [
                QRhiShaderStage(
                    QRhiShaderStage.Type.Vertex,
                    load_qshader(_SHADER_DIR / "paste_overlay.vert.qsb"),
                ),
                QRhiShaderStage(
                    QRhiShaderStage.Type.Fragment,
                    load_qshader(_SHADER_DIR / "paste_overlay.frag.qsb"),
                ),
            ]
        )
        self.pipeline.setTopology(QRhiGraphicsPipeline.Topology.TriangleStrip)
        self.pipeline.setSampleCount(target.sampleCount())
        self.pipeline.setShaderResourceBindings(self.srb)
        self.pipeline.setRenderPassDescriptor(target.renderPassDescriptor())

        blend = QRhiGraphicsPipeline.TargetBlend()
        blend.enable = True
        blend.srcColor = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstColor = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        blend.srcAlpha = QRhiGraphicsPipeline.BlendFactor.One
        blend.dstAlpha = QRhiGraphicsPipeline.BlendFactor.OneMinusSrcAlpha
        self.pipeline.setTargetBlends([blend])

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
            raise RuntimeError("Failed to create paste_overlay QRhi pipeline")

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
            raise RuntimeError("Failed to create paste_overlay SRB")
        return srb

    def should_paint(self, ctx) -> bool:
        widget = getattr(ctx, "widget", None)
        state = getattr(widget, "runtime_state", None) if widget is not None else None
        if state is None:
            return False
        return bool(getattr(state, "_paste_overlay_visible", False))

    def prepare(self, widget, ctx, resource_updates) -> None:
        image = build_ui_overlay_image(widget, ctx.metrics.render_metrics)
        if image is None or image.isNull():
            self._pending_image = None
            return
        image = image.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
        self._pending_image = image

        size = image.size()
        if self._texture_size is None or self._texture_size != size:
            if self.texture is not None:
                try:
                    self.texture.destroy()
                except RuntimeError:
                    pass
            self.texture = self.rhi.newTexture(QRhiTexture.Format.RGBA8, size)
            if not self.texture.create():
                raise RuntimeError("Failed to resize paste_overlay texture")
            self._texture_size = size
            if self.srb is not None:
                try:
                    self.srb.destroy()
                except RuntimeError:
                    pass
            self.srb = self._build_srb()

        resource_updates.updateDynamicBuffer(self.vertex_buffer, 0, FULLSCREEN_VERTICES)
        matrix = struct.pack(
            "<16f", *tuple(float(v) for v in self.rhi.clipSpaceCorrMatrix().data())
        )
        resource_updates.updateDynamicBuffer(self.uniform_buffer, 0, matrix)
        resource_updates.uploadTexture(self.texture, image)

    def record(self, command_buffer: QRhiCommandBuffer, widget, ctx) -> None:
        if self._pending_image is None or self.texture is None or self.pipeline is None:
            return
        dpr = max(1.0, float(widget.devicePixelRatioF()))
        fb_width = float(int(ctx.width) * dpr)
        fb_height = float(int(ctx.height) * dpr)
        command_buffer.setGraphicsPipeline(self.pipeline)
        command_buffer.setViewport(QRhiViewport(0.0, 0.0, fb_width, fb_height))
        command_buffer.setShaderResources(self.srb)
        command_buffer.setVertexInput(0, [(self.vertex_buffer, 0)])
        command_buffer.draw(4)

    def release(self) -> None:
        for resource in (
            self.pipeline,
            self.srb,
            self.texture,
            self.sampler,
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
        self.texture = None
        self.sampler = None
        self.uniform_buffer = None
        self.vertex_buffer = None
        self.rhi = None
        self._target = None
        self._texture_size = None
        self._pending_image = None


RENDER_PASSES: list[CanvasRenderPass] = [PasteOverlayPass()]
GL_RENDER_PASSES = RENDER_PASSES
