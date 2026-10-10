"""Per-glyph quad packing for the filename_overlay SDF text pass (C1).

One quad per glyph sampling the ``GlyphAtlas``; positions are in the pass's
pixel-space (the vertex shader applies a pixel -> clip matrix), UVs point into
the atlas. The rounded-rect background is emitted as one extra quad (mode 0)
so background + text composite through a single pipeline in one pass.

Vertex layout (40 bytes, matches ``filename_overlay.vert`` /
``render/gpu_resources.py``)::

    location 0  vec2  position (px, y-down)
    location 1  vec2  atlas uv
    location 2  vec4  premultiplied color
    location 3  vec2  aux (x = mode 0=bg / 1=glyph, y = font weight)

The shader reads ``mode`` to pick the rounded-box background path vs the SDF
threshold path; ``weight`` rides aux.y so the synthetic-bold shift
(``sd -= weight/500 * pixel_size``) is per-glyph, not a per-pass constant.
"""

from __future__ import annotations

import struct

from tabs.image_compare.canvas.features.filename_overlay.render.glyph_atlas import (
    GlyphAtlas,
)

_VERTEX_FMT = "<10f"
_BG_MODE = 0.0
_GLYPH_MODE = 1.0


def _quad(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    u0: float,
    v0: float,
    u1: float,
    v1: float,
    color: tuple[float, float, float, float],
    mode: float,
    weight: float,
) -> bytes:
    r, g, b, a = color
    verts = (
        (x0, y0, u0, v0),
        (x1, y0, u1, v0),
        (x0, y1, u0, v1),
        (x1, y0, u1, v0),
        (x1, y1, u1, v1),
        (x0, y1, u0, v1),
    )
    out = bytearray()
    for px, py, u, v in verts:
        out += struct.pack(_VERTEX_FMT, px, py, u, v, r, g, b, a, mode, weight)
    return bytes(out)


def pack_bg_quad(
    rect_px: tuple[float, float, float, float],
    color: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
) -> bytes:
    """One mode-0 quad covering the label rect (``color`` unused -- the rounded
    box is built from the per-slot uniform's ``bgColor``/``quadSizePx``)."""
    x0, y0, x1, y1 = rect_px
    return _quad(x0, y0, x1, y1, 0.0, 0.0, 1.0, 1.0, color, _BG_MODE, 0.0)


def pack_run(
    text: str,
    atlas: GlyphAtlas,
    origin_px: tuple[float, float],
    color_rgba: tuple[float, float, float, float],
    weight: float,
    scale: float,
) -> tuple[bytes, int]:
    """Pack ``text`` into mode-1 glyph quads.

    ``origin_px`` is the baseline pen origin in screen px (y-down);
    ``scale`` is the on-screen logical-px-per-logical-atlas-px factor (zoom);
    ``weight`` rides aux.y for the shader's synthetic-bold shift. Returns
    ``(vertex_bytes, quad_count)``; empty text -> ``(b"", 0)``.
    """
    if not text or atlas.image is None:
        return b"", 0
    color = tuple(float(c) for c in color_rgba)
    scale = float(scale)
    pen_x = float(origin_px[0])
    pen_y = float(origin_px[1])
    out = bytearray()
    count = 0
    for ch in text:
        slot = atlas.slot_for(ch)
        if slot is None:
            continue
        w, h = slot.size_px
        if w > 0.0 and h > 0.0:
            x0 = pen_x + slot.bearing_px[0] * scale
            y0 = pen_y + slot.bearing_px[1] * scale
            x1 = x0 + w * scale
            y1 = y0 + h * scale
            u0, v0, u1, v1 = slot.uv
            out += _quad(x0, y0, x1, y1, u0, v0, u1, v1, color, _GLYPH_MODE, weight)
            count += 1
        pen_x += slot.advance_px * scale
    return bytes(out), count
