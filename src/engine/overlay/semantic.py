"""Scale-free semantic overlay structs + shell-side pack functions (F1 shell-packs).

Resolvers return scale-free geometry in canvas-px (the unified canvas-px
promise: callers never think about zoom, pan, or framebuffer size); the
pack functions below apply the canvas-px -> framebuffer-px scale and emit
the byte-identical uniform blocks the v1 byte-packing resolvers produce.
Scale application lives here, shell-side -- resolvers never scale.

Ownership split with the v1 resolvers (which stay alive through the
F-b..F-c coexistence window):

* geometry decisions (what is visible, gating, clipping to content, arc
  validity such as radius/span gates) stay resolver-side;
* byte layout (struct formats, field order, NDC conversion) lives here.

Per-family item conventions (each pack takes the opaque frame ``ctx``
nowhere -- matrix and framebuffer size arrive precomputed, matching the
shell rule that per-frame values arrive ready to pack):

* ``pack_divider``: ``(bar: RectItem, clip: RectItem)``. ``bar`` is the
  divider bar rect in canvas-px; orientation derives from its aspect
  (``h < w`` reads as a horizontal bar, else vertical), position from its
  center on the minor axis, thickness from the minor extent, color from
  ``bar.color``. ``clip`` is the content clip rect (its color is ignored);
  when absent the clip defaults to the full ``(0, 0, fb_w, fb_h)`` frame.
* ``pack_guides``: one ``DiskItem`` per guide span --
  ``(cx, cy)`` is the span start, ``radius`` the start radius, ``color``
  the line color, ``line_width_key`` the style knob that owns the width
  (``"annotation_line_stroke_px"``), and
  ``extra == (end_x, end_y, end_radius, line_width_px)``.
* ``pack_capture``: one ``DiskItem`` per capture ring --
  ``(cx, cy)`` is the ring center, ``radius`` the stroke-corrected screen
  radius, ``line_width_key == "annotation_ring_stroke_px"``, and
  ``extra == (line_width_px,)``.
* ``pack_grid_dividers``: one ``RectItem`` per divider, already in
  framebuffer px (projection stays resolver-side, mirroring the scene
  seam that feeds it); each rect re-encodes to NDC bounds
  ``(x0, y0, x1, y1)`` via ``x0 = 2x/fb_w - 1``,
  ``y_top = 1 - 2y/fb_h``. Rects with non-positive extent are skipped and
  a non-positive framebuffer yields no blocks, matching the pass resolve
  this replaces. No ``canvas_scale`` here: the rects arrive projected.
* ``pack_arcs``: one ``DiskItem`` per arc/ring --
  ``(cx, cy)`` is the arc center, ``radius`` the stroke-corrected radius,
  ``line_width_key`` the style knob (``"annotation_arc_stroke_px"`` for
  occluded arcs, ``"annotation_selection_stroke_px"`` for selection
  rings), ``color`` the final ring color, and
  ``extra == (start_deg, span_deg, active, capture, line_width_px)`` where
  ``active``/``capture`` route the ring family for future resolvers.

``TextItem`` has no pack function in this wave: text intake rides the
raster path, so the struct exists only to complete the
``SemanticOverlayItems`` union for resolver authors.

Engine types only: this module names no caller-side geometry and imports
stdlib plus engine modules only.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from engine.cache.uniform_layout import assert_uniform_size

from .shell import FULLSCREEN_VERTICES

__all__ = [
    "Rgba",
    "RectItem",
    "DiskItem",
    "TextItem",
    "SemanticOverlayItems",
    "SemanticResolver",
    "DIVIDER_UNIFORM_FMT",
    "DIVIDER_UNIFORM_SIZE",
    "GUIDES_UNIFORM_FMT",
    "GUIDES_UNIFORM_SIZE",
    "CAPTURE_UNIFORM_FMT",
    "CAPTURE_UNIFORM_SIZE",
    "GRID_DIVIDER_UNIFORM_FMT",
    "GRID_DIVIDER_UNIFORM_SIZE",
    "ARC_UNIFORM_FMT",
    "ARC_UNIFORM_SIZE",
    "pack_divider",
    "pack_guides",
    "pack_capture",
    "pack_grid_dividers",
    "pack_arcs",
]

#: Shared-quad vertex bytes the packed blocks render through (import ties
#: pack output to the shell pipeline shape: TriangleStrip, SrcAlpha blend,
#: 2xFloat2 layout -- owned by ``shell.py``, referenced here, never copied).
_QUAD_VERTEX_BYTES = len(FULLSCREEN_VERTICES)

#: std140: mat4(64) + vec2 fb size(8) + position/half-thickness(8) +
#: vec4 color(16) + vec4 clip(16) + int flag(4) + pad(12) = 128.
DIVIDER_UNIFORM_FMT = "<24f4fi3f"
DIVIDER_UNIFORM_SIZE = 128
assert_uniform_size(DIVIDER_UNIFORM_FMT, DIVIDER_UNIFORM_SIZE, label="pack_divider")

#: mat4(64) + vec2 fb size(8) + span endpoints(16) + radii/width/pad(24) +
#: vec4 color(16) = 128.
GUIDES_UNIFORM_FMT = "<32f"
GUIDES_UNIFORM_SIZE = 128
assert_uniform_size(GUIDES_UNIFORM_FMT, GUIDES_UNIFORM_SIZE, label="pack_guides")

#: mat4(64) + vec2 fb size(8) + center/radius/width/pad(24) +
#: vec4 color(16) = 112.
CAPTURE_UNIFORM_FMT = "<28f"
CAPTURE_UNIFORM_SIZE = 112
assert_uniform_size(CAPTURE_UNIFORM_FMT, CAPTURE_UNIFORM_SIZE, label="pack_capture")

#: mat4 mvp(64) + vec4 NDC bounds(16) + vec4 color(16) = 96.
GRID_DIVIDER_UNIFORM_FMT = "<24f"
GRID_DIVIDER_UNIFORM_SIZE = 96
assert_uniform_size(
    GRID_DIVIDER_UNIFORM_FMT, GRID_DIVIDER_UNIFORM_SIZE, label="pack_grid_dividers"
)

#: mat4(64) + vec2 fb size(8) + center(8) + radius/width/start/span(16) +
#: vec4 color(16) = 112. Same shape as the arc pass uniform packing.
ARC_UNIFORM_FMT = "<16f2f2f4f4f"
ARC_UNIFORM_SIZE = 112
assert_uniform_size(ARC_UNIFORM_FMT, ARC_UNIFORM_SIZE, label="pack_arcs")


@dataclass(frozen=True, slots=True)
class Rgba:
    """Linear float color channel set (engine type, never a host color)."""

    r: float
    g: float
    b: float
    a: float


@dataclass(frozen=True, slots=True)
class RectItem:
    """Axis-aligned rect in canvas-px plus its fill color."""

    x: float
    y: float
    w: float
    h: float
    color: Rgba


@dataclass(frozen=True, slots=True)
class DiskItem:
    """Center + radius in canvas-px plus stroke routing.

    ``line_width_key`` names the style knob that owns the stroke width;
    the resolved px width rides in ``extra`` (per-family arity, see the
    module docstring) so packs stay ctx-free.
    """

    cx: float
    cy: float
    radius: float
    line_width_key: str
    color: Rgba
    extra: tuple


@dataclass(frozen=True, slots=True)
class TextItem:
    """Labeled rect for future text intake (no pack function this wave)."""

    rect: RectItem
    text: str
    style: tuple


SemanticOverlayItems = tuple["RectItem | DiskItem | TextItem", ...]


@runtime_checkable
class SemanticResolver(Protocol):
    """Scale-free geometry resolver: ctx in, semantic items out."""

    def __call__(self, ctx: Any) -> SemanticOverlayItems:
        """Resolve this frame's overlay items from the opaque context."""
        ...


