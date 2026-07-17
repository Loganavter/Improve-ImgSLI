from __future__ import annotations

import struct

# std140 layout of base.frag/base.vert's UBuf: mat4 mvp(64) + vec2 offset(8)
# + vec2 zoom(8) + float splitPosition(4) + 12B pad + vec4 letterbox1(16) +
# vec4 letterbox2(16) + 4 ints(16) + float diffThreshold(4) + 12B pad +
# vec4 tileRect1(16) + vec4 tileRect2(16) + vec4 canvasLetterbox(16) +
# vec4 letterboxFill(16) = 224. zoom became vec2 in Phase 3
# (docs/dev/TILED_RENDERING_DESIGN.md) to support the anisotropic crop
# window tiled export needs; see pack_base_uniforms's format string, which
# must stay byte-for-byte in sync with this layout.
_UNIFORM_BLOCK_SIZE = 224

_FULL_TILE_RECT = (0.0, 0.0, 1.0, 1.0)
_DISABLED_CANVAS_LETTERBOX = (0.0, 0.0, 0.0, 0.0)
_DISABLED_LETTERBOX_FILL = (0.0, 0.0, 0.0, 0.0)


def pack_base_uniforms(
    rhi,
    base_image,
    *,
    diff_source_ready: bool,
    tile_rect1: tuple[float, float, float, float] = _FULL_TILE_RECT,
    tile_rect2: tuple[float, float, float, float] = _FULL_TILE_RECT,
    viewport_zoom: tuple[float, float] | None = None,
    viewport_offset: tuple[float, float] | None = None,
) -> bytes:
    """``viewport_zoom``/``viewport_offset`` override ``base_image.zoom``/
    ``pan_offset_x/y`` when given — used by tiled export (docs/dev/
    TILED_RENDERING_DESIGN.md Phase 3) to render an anisotropic crop window
    of the canvas into a tile-sized render target. ``None`` (the default,
    live/preview rendering) reproduces the prior isotropic behavior exactly:
    zoom.x == zoom.y == base_image.zoom."""
    matrix = tuple(float(value) for value in rhi.clipSpaceCorrMatrix().data())
    zoom_x, zoom_y = viewport_zoom or (float(base_image.zoom), float(base_image.zoom))
    offset_x, offset_y = viewport_offset or (
        float(base_image.pan_offset_x),
        float(base_image.pan_offset_y),
    )
    canvas_letterbox = getattr(
        base_image, "canvas_letterbox", None
    ) or _DISABLED_CANVAS_LETTERBOX
    letterbox_fill = getattr(
        base_image, "letterbox_fill", None
    ) or _DISABLED_LETTERBOX_FILL
    return struct.pack(
        "<32f4i20f",
        *matrix,
        offset_x,
        offset_y,
        zoom_x,
        zoom_y,
        float(base_image.split_position),
        0.0,
        0.0,
        0.0,
        *base_image.letterbox1,
        *base_image.letterbox2,
        int(bool(base_image.is_horizontal)),
        int(base_image.channel_mode_int),
        int(base_image.diff_mode_int),
        int(bool(diff_source_ready)),
        20.0 / 255.0,
        0.0,
        0.0,
        0.0,
        *tile_rect1,
        *tile_rect2,
        *tuple(float(v) for v in canvas_letterbox),
        *tuple(float(v) for v in letterbox_fill),
    )
