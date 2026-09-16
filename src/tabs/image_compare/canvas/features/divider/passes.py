from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from PySide6.QtGui import QColor

from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
    is_single_image_preview_scene,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole
from engine.cache.uniform_layout import assert_uniform_size
from engine.overlay import OverlayBinding, OverlayResolver, OverlayShell
from tabs.image_compare.canvas.rhi_feature_common import scissor_from_widget_rect
from tabs.image_compare.canvas.features.divider.overlay_model import (
    content_split_visual,
    resolve_divider_spec,
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
# std140: mat4(64) + vec2(8) + 2 floats(8) + vec4 color(16) + vec4 clip(16)
# + int(4) + pad(12) = 128
_UNIFORM_FMT = "<24f4fi3f"
_UNIFORM_SIZE = 128
assert_uniform_size(_UNIFORM_FMT, _UNIFORM_SIZE, label="DividerPass uniform")

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="divider",
    uniform_size=_UNIFORM_SIZE,
)


def _content_split_visual(ctx) -> float:
    return content_split_visual(ctx)


def _blocks_resolver(widget, matrix: tuple) -> OverlayResolver:
    """Ctx-first uniform-block resolver: ctx in, one packed block out."""

    def resolve(ctx: Any) -> tuple[bytes, ...]:
        _show, position, thickness, horizontal, color, clip = (
            DividerPass._resolve_divider_state(widget, ctx)
        )
        cx, cy, cw, ch = clip
        return (
            struct.pack(
                _UNIFORM_FMT,
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
            ),
        )

    return resolve


class DividerPass(CanvasRenderPass):
    stack_role = CanvasStackRole.UNDERLAY_SPLIT
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = OverlayShell(_UNIFORM_SIZE)

    @staticmethod
    def _resolve_divider_state(widget, ctx):
        # Stateless decision layer (overlay_model); this shim preserves the
        # historical tuple shape for should_paint/prepare below.
        spec = resolve_divider_spec(ctx, widget)
        return (
            spec.show,
            spec.position_px,
            spec.thickness_px,
            spec.is_horizontal,
            QColor.fromRgbF(spec.red, spec.green, spec.blue, spec.alpha),
            (spec.clip_x, spec.clip_y, spec.clip_w, spec.clip_h),
        )

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

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
        matrix = self._shell.clip_matrix()
        (block,) = _blocks_resolver(widget, matrix)(ctx)
        self._shell.ensure_slots(1)
        self._shell.stage_quad(resource_updates)
        self._shell.stage_slot(resource_updates, 0, block)

    def record(self, command_buffer, widget, ctx) -> None:
        target_size = widget.renderTarget().pixelSize()
        # Full-target scissor only — content clip lives in the fragment shader
        # (src/tabs/image_compare/docs/investigations/divider-zoom-pan-detach.md).
        scissor = scissor_from_widget_rect(
            widget, self._shell.rhi, ctx, 0.0, 0.0, float(ctx.width), float(ctx.height)
        )
        self._shell.draw(
            command_buffer,
            width=float(target_size.width()),
            height=float(target_size.height()),
            scissor=scissor,
            count=1,
        )

    def release(self) -> None:
        self._shell.teardown()


RENDER_PASSES: list[CanvasRenderPass] = [DividerPass()]
RENDER_PASSES = RENDER_PASSES
