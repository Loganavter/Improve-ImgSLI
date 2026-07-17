"""Canvas↔widget projection helpers for multi-compare hit testing."""

from __future__ import annotations

from PySide6.QtCore import QRect

from tabs.multi_compare.models import LeafNode, SplitNode
from tabs.multi_compare.ui import layout_geometry


def canvas_layout(widget) -> tuple[int, int, float, float, float] | None:
    """Return ``(canvas_w, canvas_h, sr, ox, oy)`` for projecting composition
    canvas-px to widget-px using the same letterbox formula as ``render()``.

    ``sr = min(fb_w/canvas_w, fb_h/canvas_h)``; ``ox/oy`` are letterbox
    offsets. Mirrors :func:`tabs.multi_compare.scene.projection.build_render_context`
    so hit-testing and rendering are guaranteed to agree.
    """
    if widget.state.root is None or widget.width() <= 0 or widget.height() <= 0:
        return None
    comp = widget._active_composition
    if comp is not None and comp.canvas_w > 0 and comp.canvas_h > 0:
        canvas_w = int(comp.canvas_w)
        canvas_h = int(comp.canvas_h)
    else:
        from tabs.multi_compare.services.composition_builder import (
            build_composition_plan,
        )

        plan = build_composition_plan(widget.state, include_labels=False)
        if plan is None:
            return None
        canvas_w = int(plan.canvas_w)
        canvas_h = int(plan.canvas_h)
    if canvas_w <= 0 or canvas_h <= 0:
        return None
    fb_w = float(widget.width())
    fb_h = float(widget.height())
    sr = min(fb_w / canvas_w, fb_h / canvas_h)
    ox = (fb_w - canvas_w * sr) * 0.5
    oy = (fb_h - canvas_h * sr) * 0.5
    return canvas_w, canvas_h, sr, ox, oy


def project_canvas_rect(
    rect_canvas: QRect, sr: float, ox: float, oy: float
) -> QRect:
    x = int(round(ox + rect_canvas.x() * sr))
    y = int(round(oy + rect_canvas.y() * sr))
    w = max(1, int(round(rect_canvas.width() * sr)))
    h = max(1, int(round(rect_canvas.height() * sr)))
    return QRect(x, y, w, h)


def composition_gap_canvas_px() -> int:
    from tabs.multi_compare.services.composition_builder import (
        DEFAULT_SPLIT_GAP_PX,
    )

    return int(DEFAULT_SPLIT_GAP_PX)


def drop_gaps(widget) -> list[tuple[SplitNode, tuple[int, ...], int, QRect]]:
    """Return split gaps with their tree paths for drop-zone hit-testing.

    Walks the layout in canvas-px (same gap as ``composition_builder``) and
    projects rects through the composition letterbox transform so divider
    hit-zones line up with what the renderer draws.
    """
    layout = canvas_layout(widget)
    if layout is None:
        return []
    canvas_w, canvas_h, sr, ox, oy = layout
    canvas_rect = QRect(0, 0, canvas_w, canvas_h)
    gaps_canvas = layout_geometry.drop_gaps(
        widget.state.root,
        canvas_rect,
        gap=composition_gap_canvas_px(),
    )
    return [
        (split, path, idx, project_canvas_rect(rect, sr, ox, oy))
        for (split, path, idx, rect) in gaps_canvas
    ]


def leaf_paths_and_rects(
    widget,
) -> list[tuple[LeafNode, QRect, tuple[int, ...]]]:
    layout = canvas_layout(widget)
    if layout is None:
        return []
    canvas_w, canvas_h, sr, ox, oy = layout
    canvas_rect = QRect(0, 0, canvas_w, canvas_h)
    leaves, _splits = layout_geometry.walk_paths(
        widget.state.root,
        canvas_rect,
        gap=composition_gap_canvas_px(),
    )
    return [
        (leaf, project_canvas_rect(rect, sr, ox, oy), path)
        for (leaf, rect, path) in leaves
    ]


def node_rect_at_path(widget, path: tuple[int, ...]) -> QRect | None:
    if widget.state.root is None:
        return None
    if not path:
        return widget.rect()
    layout = canvas_layout(widget)
    if layout is None:
        return None
    canvas_w, canvas_h, sr, ox, oy = layout
    canvas_rect = QRect(0, 0, canvas_w, canvas_h)
    leaves, splits = layout_geometry.walk_paths(
        widget.state.root,
        canvas_rect,
        only_path=path,
        gap=composition_gap_canvas_px(),
    )
    for _, rect, p in splits:
        if p == path:
            return project_canvas_rect(rect, sr, ox, oy)
    for _, rect, p in leaves:
        if p == path:
            return project_canvas_rect(rect, sr, ox, oy)
    return None


def leaf_rects(widget) -> list[tuple[LeafNode, QRect]]:
    """Leaf rects in widget-px, projected from the composition layout."""
    return [(leaf, rect) for (leaf, rect, _path) in leaf_paths_and_rects(widget)]