def _scale(value: float, canvas_scale: float) -> float:
    """Canvas-px -> framebuffer-px for one scalar.

    Pure ratio applied shell-side only. Tile-side precedent for the same
    ownership principle (scale applied by the engine, never by callers) is
    ``engine.cache.draw_plans.content_scale_for``; the ratio here differs
    (canvas scale, not array-layer content scale) so the one-line formula
    is stated locally instead of reused.
    """
    return float(value) * float(canvas_scale)


def _matrix_tuple(clip_matrix: Any) -> tuple[float, ...]:
    values = tuple(float(v) for v in clip_matrix)
    if len(values) != 16:
        raise ValueError(
            f"clip_matrix must hold 16 floats, got {len(values)}"
        )
    return values


def pack_divider(
    items: SemanticOverlayItems,
    clip_matrix: Any,
    fb_w: float,
    fb_h: float,
    *,
    canvas_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """Pack one 128B divider block from ``(bar, clip)`` rect items."""
    if not items:
        return ()
    bar = items[0]
    if not isinstance(bar, RectItem):
        raise TypeError(
            f"pack_divider takes (bar: RectItem, clip: RectItem), got {type(bar).__name__}"
        )
    if len(items) > 1:
        clip = items[1]
        if not isinstance(clip, RectItem):
            raise TypeError(
                "pack_divider takes (bar: RectItem, clip: RectItem), "
                f"got clip {type(clip).__name__}"
            )
        clip_rect = (
            _scale(clip.x, canvas_scale),
            _scale(clip.y, canvas_scale),
            _scale(clip.w, canvas_scale),
            _scale(clip.h, canvas_scale),
        )
    else:
        clip_rect = (0.0, 0.0, float(fb_w), float(fb_h))
    bw = _scale(bar.w, canvas_scale)
    bh = _scale(bar.h, canvas_scale)
    horizontal = bh < bw
    if horizontal:
        position = _scale(bar.y, canvas_scale) + bh * 0.5
        thickness = bh
    else:
        position = _scale(bar.x, canvas_scale) + bw * 0.5
        thickness = bw
    color = bar.color
    return (
        struct.pack(
            DIVIDER_UNIFORM_FMT,
            *_matrix_tuple(clip_matrix),
            float(fb_w),
            float(fb_h),
            position,
            thickness * 0.5,
            color.r,
            color.g,
            color.b,
            color.a,
            *clip_rect,
            int(horizontal),
            0.0,
            0.0,
            0.0,
        ),
    )


def pack_guides(
    items: SemanticOverlayItems,
    clip_matrix: Any,
    fb_w: float,
    fb_h: float,
    *,
    canvas_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """Pack one 128B guide block per span disk item."""
    matrix = _matrix_tuple(clip_matrix)
    blocks: list[bytes] = []
    for item in items:
        if not isinstance(item, DiskItem):
            raise TypeError(
                f"pack_guides takes DiskItem spans, got {type(item).__name__}"
            )
        extra = tuple(item.extra)
        if len(extra) != 4:
            raise ValueError(
                "guide DiskItem.extra must be "
                "(end_x, end_y, end_radius, line_width_px), "
                f"got {len(extra)} values"
            )
        end_x, end_y, end_radius, line_width = (float(v) for v in extra)
        blocks.append(
            struct.pack(
                GUIDES_UNIFORM_FMT,
                *matrix,
                float(fb_w),
                float(fb_h),
                _scale(item.cx, canvas_scale),
                _scale(item.cy, canvas_scale),
                _scale(end_x, canvas_scale),
                _scale(end_y, canvas_scale),
                _scale(item.radius, canvas_scale),
                _scale(end_radius, canvas_scale),
                _scale(line_width, canvas_scale),
                0.0,
                0.0,
                0.0,
                item.color.r,
                item.color.g,
                item.color.b,
                item.color.a,
            )
        )
    return tuple(blocks)


def pack_capture(
    items: SemanticOverlayItems,
    clip_matrix: Any,
    fb_w: float,
    fb_h: float,
    *,
    canvas_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """Pack one 112B capture-ring block per ring disk item."""
    matrix = _matrix_tuple(clip_matrix)
    blocks: list[bytes] = []
    for item in items:
        if not isinstance(item, DiskItem):
            raise TypeError(
                f"pack_capture takes DiskItem rings, got {type(item).__name__}"
            )
        extra = tuple(item.extra)
        if len(extra) != 1:
            raise ValueError(
                "capture DiskItem.extra must be (line_width_px,), "
                f"got {len(extra)} values"
            )
        (line_width,) = (float(v) for v in extra)
        blocks.append(
            struct.pack(
                CAPTURE_UNIFORM_FMT,
                *matrix,
                float(fb_w),
                float(fb_h),
                _scale(item.cx, canvas_scale),
                _scale(item.cy, canvas_scale),
                _scale(item.radius, canvas_scale),
                _scale(line_width, canvas_scale),
                0.0,
                0.0,
                item.color.r,
                item.color.g,
                item.color.b,
                item.color.a,
            )
        )
    return tuple(blocks)


def _fb_rect_to_ndc_bounds(
    x: float, y: float, w: float, h: float, fb_w: float, fb_h: float
) -> tuple[float, float, float, float]:
    """Framebuffer-px rect (origin top-left) -> NDC bounds (x0, y0, x1, y1).

    Same formula the grid-dividers pass resolve uses: ``x0 = 2x/fb_w - 1``,
    ``y_top = 1 - 2y/fb_h``. Y flips so +y is up in clip space. Stated
    here so the shell owns the conversion; resolvers hand over fb rects.
    """
    x0 = (2.0 * x / fb_w) - 1.0
    x1 = (2.0 * (x + w) / fb_w) - 1.0
    y_top = 1.0 - (2.0 * y / fb_h)
    y_bottom = 1.0 - (2.0 * (y + h) / fb_h)
    return (x0, y_bottom, x1, y_top)


def pack_grid_dividers(
    items: SemanticOverlayItems,
    clip_matrix: Any,
    fb_w: float,
    fb_h: float,
) -> tuple[bytes, ...]:
    """Pack one 96B grid-divider block per fb-px rect item.

    Rects arrive projected (projection stays resolver-side); only the
    fb-rect -> NDC-bounds conversion lives here. No ``canvas_scale``: the
    items are already framebuffer px.
    """
    fb_w = float(fb_w)
    fb_h = float(fb_h)
    if fb_w <= 0.0 or fb_h <= 0.0:
        return ()
    matrix = _matrix_tuple(clip_matrix)
    blocks: list[bytes] = []
    for item in items:
        if not isinstance(item, RectItem):
            raise TypeError(
                f"pack_grid_dividers takes RectItem fb rects, got {type(item).__name__}"
            )
        if item.w <= 0.0 or item.h <= 0.0:
            continue
        x0, y0, x1, y1 = _fb_rect_to_ndc_bounds(
            float(item.x), float(item.y), float(item.w), float(item.h), fb_w, fb_h
        )
        blocks.append(
            struct.pack(
                GRID_DIVIDER_UNIFORM_FMT,
                *matrix,
                x0,
                y0,
                x1,
                y1,
                item.color.r,
                item.color.g,
                item.color.b,
                item.color.a,
            )
        )
    return tuple(blocks)


def pack_arcs(
    items: SemanticOverlayItems,
    clip_matrix: Any,
    fb_w: float,
    fb_h: float,
    *,
    canvas_scale: float = 1.0,
) -> tuple[bytes, ...]:
    """Pack one 112B arc block per arc disk item (arc uniform shape)."""
    matrix = _matrix_tuple(clip_matrix)
    blocks: list[bytes] = []
    for item in items:
        if not isinstance(item, DiskItem):
            raise TypeError(
                f"pack_arcs takes DiskItem arcs, got {type(item).__name__}"
            )
        extra = tuple(item.extra)
        if len(extra) != 5:
            raise ValueError(
                "arc DiskItem.extra must be "
                "(start_deg, span_deg, active, capture, line_width_px), "
                f"got {len(extra)} values"
            )
        start_deg, span_deg, _active, _capture, line_width = extra
        blocks.append(
            struct.pack(
                ARC_UNIFORM_FMT,
                *matrix,
                float(fb_w),
                float(fb_h),
                _scale(item.cx, canvas_scale),
                _scale(item.cy, canvas_scale),
                _scale(item.radius, canvas_scale),
                _scale(float(line_width), canvas_scale),
                float(start_deg),
                float(span_deg),
                item.color.r,
                item.color.g,
                item.color.b,
                item.color.a,
            )
        )
    return tuple(blocks)
