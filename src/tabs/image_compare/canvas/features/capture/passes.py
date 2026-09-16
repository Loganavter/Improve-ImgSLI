from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.overlay import (
    CAPTURE_UNIFORM_SIZE,
    DiskItem,
    OverlayBinding,
    OverlayShell,
    Rgba,
    SemanticOverlayItems,
    SemanticResolver,
    pack_capture,
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

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="capture",
    uniform_size=CAPTURE_UNIFORM_SIZE,
)


def _semantic_resolver(widget) -> SemanticResolver:
    """Ctx-first semantic resolver: ctx in, canvas-px ring items out.

    Ring decisions are stateless (overlay_model); this binding only adapts
    them to engine-typed items -- byte layout lives shell-side in
    ``pack_capture``.
    """

    def resolve(ctx: Any) -> SemanticOverlayItems:
        return tuple(
            DiskItem(
                cx=ring.center_x,
                cy=ring.center_y,
                radius=ring.screen_radius,
                line_width_key="annotation_ring_stroke_px",
                color=Rgba(ring.red, ring.green, ring.blue, ring.alpha),
                extra=(ring.line_width,),
            )
            for ring in resolve_capture_rings(ctx, widget)
        )

    return resolve


class CaptureRingPass(CanvasRenderPass):
    """Draw capture-area rings for all visible magnifier instances."""

    stack_role = CanvasStackRole.ANNOTATION_RING
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = OverlayShell(CAPTURE_UNIFORM_SIZE)
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
        matrix = self._shell.clip_matrix()
        items = _semantic_resolver(widget)(ctx)
        blocks = pack_capture(items, matrix, float(ctx.width), float(ctx.height))
        self._items = list(blocks)
        self._shell.stage_packed(resource_updates, blocks)

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
