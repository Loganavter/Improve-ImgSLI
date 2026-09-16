from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from engine.cache.uniform_layout import assert_uniform_size
from engine.overlay import (
    OverlayBinding,
    OverlayResolver,
    OverlayShell,
    UniformPassView,
)
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
    resolve_rhi_scissor,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
_UNIFORM_FMT = "<28f"
_UNIFORM_SIZE = 112
assert_uniform_size(_UNIFORM_FMT, _UNIFORM_SIZE, label="CaptureRingPass uniform")

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="capture",
    uniform_size=_UNIFORM_SIZE,
)


def _blocks_resolver(widget, matrix: tuple) -> OverlayResolver:
    """Ctx-first uniform-block resolver: ctx in, packed blocks out."""

    def resolve(ctx: Any) -> tuple[bytes, ...]:
        # Ring decisions are stateless (overlay_model); this binding only packs
        # them into per-item uniform blocks.
        return tuple(
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
            for ring in resolve_capture_rings(ctx, widget)
        )

    return resolve


class CaptureRingPass(CanvasRenderPass):
    """Draw capture-area rings for all visible magnifier instances."""

    stack_role = CanvasStackRole.ANNOTATION_RING
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = OverlayShell(_UNIFORM_SIZE)
        self.resources = UniformPassView(self._shell)
        self._items: list[bytes] = []

    @staticmethod
    def _resolve_capture_circles(widget, ctx) -> tuple:
        # Stateless decision layer (overlay_model); shim preserves the
        # historical raw-circle return shape (see
        # test_runtime_overlay_snapshot_contracts.py).
        return resolve_capture_circles(ctx, widget)

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

    def should_paint(self, ctx) -> bool:
        if is_single_image_preview_scene(ctx):
            return False
        return bool(self._resolve_capture_circles(ctx.widget, ctx))

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = []
        matrix = tuple(
            float(value) for value in self.resources.rhi.clipSpaceCorrMatrix().data()
        )
        self._items = list(_blocks_resolver(widget, matrix)(ctx))
        self.resources.ensure_items(len(self._items))
        self.resources.prepare_vertex_buffer(resource_updates)
        for index, block in enumerate(self._items):
            resource_updates.updateDynamicBuffer(
                self.resources.uniform_buffers[index], 0, block
            )

    def record(self, command_buffer, widget, ctx) -> None:
        if not self._items:
            return
        target_size = widget.renderTarget().pixelSize()
        # The capture ring marks the sampled source region and must never
        # visually poke past the image edge (its centered stroke otherwise
        # overshoots the clamped fill radius by half the line width) —
        # unlike other overlays, this clip is unconditional, independent of
        # the shared content-rect clip flag used for split/padded-composite
        # isolation elsewhere.
        scissor = resolve_rhi_scissor(
            widget,
            self._shell.rhi,
            ctx,
            clip_to_content=True,
        )
        self._shell.draw(
            command_buffer,
            width=float(target_size.width()),
            height=float(target_size.height()),
            scissor=scissor,
            count=len(self._items),
        )

    def release(self) -> None:
        self._shell.teardown()
        self._items = []


RENDER_PASSES: list[CanvasRenderPass] = [CaptureRingPass()]
RENDER_PASSES = RENDER_PASSES
