"""QRhi render pass: dim the canvas area outside a focused slot's image.

When a slot is focused (single-click, see drag_drop_overlay's
end_slot_press), ``composition_builder`` collapses the tree to just that
slot's ``LayerNode`` -- its own image aspect ratio becomes the composition's
native canvas size, so the image fills the composition canvas exactly (no
internal letterboxing). The only bars left are the canvas-vs-framebuffer
ones (``ctx.offset``/``ctx.scale`` in ``build_render_context``), i.e. the
"sides of the image" on the canvas itself -- this pass paints translucent
black over exactly those bars.

The bars are plain axis-aligned rectangles, so they draw as solid-color
NDC-bounded quads through the shared fullscreen-quad uniform shell
(``engine.overlay.OverlayShell``) rather than a fullscreen raster: geometry
is built in framebuffer px and packed with the shared
``engine.overlay.pack_grid_dividers`` packer (fb-rect -> NDC bounds + color,
the same conversion ``grid_dividers`` uses). No GPU allocation, no bespoke
pipeline builders, no draw-recorder calls here -- those live in the shell;
this pass only declares its binding, resolves per-frame packed blocks, and
stages them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from PySide6.QtGui import QColor, QRhiScissor

from engine.frame.context import make_ids
from engine.overlay import (
    GRID_DIVIDER_UNIFORM_SIZE,
    OverlayBinding,
    OverlayResolver,
    OverlayShell,
    RectItem,
    Rgba,
    pack_grid_dividers,
)
from ui.canvas_infra.scene.pass_contract import (
    CanvasRenderPass,
    SceneVisibility,
)
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

logger = logging.getLogger("ImproveImgSLI")

DIM_COLOR = QColor(0, 0, 0, 235)
#: Linear float form of ``DIM_COLOR`` for the engine-typed packed uniform
#: (the shell/wire color type is ``Rgba``, never a host ``QColor``).
_DIM_RGBA = Rgba(
    DIM_COLOR.redF(),
    DIM_COLOR.greenF(),
    DIM_COLOR.blueF(),
    DIM_COLOR.alphaF(),
)

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="focus_dim",
    uniform_size=GRID_DIVIDER_UNIFORM_SIZE,
)


def focus_dim_rects(ctx: Any) -> tuple[RectItem, ...]:
    """The 0-4 dim bars (framebuffer px) around the focused image in ``ctx``.

    Pure geometry, byte-for-byte the bounds the retired raster pass painted:
    the area outside the letterboxed image within the framebuffer -- top
    ``0..oy``, bottom ``oy+image_h..fb_h``, left ``0..ox`` within
    ``[top, bottom]``, right ``ox+image_w..fb_w`` -- skipping zero-area bars.
    """
    fb_w, fb_h = ctx.framebuffer_size
    fb_w, fb_h = max(1, int(fb_w)), max(1, int(fb_h))
    ox, oy = ctx.offset
    comp = ctx.composition
    image_w = max(1, int(comp.canvas_w)) * ctx.scale
    image_h = max(1, int(comp.canvas_h)) * ctx.scale
    top = max(0, int(round(oy)))
    bottom = min(fb_h, int(round(oy + image_h)))
    left = max(0, int(round(ox)))
    right = min(fb_w, int(round(ox + image_w)))

    rects: list[RectItem] = []
    if top > 0:
        rects.append(RectItem(0.0, 0.0, float(fb_w), float(top), _DIM_RGBA))
    if bottom < fb_h:
        rects.append(
            RectItem(0.0, float(bottom), float(fb_w), float(fb_h - bottom), _DIM_RGBA)
        )
    if left > 0:
        rects.append(
            RectItem(0.0, float(top), float(left), float(bottom - top), _DIM_RGBA)
        )
    if right < fb_w:
        rects.append(
            RectItem(
                float(right),
                float(top),
                float(fb_w - right),
                float(bottom - top),
                _DIM_RGBA,
            )
        )
    return tuple(rects)


def resolve(ctx: Any) -> tuple[bytes, ...]:
    """Ctx-first resolver: ctx in, packed uniform blocks out (or empty).

    Reuses the shared grid-dividers packer (framebuffer-px rect -> NDC
    bounds + per-item color); no second quad packer is introduced.
    """
    fb_w, fb_h = (float(value) for value in ctx.framebuffer_size)
    if fb_w <= 0.0 or fb_h <= 0.0:
        return ()
    matrix = tuple(float(value) for value in ctx.clip_matrix)
    return pack_grid_dividers(focus_dim_rects(ctx), matrix, fb_w, fb_h)


class FocusDimPass(CanvasRenderPass):
    stack_role = CanvasStackRole.HUD_LABEL
    visibility = SceneVisibility.ALL

    def __init__(self) -> None:
        self._shell = OverlayShell(GRID_DIVIDER_UNIFORM_SIZE)
        self._items: list[bytes] = []

    def should_paint(self, ctx) -> bool:
        widget = ctx.widget
        state = getattr(widget, "state", None)
        return bool(
            state is not None
            and getattr(state, "is_focused", False)
            and ctx.composition is not None
        )

    def initialize(self, rhi, target) -> None:
        self._shell.mount(rhi, target, BINDING.shader_dir, BINDING.shader_stem)

    def prepare(self, widget, ctx, resource_updates, frame_context=None) -> None:
        self._items = list(resolve(ctx))
        self._shell.stage_packed(resource_updates, self._items)

    def record(self, command_buffer, widget, ctx, frame_context=None) -> None:
        # Frame bus: overlay fact (record only, never instead). Verdict
        # from this pass's own should_paint gate; None-safe (unwired
        # callers stay silent).
        if frame_context is not None:
            _gate = self.should_paint(ctx)
            _count = len(self._items)
            frame_context.record(
                "overlay.focus_dim",
                "ran" if _gate else "skipped",
                f"overlay.focus_dim items={_count}",
                ids=make_ids(frame_context.frame_id, _count),
            )
        if getattr(widget, "_mc_overlay_debug", False):
            logger.info(
                "[mc-overlay-debug] %s.record: items=%s pipeline=%s",
                type(self).__name__,
                len(self._items),
                self._shell.pipeline is not None,
            )
        if not self._items:
            return
        fb_w, fb_h = ctx.framebuffer_size
        # Full-target scissor only -- per-bar bounds live in the fragment
        # shader (fullscreen quad, one uniform block per bar). A full-target
        # scissor is Y-convention-agnostic, so it needs no widget/rhi reads
        # and record() stays ctx-only.
        scissor = QRhiScissor(0, 0, int(round(float(fb_w))), int(round(float(fb_h))))
        self._shell.draw(
            command_buffer,
            width=float(fb_w),
            height=float(fb_h),
            scissor=scissor,
            count=len(self._items),
        )

    def release(self) -> None:
        self._shell.teardown()
        self._items = []


RENDER_PASSES: list[CanvasRenderPass] = [FocusDimPass()]
