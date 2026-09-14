from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtGui import QRhiViewport

from engine.cache.uniform_layout import assert_uniform_size
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from tabs.image_compare.canvas.features.capture.overlay_model import (
    resolve_capture_circles,
    resolve_capture_rings,
)
from tabs.image_compare.canvas.rhi_feature_common import (
    FullscreenUniformPassResources,
    resolve_rhi_scissor,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_FMT = "<28f"
_UNIFORM_SIZE = 112
assert_uniform_size(_UNIFORM_FMT, _UNIFORM_SIZE, label="CaptureRingPass uniform")


class CaptureRingPass(CanvasRenderPass):
    """Draw capture-area rings for all visible magnifier instances."""

    stack_role = CanvasStackRole.ANNOTATION_RING
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self.resources = FullscreenUniformPassResources(_UNIFORM_SIZE)
        self._items: list[bytes] = []

    @staticmethod
    def _resolve_capture_circles(widget, ctx) -> tuple:
        # Stateless decision layer (overlay_model); shim preserves the
        # historical raw-circle return shape (see
        # test_runtime_overlay_snapshot_contracts.py).
        return resolve_capture_circles(ctx, widget)

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
        # Ring decisions are stateless (overlay_model); this shell only packs
        # them into per-item uniform blocks and stages the GPU buffers.
        for ring in resolve_capture_rings(ctx, widget):
            self._items.append(
                struct.pack(
                    _UNIFORM_FMT,
                    *matrix,
                    float(ctx.width),
                    float(ctx.height),
                    ring.center_x,
                    ring.center_y,
                    ring.screen_radius,
                    ring.line_width,
                    0.0,
                    0.0,
                    ring.red,
                    ring.green,
                    ring.blue,
                    ring.alpha,
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
        # The capture ring marks the sampled source region and must never
        # visually poke past the image edge (its centered stroke otherwise
        # overshoots the clamped fill radius by half the line width) —
        # unlike other overlays, this clip is unconditional, independent of
        # the shared content-rect clip flag used for split/padded-composite
        # isolation elsewhere.
        command_buffer.setScissor(
            resolve_rhi_scissor(
                widget,
                self.resources.rhi,
                ctx,
                clip_to_content=True,
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
