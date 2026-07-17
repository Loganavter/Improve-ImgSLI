"""Projection helpers for Multi Compare rendering.

This is the single source of truth for converting composition canvas
coordinates into framebuffer-space rectangles and screen-space quad vertices.
"""

from __future__ import annotations

import struct

from PySide6.QtCore import QRectF

from tabs.multi_compare.scene.context import (
    MultiCompareRenderContext,
    ProjectedLayer,
)


def build_screen_quad_vertices(rect: QRectF, fb_w: float, fb_h: float) -> bytes:
    """Return triangle-strip vertices for a framebuffer-space rect."""

    x0 = rect.left() / fb_w * 2.0 - 1.0
    x1 = rect.right() / fb_w * 2.0 - 1.0
    y0 = 1.0 - rect.top() / fb_h * 2.0
    y1 = 1.0 - rect.bottom() / fb_h * 2.0
    return struct.pack(
        "<16f",
        x0,
        y0,
        0.0,
        0.0,
        x0,
        y1,
        0.0,
        1.0,
        x1,
        y0,
        1.0,
        0.0,
        x1,
        y1,
        1.0,
        1.0,
    )


def layer_fit_scale(image, rect_w: float, rect_h: float) -> tuple[float, float]:
    """Aspect-fit scale of a layer image inside a canvas-px rect."""

    if image is None or rect_w <= 0 or rect_h <= 0:
        return 1.0, 1.0
    if hasattr(image, "shape"):
        h, w = image.shape[:2]
    else:
        w, h = image.width, image.height
    if h <= 0 or w <= 0:
        return 1.0, 1.0
    img_ar = w / h
    cell_ar = rect_w / rect_h
    if img_ar > cell_ar:
        return 1.0, cell_ar / img_ar
    return img_ar / cell_ar, 1.0


def build_render_context(
    *,
    composition,
    framebuffer_size: tuple[float, float],
    clip_matrix: tuple[float, ...],
    available_slot_ids: set[int] | frozenset[int],
    widget: object | None = None,
) -> MultiCompareRenderContext:
    """Project a resolved composition into a render context for one frame."""

    fb_w, fb_h = framebuffer_size
    scale, ox, oy = 1.0, 0.0, 0.0
    export_viewport = None
    if widget is not None:
        export_viewport = getattr(widget, "_export_canvas_viewport", None)
    layers = []
    if composition is not None and composition.layers:
        canvas_w = max(1, int(composition.canvas_w))
        canvas_h = max(1, int(composition.canvas_h))
        if export_viewport is not None:
            full_fb_w, full_fb_h, tile_left, tile_top = export_viewport
            scale = min(full_fb_w / canvas_w, full_fb_h / canvas_h)
            ox_full = (full_fb_w - canvas_w * scale) * 0.5
            oy_full = (full_fb_h - canvas_h * scale) * 0.5
            ox = ox_full - float(tile_left)
            oy = oy_full - float(tile_top)
        else:
            scale = min(fb_w / canvas_w, fb_h / canvas_h)
            ox = (fb_w - canvas_w * scale) * 0.5
            oy = (fb_h - canvas_h * scale) * 0.5
        layers = list(composition.layers)

    projected: list[ProjectedLayer] = []
    for layer in layers:
        slot_id = int(layer.layer_id)
        if slot_id not in available_slot_ids:
            continue
        lx, ly, lw, lh = layer.rect
        fit_x, fit_y = layer_fit_scale(layer.image, lw, lh)
        projected.append(
            ProjectedLayer(
                layer=layer,
                slot_id=slot_id,
                rect_fb=(
                    ox + lx * scale,
                    oy + ly * scale,
                    max(1.0, lw * scale),
                    max(1.0, lh * scale),
                ),
                fit_x=fit_x,
                fit_y=fit_y,
                zoom=float(layer.zoom),
                pan_x=float(layer.pan_x),
                pan_y=float(layer.pan_y),
            )
        )

    return MultiCompareRenderContext(
        composition=composition,
        framebuffer_size=framebuffer_size,
        scale=scale,
        offset=(ox, oy),
        clip_matrix=clip_matrix,
        projected_layers=tuple(projected),
        widget=widget,
    )
