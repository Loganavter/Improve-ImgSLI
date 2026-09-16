from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.overlay import (
    GUIDES_UNIFORM_SIZE,
    DiskItem,
    OverlayBinding,
    OverlayShell,
    Rgba,
    SemanticOverlayItems,
    SemanticResolver,
    pack_guides,
)

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
    resolve_rhi_scissor,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="guides",
    uniform_size=GUIDES_UNIFORM_SIZE,
)


def _semantic_resolver(widget) -> SemanticResolver:
    """Ctx-first semantic resolver: ctx in, canvas-px span items out.

    Span decisions are stateless (overlay_model); this binding only adapts
    them to engine-typed items -- byte layout lives shell-side in
    ``pack_guides``.
    """

    def resolve(ctx: Any) -> SemanticOverlayItems:
        return tuple(
            DiskItem(
                cx=span.start_x,
                cy=span.start_y,
                radius=span.start_radius,
                line_width_key="annotation_line_stroke_px",
                color=Rgba(span.red, span.green, span.blue, span.alpha),
                extra=(span.end_x, span.end_y, span.end_radius, span.line_width),
            )
            for span in resolve_guide_spans(ctx, widget)
        )

    return resolve


class GuidesPass(CanvasRenderPass):
    """Draw laser guide lines from capture center to magnifier circles."""

    stack_role = CanvasStackRole.ANNOTATION_GUIDE
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = OverlayShell(GUIDES_UNIFORM_SIZE)
        self._items: list[bytes] = []

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

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
        matrix = self._shell.clip_matrix()
        items = _semantic_resolver(widget)(ctx)
        blocks = pack_guides(items, matrix, float(ctx.width), float(ctx.height))
        self._items = list(blocks)
        self._shell.stage_packed(resource_updates, blocks)

    def record(self, command_buffer, widget, ctx) -> None:
        if not self._items:
            return
        target_size = widget.renderTarget().pixelSize()
        scissor = resolve_rhi_scissor(
            widget,
            self._shell.rhi,
            ctx,
            clip_to_content=bool(
                widget.runtime_state._clip_overlays_to_content_rect
            ),
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


RENDER_PASSES: list[CanvasRenderPass] = [GuidesPass()]
RENDER_PASSES = RENDER_PASSES
