"""QRhi render pass for multi_compare grid dividers (uniform shell).

Geometry comes from the scene-side semantic seam
(``dividers.resolve_items()``: composition gaps -> canvas-clipped
framebuffer rects + color); this pass packs shell-side via
``engine.overlay.pack_grid_dividers`` (matrix from ``ctx.clip_matrix``)
and stages through ``OverlayShell.stage_packed``. No GPU allocation, no
bespoke pipeline, no draw-recorder calls here -- those live in the shell.

``fb_rect_to_ndc_quad`` stays as the pure CPU-side rect math pinned by the
dividers render tests; the frame path renders through the shared
fullscreen-quad shell, not NDC vertex quads.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QRhiScissor

from engine.cache.uniform_layout import assert_uniform_size
from engine.frame.context import make_ids
from engine.overlay import (
    OverlayBinding,
    OverlayResolver,
    OverlayShell,
    pack_grid_dividers,
)
from tabs.multi_compare.scene.passes.dividers import (
    DividersOverlaySource,
    resolve_items as resolve_divider_items,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
# std140: mat4 mvp (64) + vec4 NDC rect bounds x0/y0/x1/y1 (16) + vec4
# color (16) = 96. Deprecated aliases of GRID_DIVIDER_UNIFORM_FMT/SIZE
# (engine.overlay.semantic): pinned by the F1 layout-marker dogma in
# tests/contracts/test_overlay_shell.py -- F6 retires them with the v1 seam.
_UNIFORM_FMT = "<24f"
_UNIFORM_SIZE = 96
assert_uniform_size(_UNIFORM_FMT, _UNIFORM_SIZE, label="GridDividersPass uniform")

BINDING = OverlayBinding(
    shader_dir=_SHADER_DIR,
    shader_stem="grid_divider",
    uniform_size=_UNIFORM_SIZE,
)


def fb_rect_to_ndc_quad(rect: QRectF, fb_w: float, fb_h: float) -> bytes:
    """Pack one triangle-strip quad (TL, BL, TR, BR) in NDC for ``rect`` in FB px."""

    if fb_w <= 0.0 or fb_h <= 0.0 or rect.width() <= 0.0 or rect.height() <= 0.0:
        return b""
    x0 = float(rect.x())
    y0 = float(rect.y())
    x1 = x0 + float(rect.width())
    y1 = y0 + float(rect.height())
    # FB px (origin top-left) → NDC; Y flips so +y is up in clip space.
    def ndc(x: float, y: float) -> tuple[float, float]:
        return (2.0 * x / fb_w) - 1.0, 1.0 - (2.0 * y / fb_h)

    tl = ndc(x0, y0)
    bl = ndc(x0, y1)
    tr = ndc(x1, y0)
    br = ndc(x1, y1)
    return struct.pack(
        "<16f",
        tl[0],
        tl[1],
        0.0,
        0.0,
        bl[0],
        bl[1],
        0.0,
        1.0,
        tr[0],
        tr[1],
        1.0,
        0.0,
        br[0],
        br[1],
        1.0,
        1.0,
    )


def resolve(ctx: Any) -> tuple[bytes, ...]:
    """Ctx-first uniform-block resolver (OverlayResolver): ctx in, packed blocks out.

    Consumes the scene semantic seam (``dividers.resolve_items(ctx)`` owns
    gap geometry, canvas clipping, and color) and packs shell-side via
    ``pack_grid_dividers`` with the frame matrix from ``ctx.clip_matrix``.
    No geometry is decided here and no blocks are unpacked/repacked -- the
    items pack straight to the 96B NDC-bounds blocks the shell stages.
    ``OverlayResolver`` names the satisfied protocol (ctx-first intake).
    """
    fb_w, fb_h = (float(value) for value in ctx.framebuffer_size)
    if fb_w <= 0.0 or fb_h <= 0.0:
        return ()
    matrix = tuple(float(value) for value in ctx.clip_matrix)
    return pack_grid_dividers(resolve_divider_items(ctx), matrix, fb_w, fb_h)


class GridDividersPass(CanvasRenderPass):
    """Draw every N-way grid split as a shell-rendered solid-color rect."""

    stack_role = CanvasStackRole.UNDERLAY_SPLIT

    def __init__(self) -> None:
        self._shell = OverlayShell(_UNIFORM_SIZE)
        self._source = DividersOverlaySource()
        self._items: list[bytes] = []

    def should_paint(self, ctx) -> bool:
        return self._source.should_paint(ctx.composition)

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
                "overlay.dividers",
                "ran" if _gate else "skipped",
                f"overlay.dividers items={_count}",
                ids=make_ids(frame_context.frame_id, _count),
            )
        if not self._items:
            return
        fb_w, fb_h = ctx.framebuffer_size
        # Full-target scissor only -- per-divider bounds live in the
        # fragment shader (fullscreen quad, one uniform block per divider).
        # A full-target scissor is Y-convention-agnostic, so it needs no
        # widget/rhi reads and record() stays ctx-only.
        scissor = QRhiScissor(
            0, 0, int(round(float(fb_w))), int(round(float(fb_h)))
        )
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


RENDER_PASSES: list[CanvasRenderPass] = [GridDividersPass()]
RENDER_PASSES = RENDER_PASSES
