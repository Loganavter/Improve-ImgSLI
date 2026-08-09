"""Pure zoom/pan screen-projection math, shared across tabs.

Every tab that lets the user zoom/pan a canvas needs the same answer to
"where does this widget-px point land on screen at the current zoom/pan,"
but each tab can store its own zoom/pan state differently (one zoom/pan
pair per widget, one per slot, ...).
These functions take zoom/pan as plain numbers instead of reaching into any
particular tab's state, so any tab's own accessor can call them directly
rather than re-deriving the same formula (see docs/dev/rendering/
patterns.md "Screen position from widget-px" -- a magnifier content quad
and its own border ring drifted apart on zoom/pan because the content quad
reimplemented this instead of sharing it).
"""

from __future__ import annotations


def project_px_to_screen(
    px_x: float,
    px_y: float,
    w: float,
    h: float,
    zoom: float,
    pan_x: float,
    pan_y: float,
    *,
    canvas_offset_x: float = 0.0,
    canvas_offset_y: float = 0.0,
) -> tuple[float, float]:
    """Map a logical-canvas pixel point to render-target pixel space under
    the given zoom (around the canvas center) and pan.

    ``canvas_offset_x/y`` subtracts a render-target-local origin -- used by
    tiled export, where the render target is only one tile's worth of
    pixels out of a larger logical canvas.
    """
    if w <= 0 or h <= 0:
        return px_x, px_y
    sx = ((px_x / w) - 0.5 + pan_x) * zoom + 0.5
    sy = ((px_y / h) - 0.5 + pan_y) * zoom + 0.5
    return sx * w - canvas_offset_x, sy * h - canvas_offset_y


def ndc_rect_from_screen_disk(
    center_x_px: float, center_y_px: float, radius_px: float, w: float, h: float
) -> tuple[float, float, float, float]:
    """NDC ``(x0, y0, x1, y1)`` bounding box for a disk already given in
    final render-target pixels (i.e. its center has already been projected
    through ``project_px_to_screen``/a tab's own equivalent, and
    ``radius_px`` already includes any zoom scaling the caller wants).

    Most disk-shaped overlays draw a fullscreen quad and test a signed
    distance in the fragment shader instead, needing only the projected
    center + a radius. This is for the other kind: a pass that shrinks its
    *vertex* quad to fit the disk (e.g. a texture-sampling magnifier
    content quad, avoiding overdraw outside the disk's bounds).
    """
    x0 = ((center_x_px - radius_px) / w) * 2.0 - 1.0
    x1 = ((center_x_px + radius_px) / w) * 2.0 - 1.0
    y1 = 1.0 - (((center_y_px - radius_px) / h) * 2.0)
    y0 = 1.0 - (((center_y_px + radius_px) / h) * 2.0)
    return x0, y0, x1, y1
