"""Immediate-overlay pilot: stateless capture-ring resolver (Engine Phase 3).

Pure decision + geometry layer for ``CaptureRingPass``. Every public
function takes the frame context first and returns frozen plain data —
no QRhi objects, no uniform buffers, no pipelines, no module-level
mutable state, no ``store`` import, no export-mode branch.
``CaptureRingPass`` (``passes.py``) keeps the retained GPU shell its
``CanvasRenderPass`` contract requires (``initialize``-owned
``FullscreenUniformPassResources``, ``prepare`` → ``resource_updates``
staging, ``record`` draw) and delegates all ring decisions here, so
live and snapshot rendering share one source of truth.

Source priority is unchanged: ``feature_overlay.capture_circles`` first,
then ``scene_frame.feature_payloads["capture_circles"]``, then
``widget.runtime_state._capture_circles``.

Retained on purpose (see ``test_overlay_stateless.py``): pipeline /
buffer ownership stays in the pass — creating them per frame would
recompile shaders every frame, and
``tests/contracts/test_pass_reads_only_ctx.py`` pins ``record()`` as
"ctx plus its own retained GPU resources".
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from engine.cache.stroke_geometry import shrink_screen_radius_for_stroke
from ui.canvas_infra.rhi.render_common import widget_px_to_screen_px

__all__ = ["CaptureRing", "resolve_capture_circles", "resolve_capture_rings"]


@dataclass(frozen=True, slots=True)
class CaptureRing:
    """One capture ring, fully resolved to screen space (plain data)."""

    center_x: float
    center_y: float
    screen_radius: float
    line_width: float
    red: float
    green: float
    blue: float
    alpha: float


def resolve_capture_circles(ctx, widget) -> tuple:
    """Resolve raw capture circles for this frame from the context (pure).

    Priority: ``feature_overlay.capture_circles`` → scene-frame payload
    ``capture_circles`` → ``widget.runtime_state._capture_circles``.
    Returns the circles untouched (no geometry applied); ``()`` when none.
    """
    overlay = getattr(ctx, "feature_overlay", None)
    circles = tuple(getattr(overlay, "capture_circles", ()) or ())
    if circles:
        return circles
    payloads = (
        ctx.scene_frame.feature_payloads
        if isinstance(getattr(ctx.scene_frame, "feature_payloads", None), dict)
        else {}
    )
    payload_circles = payloads.get("capture_circles")
    if payload_circles:
        return tuple(payload_circles)
    return tuple(getattr(widget.runtime_state, "_capture_circles", ()))


def resolve_capture_rings(ctx, widget) -> tuple[CaptureRing, ...]:
    """Resolve screen-space capture rings for this frame (pure).

    Applies zoom, pan projection, stroke-shrink, and full-opacity ring
    color. Calling twice with an unchanged frame yields an equal tuple;
    nothing is cached, stored, or mutated.
    """
    line_width = float(ctx.resolved_style.annotation_ring_stroke_px)
    zoom = float(ctx.zoom_level)
    rings: list[CaptureRing] = []
    for center, radius, color in resolve_capture_circles(ctx, widget):
        if center is None or float(radius or 0.0) <= 0.0:
            continue
        center_x, center_y = widget_px_to_screen_px(
            widget,
            center.x(),
            center.y(),
            canvas_width=ctx.canvas_width,
            canvas_height=ctx.canvas_height,
            canvas_offset_x=ctx.canvas_offset_x,
            canvas_offset_y=ctx.canvas_offset_y,
        )
        draw_color = QColor(color)
        draw_color.setAlpha(255)
        rings.append(
            CaptureRing(
                center_x=float(center_x),
                center_y=float(center_y),
                screen_radius=shrink_screen_radius_for_stroke(
                    float(radius) * zoom, line_width
                ),
                line_width=line_width,
                red=draw_color.redF(),
                green=draw_color.greenF(),
                blue=draw_color.blueF(),
                alpha=draw_color.alphaF(),
            )
        )
    return tuple(rings)
