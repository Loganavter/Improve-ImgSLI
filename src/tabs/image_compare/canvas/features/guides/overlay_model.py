"""Immediate-overlay pilot: stateless guide-span resolver (Engine Phase 3).

Pure decision + geometry layer for ``GuidesPass``. Every public function
takes the frame context first and returns frozen plain data — no QRhi
objects, no uniform buffers, no pipelines, no module-level mutable
state, no ``store`` import, no export-mode branch. ``GuidesPass``
(``passes.py``) keeps the retained GPU shell its ``CanvasRenderPass``
contract requires (``initialize``-owned ``FullscreenUniformPassResources``,
``prepare`` → ``resource_updates`` staging, ``record`` draw) and
delegates all span decisions here, so live and snapshot rendering share
one source of truth.

Retained on purpose (see ``test_overlay_stateless.py``): pipeline /
buffer ownership stays in the pass — creating them per frame would
recompile shaders every frame, and
``tests/contracts/test_pass_reads_only_ctx.py`` pins ``record()`` as
"ctx plus its own retained GPU resources".
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor

from engine.cache.screen_projection import project_px_to_screen

__all__ = ["GuideSpan", "resolve_guide_spans"]


@dataclass(frozen=True, slots=True)
class GuideSpan:
    """One laser guide line, fully resolved to canvas-px (plain data)."""

    start_x: float
    start_y: float
    end_x: float
    end_y: float
    start_radius: float
    end_radius: float
    line_width: float
    red: float
    green: float
    blue: float
    alpha: float


def resolve_guide_spans(ctx, widget) -> tuple[GuideSpan, ...]:
    """Resolve canvas-px guide spans for this frame from the context (pure).

    Reads ``widget.runtime_state._guide_sets``, ``ctx`` zoom / pan /
    canvas geometry / style only. Projection inputs come from ``ctx``
    (canvas dims, zoom, pan, tile offsets) via the shared engine
    projector -- the widget handle only sources the guide sets.
    Calling twice with an unchanged frame yields an equal tuple;
    nothing is cached, stored, or mutated.
    """
    guide_sets = tuple(getattr(widget.runtime_state, "_guide_sets", ()) or ())
    if not guide_sets:
        return ()
    line_width = float(ctx.resolved_style.annotation_line_stroke_px)
    zoom = float(ctx.zoom_level)
    pan_x = float(getattr(ctx, "pan_offset_x", 0.0))
    pan_y = float(getattr(ctx, "pan_offset_y", 0.0))
    canvas_w = float(ctx.canvas_width)
    canvas_h = float(ctx.canvas_height)
    offset_x = float(ctx.canvas_offset_x)
    offset_y = float(ctx.canvas_offset_y)
    spans: list[GuideSpan] = []
    for (
        capture_center,
        capture_radius,
        target_centers,
        target_radii,
        color,
    ) in guide_sets:
        if capture_center is None:
            continue
        end_x, end_y = project_px_to_screen(
            capture_center.x(),
            capture_center.y(),
            canvas_w,
            canvas_h,
            zoom,
            pan_x,
            pan_y,
            canvas_offset_x=offset_x,
            canvas_offset_y=offset_y,
        )
        end_radius = max(0.0, float(capture_radius or 0.0) * zoom)
        draw_color = QColor(color)
        targets = tuple(target_centers or ())
        radii = tuple(target_radii or ())
        for index, target_center in enumerate(targets):
            if target_center is None:
                continue
            target_radius = (
                radii[index]
                if index < len(radii)
                else (radii[-1] if radii else 0.0)
            )
            start_x, start_y = project_px_to_screen(
                target_center.x(),
                target_center.y(),
                canvas_w,
                canvas_h,
                zoom,
                pan_x,
                pan_y,
                canvas_offset_x=offset_x,
                canvas_offset_y=offset_y,
            )
            spans.append(
                GuideSpan(
                    start_x=float(start_x),
                    start_y=float(start_y),
                    end_x=float(end_x),
                    end_y=float(end_y),
                    start_radius=max(0.0, float(target_radius or 0.0) * zoom),
                    end_radius=end_radius,
                    line_width=line_width,
                    red=draw_color.redF(),
                    green=draw_color.greenF(),
                    blue=draw_color.blueF(),
                    alpha=draw_color.alphaF(),
                )
            )
    return tuple(spans)
