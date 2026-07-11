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
_UNIFORM_SIZE = 128


class GuidesPass(CanvasRenderPass):
    """Draw laser guide lines from capture center to magnifier circles."""

    stack_role = CanvasStackRole.ANNOTATION_GUIDE
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(_UNIFORM_SIZE)
        self._items: list[bytes] = []

    def initialize(self, rhi, target) -> None:
        self.resources.initialize(rhi, target, _SHADER_DIR, "guides")

    def should_paint(self, ctx) -> bool:
        state = getattr(ctx.widget, "runtime_state", None)
        return bool(
            not is_single_image_preview_scene(ctx)
            and state is not None
            and getattr(state, "_guide_sets", ())
            and ctx.width > 0
            and ctx.height > 0
        )

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        line_width = float(ctx.resolved_style.annotation_line_stroke_px)
        for (
            capture_center,
            capture_radius,
            target_centers,
            target_radii,
            color,
        ) in tuple(widget.runtime_state._guide_sets):
            if capture_center is None:
                continue
            end_x, end_y = widget_px_to_screen_px(
                widget,
                capture_center.x(),
                capture_center.y(),
                canvas_width=ctx.canvas_width,
                canvas_height=ctx.canvas_height,
                canvas_offset_x=ctx.canvas_offset_x,
                canvas_offset_y=ctx.canvas_offset_y,
            )
            end_radius = max(0.0, float(capture_radius or 0.0) * float(ctx.zoom_level))
            draw_color = QColor(color)
            targets = tuple(target_centers or ())
            radii = tuple(target_radii or ())
            for index, target_center in enumerate(targets):
                if target_center is None:
                    continue
                target_radius = (
                    radii[index]
                    if index < len(radii)
                    else (radii[-1] if radii else 0.0)
                )
                start_x, start_y = widget_px_to_screen_px(
                    widget,
                    target_center.x(),
                    target_center.y(),
                    canvas_width=ctx.canvas_width,
                    canvas_height=ctx.canvas_height,
                    canvas_offset_x=ctx.canvas_offset_x,
                    canvas_offset_y=ctx.canvas_offset_y,
                )
                self._items.append(
                    struct.pack(
                        "<32f",
                        *matrix,
                        float(ctx.width),
                        float(ctx.height),
                        float(start_x),
                        float(start_y),
                        float(end_x),
                        float(end_y),
                        max(
                            0.0,
                            float(target_radius or 0.0) * float(ctx.zoom_level),
                        ),
                        end_radius,
                        line_width,
                        0.0,
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


RENDER_PASSES: list[CanvasRenderPass] = [GuidesPass()]
RENDER_PASSES = RENDER_PASSES
