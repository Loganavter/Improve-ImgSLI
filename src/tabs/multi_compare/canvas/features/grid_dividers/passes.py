"""QRhi render pass for multi_compare grid dividers (uniform shell).

Geometry comes from the scene-side ``dividers.resolve()`` seam
(composition gaps -> canvas-clipped framebuffer rects + color); this pass
only re-encodes each block's framebuffer-px rect into pre-clip NDC bounds
for the shared fullscreen-quad shell (``engine.overlay.OverlayShell``) and
stages one block per divider. No GPU allocation, no bespoke pipeline, no
draw-recorder calls here -- those live in the shell.

``fb_rect_to_ndc_quad`` stays as the pure CPU-side rect math pinned by the
dividers render tests; the frame path no longer uploads NDC vertex quads.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from PySide6.QtCore import QRectF
from PySide6.QtGui import QRhiScissor

from engine.cache.uniform_layout import assert_uniform_size
from engine.overlay import OverlayBinding, OverlayResolver, OverlayShell
from tabs.multi_compare.scene.passes.dividers import (
    _DIVIDER_BLOCK_FMT,
    DividersOverlaySource,
    resolve as resolve_divider_blocks,
)
from ui.canvas_infra.scene.pass_contract import CanvasRenderPass
from ui.canvas_infra.scene.stacking_policy import CanvasStackRole

_SHADER_DIR = Path(__file__).resolve().parent / "shaders"
# std140: mat4 mvp (64) + vec4 NDC rect bounds x0/y0/x1/y1 (16) + vec4
# color (16) = 96. Same skeleton as the scene seam's block (matrix + rect
# + color); only the rect encoding differs (NDC bounds here, framebuffer
# px there -- converted in resolve() below).
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


def _fb_rect_to_ndc_bounds(
    x: float, y: float, w: float, h: float, fb_w: float, fb_h: float
) -> tuple[float, float, float, float]:
    """Framebuffer-px rect (origin top-left) -> NDC bounds (x0, y0, x1, y1).

    Same formula as ``fb_rect_to_ndc_quad``'s ``ndc()`` above, repackaged
    as min/max bounds for the in-shader rect test: the shell draws a
    fullscreen quad, so each divider survives only as these bounds plus
    its color. Edges match the old vertex quads exactly (same space, same
    clip matrix), so coverage is identical for axis-aligned rects.
    """
    x0 = (2.0 * x / fb_w) - 1.0
    x1 = (2.0 * (x + w) / fb_w) - 1.0
    y_top = 1.0 - (2.0 * y / fb_h)
    y_bottom = 1.0 - (2.0 * (y + h) / fb_h)
    return (x0, y_bottom, x1, y_top)


def resolve(ctx: Any) -> tuple[bytes, ...]:
    """Ctx-first uniform-block resolver: ctx in, packed blocks out.

    Consumes the scene seam (``dividers.resolve(ctx)`` owns gap geometry,
    canvas clipping, and color) and re-encodes each block's rect into NDC
    bounds for this pass's shader. The matrix and color travel through
    verbatim; no geometry is decided here.
    """
    fb_w, fb_h = (float(value) for value in ctx.framebuffer_size)
    if fb_w <= 0.0 or fb_h <= 0.0:
        return ()
    blocks: list[bytes] = []
    for block in resolve_divider_blocks(ctx):
        values = struct.unpack(_DIVIDER_BLOCK_FMT, block)
        x, y, w, h = values[16:20]
        if w <= 0.0 or h <= 0.0:
            continue
        x0, y0, x1, y1 = _fb_rect_to_ndc_bounds(x, y, w, h, fb_w, fb_h)
        blocks.append(
            struct.pack(
                _UNIFORM_FMT,
                *values[:16],
                x0,
                y0,
                x1,
                y1,
                *values[20:24],
            )
        )
    return tuple(blocks)


def _blocks_resolver() -> OverlayResolver:
    """Resolver factory: geometry arrives via ``ctx``, nothing is captured.

    Mirrors the IC pilot ``_blocks_resolver`` call shape
    (``prepare`` invokes ``_blocks_resolver()(ctx)``); unlike the pilots
    there is no widget/matrix capture because the scene seam already binds
    its frame sources behind ``ctx``.
    """
    return resolve


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

    def prepare(self, widget, ctx, resource_updates) -> None:
        self._items = list(_blocks_resolver()(ctx))
        self._shell.ensure_slots(len(self._items))
        self._shell.stage_quad(resource_updates)
        for index, block in enumerate(self._items):
            self._shell.stage_slot(resource_updates, index, block)

    def record(self, command_buffer, widget, ctx) -> None:
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
