"""Focus-dim bars render as solid NDC quads, not an uploaded raster.

Overdraw wave: ``FocusDimPass`` used to rasterize up to four translucent
bars into a fullscreen ``QImage`` + ``QPainter`` and upload it every active
frame. The bars are plain rectangles, so they now draw through the shared
fullscreen-quad uniform shell (``engine.overlay.OverlayShell``) with the
shared ``pack_grid_dividers`` NDC-bounds packer, exactly like
``grid_dividers``.

This file pins that migration without GPU (no QRhi host):

* the pure ``focus_dim_rects`` geometry is byte-for-byte the bounds the
  retired raster pass painted (the reference below replicates its literal
  ``painter.drawRect`` calls);
* the packed resolver emits one 96B NDC-bounds block per non-empty bar;
* the module no longer names ``QImage``/``QPainter`` or the textured shell.
"""

from __future__ import annotations

import struct
from pathlib import Path
from types import SimpleNamespace

from tabs.multi_compare.canvas.features.focus_dim.passes import (
    GRID_DIVIDER_UNIFORM_SIZE,
    focus_dim_rects,
    resolve,
)

_PASSES_PATH = (
    Path(__file__).resolve().parents[2] / "canvas" / "features" / "focus_dim" / "passes.py"
)

# 235/255 -- QColor(0, 0, 0, 235) in its 0..1 float form.
_DIM_ALPHA = 235 / 255.0


def _make_ctx(fb, offset, scale, canvas):
    return SimpleNamespace(
        framebuffer_size=fb,
        offset=offset,
        scale=scale,
        composition=SimpleNamespace(canvas_w=canvas[0], canvas_h=canvas[1]),
        clip_matrix=tuple(float(i) for i in range(16)),
    )


def _legacy_raster_bar_rects(ctx) -> list[tuple[int, int, int, int]]:
    """Framebuffer-px (x, y, w, h) of every bar the retired raster painted.

    Literal replay of the old ``_raster_image`` ``painter.drawRect`` calls
    (top / bottom / left / right, each skipped when it would be zero-area).
    """
    fb_w, fb_h = ctx.framebuffer_size
    fb_w, fb_h = max(1, int(fb_w)), max(1, int(fb_h))
    ox, oy = ctx.offset
    image_w = max(1, int(ctx.composition.canvas_w)) * ctx.scale
    image_h = max(1, int(ctx.composition.canvas_h)) * ctx.scale
    top = max(0, int(round(oy)))
    bottom = min(fb_h, int(round(oy + image_h)))
    left = max(0, int(round(ox)))
    right = min(fb_w, int(round(ox + image_w)))
    rects: list[tuple[int, int, int, int]] = []
    if top > 0:
        rects.append((0, 0, fb_w, top))
    if bottom < fb_h:
        rects.append((0, bottom, fb_w, fb_h - bottom))
    if left > 0:
        rects.append((0, top, left, bottom - top))
    if right < fb_w:
        rects.append((right, top, fb_w - right, bottom - top))
    return rects


def _rect_tuples(items) -> list[tuple[int, int, int, int]]:
    return [(int(r.x), int(r.y), int(r.w), int(r.h)) for r in items]


def test_focus_dim_rects_match_retired_raster_four_bars():
    ctx = _make_ctx((500, 500), (50, 60), 1.0, (300, 200))
    assert _rect_tuples(focus_dim_rects(ctx)) == _legacy_raster_bar_rects(ctx) == [
        (0, 0, 500, 60),
        (0, 260, 500, 240),
        (0, 60, 50, 200),
        (350, 60, 150, 200),
    ]


def test_focus_dim_rects_match_retired_raster_partial_bars():
    for ctx in (
        _make_ctx((800, 600), (100, 50), 1.0, (800, 600)),
        _make_ctx((640, 480), (0, 0), 2.0, (200, 150)),
        _make_ctx((800, 600), (0, 0), 1.0, (800, 600)),
    ):
        assert _rect_tuples(focus_dim_rects(ctx)) == _legacy_raster_bar_rects(ctx)


def test_focus_dim_rects_carry_exact_dim_color():
    ctx = _make_ctx((500, 500), (50, 60), 1.0, (300, 200))
    items = focus_dim_rects(ctx)
    assert items
    for item in items:
        assert (item.color.r, item.color.g, item.color.b) == (0.0, 0.0, 0.0)
        # QColor.alphaF() is float32-rounded; compare within a float tolerance.
        assert abs(item.color.a - _DIM_ALPHA) < 1e-6


def test_focus_dim_resolve_packs_one_ndc_block_per_bar():
    ctx = _make_ctx((500, 500), (50, 60), 1.0, (300, 200))
    blocks = resolve(ctx)
    assert len(blocks) == 4
    assert all(len(block) == GRID_DIVIDER_UNIFORM_SIZE for block in blocks)
    # After the 64B clip matrix: NDC bounds (x0, y0, x1, y1) then RGBA color.
    (first,) = blocks[:1]
    values = struct.unpack("<24f", first)
    assert values[20:23] == (0.0, 0.0, 0.0)
    assert abs(values[23] - _DIM_ALPHA) < 1e-6
    # Top bar spans the full framebuffer width: x0=-1, x1=+1.
    assert values[16] == -1.0
    assert values[18] == 1.0


def test_focus_dim_resolve_empty_when_no_bars():
    ctx = _make_ctx((800, 600), (0, 0), 1.0, (800, 600))
    assert resolve(ctx) == ()


def test_focus_dim_module_dropped_raster_and_textured_shell():
    text = _PASSES_PATH.read_text(encoding="utf-8")
    for banned in ("QImage", "QPainter", "TexturedOverlayShell", "upload_frame"):
        assert banned not in text, (
            f"focus_dim/passes.py still names {banned!r} -- the bars are "
            f"solid NDC quads through OverlayShell now, no raster upload"
        )
