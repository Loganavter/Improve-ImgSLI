from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import QColor, QRhiViewport

from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from ui.widgets.canvas.render_common import widget_px_to_screen_px
from tabs.image_compare.canvas.rhi_feature_common import (
    FullscreenUniformPassResources,
    resolve_rhi_scissor,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_SIZE = 112


class CaptureRingPass(CanvasRenderPass):
    """Draw capture-area rings for all visible magnifier instances."""

    stack_role = CanvasStackRole.ANNOTATION_RING
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(_UNIFORM_SIZE)
        self._items: list[bytes] = []

    @staticmethod
    def _resolve_capture_circles(widget, ctx) -> tuple:
        overlay = getattr(ctx, "feature_overlay", None)
        circles = tuple(getattr(overlay, "capture_circles", ()) or ())
        if circles:
            return circles
        payloads = (
            ctx.scene_frame.feature_payloads
            if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
            else {}
        )
        circles = payloads.get("capture_circles")
        if circles:
            return tuple(circles)
        return tuple(getattr(widget.runtime_state, "_capture_circles", ()))

    def initialize(self, rhi, target) -> None:
        self.resources.initialize(rhi, target, _SHADER_DIR, "capture")

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_capture_circles(ctx.widget, ctx))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        line_width = float(ctx.resolved_style.annotation_ring_stroke_px)
        for center, radius, color in self._resolve_capture_circles(widget, ctx):
            if center is None or float(radius or 0.0) <= 0.0:
                continue
            center_x, center_y = widget_px_to_screen_px(
                widget,
                center.x(),
                center.y(),
                canvas_width=ctx.canvas_width,
                canvas_height=ctx.canvas_height,
                canvas_offset_x=ctx.canvas_offset_x,
                canvas_offset_y=ctx.canvas_offset_y,
            )
            draw_color = QColor(color)
            draw_color.setAlpha(255)
            self._items.append(
                struct.pack(
                    "<28f",
                    *matrix,
                    float(ctx.width),
                    float(ctx.height),
                    float(center_x),
                    float(center_y),
                    float(radius) * float(ctx.zoom_level),
                    line_width,
                    0.0,
                    0.0,
                    draw_color.redF(),
                    draw_color.greenF(),
                    draw_color.blueF(),
                    draw_color.alphaF(),
                )
            )
        self.resources.ensure_items(len(self._items))
        self.resources.prepare_vertex_buffer(resource_updates)
        for index, block in enumerate(self._items):
            resource_updates.updateDynamicBuffer(
                self.resources.uniform_buffers[index], 0, block
            )

    def record(self, command_buffer, widget, ctx) -> None:
        if not self._items:
            return
        command_buffer.setGraphicsPipeline(self.resources.pipeline)
        target_size = widget.renderTarget().pixelSize()
        command_buffer.setViewport(
            QRhiViewport(
                0.0,
                0.0,
                float(target_size.width()),
                float(target_size.height()),
            )
        )
        command_buffer.setScissor(
            resolve_rhi_scissor(
                widget,
                self.resources.rhi,
                ctx,
                clip_to_content=bool(
                    widget.runtime_state._clip_overlays_to_content_rect
                ),
            )
        )
        command_buffer.setVertexInput(0, [(self.resources.vertex_buffer, 0)])
        for index in range(len(self._items)):
            command_buffer.setShaderResources(self.resources.srbs[index])
            command_buffer.draw(4)

    def release(self) -> None:
        self.resources.release()
        self._items = []


RENDER_PASSES: list[CanvasRenderPass] = [CaptureRingPass()]
RENDER_PASSES = RENDER_PASSES
