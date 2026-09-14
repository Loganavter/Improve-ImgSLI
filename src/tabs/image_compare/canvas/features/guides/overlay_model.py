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

from ui.canvas_infra.rhi.render_common import widget_px_to_screen_px

__all__ = ["GuideSpan", "resolve_guide_spans"]


@dataclass(frozen=True, slots=True)
class GuideSpan:
    """One laser guide line, fully resolved to screen space (plain data)."""

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


def resolve_guide_spans(ctx, widget, matrix) -> tuple[GuideSpan, ...]:
    """Resolve every guide line for this frame from the context (pure).

    Reads ``widget.runtime_state._guide_sets``, ``ctx`` zoom / canvas
    geometry / style only. Calling twice with an unchanged frame yields
    an equal tuple; nothing is cached, stored, or mutated.
    """
    del matrix  # matrix is packed by the pass; spans are matrix-free.
    guide_sets = tuple(getattr(widget.runtime_state, "_guide_sets", ()) or ())
    if not guide_sets:
        return ()
    line_width = float(ctx.resolved_style.annotation_line_stroke_px)
    zoom = float(ctx.zoom_level)
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
        end_x, end_y = widget_px_to_screen_px(
            widget,
            capture_center.x(),
            capture_center.y(),
            canvas_width=ctx.canvas_width,
            canvas_height=ctx.canvas_height,
            canvas_offset_x=ctx.canvas_offset_x,
            canvas_offset_y=ctx.canvas_offset_y,
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
            start_x, start_y = widget_px_to_screen_px(
                widget,
                target_center.x(),
                target_center.y(),
                canvas_width=ctx.canvas_width,
                canvas_height=ctx.canvas_height,
                canvas_offset_x=ctx.canvas_offset_x,
                canvas_offset_y=ctx.canvas_offset_y,
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
