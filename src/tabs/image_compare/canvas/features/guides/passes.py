from __future__ import annotations

import struct
from pathlib import Path

from engine.cache.uniform_layout import assert_uniform_size

from PySide6.QtGui import QRhiViewport

from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from tabs.image_compare.canvas.features.guides.overlay_model import (
    resolve_guide_spans,
)
from tabs.image_compare.canvas.rhi_feature_common import (
    FullscreenUniformPassResources,
    resolve_rhi_scissor,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_FMT = "<32f"
_UNIFORM_SIZE = 128
assert_uniform_size(_UNIFORM_FMT, _UNIFORM_SIZE, label="GuidesPass uniform")


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
        # Span decisions are stateless (overlay_model); this shell only packs
        # them into per-item uniform blocks and stages the GPU buffers.
        for span in resolve_guide_spans(ctx, widget, matrix):
            self._items.append(
                struct.pack(
                    _UNIFORM_FMT,
                    *matrix,
                    float(ctx.width),
                    float(ctx.height),
                    span.start_x,
                    span.start_y,
                    span.end_x,
                    span.end_y,
                    span.start_radius,
                    span.end_radius,
                    span.line_width,
                    0.0,
                    0.0,
                    0.0,
                    span.red,
                    span.green,
                    span.blue,
                    span.alpha,
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
