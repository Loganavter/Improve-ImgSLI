"""List-row overlay painter — metric dots + activity pill + rejected dim.

Palette parity: no shared hover wash over the row (find-action rows wash
only the hovered chrome target via the standard variant hover). The
metric-axis dots draw in the meta region; only the dot geometry helper is
shared with the grid card (lazy import, no grid widget/layout code).
"""

from __future__ import annotations

from PySide6.QtCore import Qt


def _list_substrate_color(tm=None):  # type: ignore[no-untyped-def]
    """Grid substrate behind rows: gallery-scoped, white / dark gray."""
    try:
        from PySide6.QtGui import QColor as _QC

        from sli_ui_toolkit.managers import ThemeManager
        from ui.theming import try_resolve_theme_color

        if tm is None:
            try:
                tm = ThemeManager.get_instance()
            except Exception:
                tm = None
        if tm is not None:
            for tok in ("gallery.grid.background", "surface.background"):
                try:
                    c = try_resolve_theme_color(tm, tok)
                except Exception:
                    c = None
                if c is not None:
                    return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    try:
        from PySide6.QtGui import QColor as _QC2

        dark = bool(tm.is_dark()) if tm is not None else False
        return _QC2("#2b2b2b") if dark else _QC2("#ffffff")
    except Exception:
        return None


_REJECTED_DIM_ALPHA = 0.62


def _list_activity_overlay(painter, ctx) -> None:  # type: ignore[no-untyped-def]
    """Activity pill over the thumb (left column, vertically centered)."""
    from PySide6.QtCore import QRectF

    from tabs.image_gallery.ui.card.activity_pill import paint_item_activity
    from tabs.image_gallery.ui.list.card import LIST_THUMB_W, _list_metrics

    widget = getattr(ctx, "widget", None)
    rect = getattr(ctx, "rect", None)
    if widget is None or rect is None:
        return
    state = getattr(widget, "_gallery_row_state", None)
    design_w = float(state.get("w", LIST_THUMB_W)) if isinstance(state, dict) else float(LIST_THUMB_W)
    thumb_w, _meta_w = _list_metrics(rect, design_w)
    box = QRectF(rect.x(), rect.y(), thumb_w, rect.height())
    paint_item_activity(painter, widget, box, corner="middle_left")


def _list_metric_dots_overlay(painter, ctx) -> None:  # type: ignore[no-untyped-def]
    """Metric-axis dots right-aligned in the row's meta region.

    Same colors/values/computation as the grid card (computed in
    ``ui/list/card.py`` via the card dot helper); this painter only owns
    placement + stashing the geometry for the shared per-dot tooltip.
    """
    widget = getattr(ctx, "widget", None)
    rect = getattr(ctx, "rect", None)
    if widget is None or rect is None:
        return
    try:
        widget._gallery_dot_geometry = None  # type: ignore[attr-defined]
    except Exception:
        pass
    colors = getattr(widget, "_gallery_dot_colors", None)
    if not isinstance(colors, (list, tuple)) or not colors:
        return
    infos = getattr(widget, "_gallery_dot_infos", ()) or ()
    from tabs.image_gallery.ui.card.dots import DOT_DIAMETER, DOT_PITCH, layout_dots
    from tabs.image_gallery.ui.list.card import LIST_THUMB_W, _list_metrics

    state = getattr(widget, "_gallery_row_state", None)
    design_w = (
        float(state.get("w", LIST_THUMB_W))
        if isinstance(state, dict)
        else float(LIST_THUMB_W)
    )
    _thumb_w, meta_w = _list_metrics(rect, design_w)
    count = len(colors)
    try:
        y_center = float(rect.y()) + float(rect.height()) / 2.0
        x_right = float(rect.x()) + float(rect.width()) - 4.0 - 4.0
    except Exception:
        return
    # Same wrapping helper as the grid card: keep the full pitch and wrap into
    # right-aligned rows rather than shrinking the dots to fit the meta width.
    avail = max(0.0, float(meta_w) - 8.0)
    centers = layout_dots(count, x_right, y_center, avail)
    if len(centers) != count:
        return
    radius = DOT_DIAMETER / 2.0
    painter.save()
    try:
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        for idx, color in enumerate(colors):
            if color is None:
                continue
            painter.setBrush(color)
            cx, cy = centers[idx]
            painter.drawEllipse(
                int(cx - radius),
                int(cy - radius),
                DOT_DIAMETER,
                DOT_DIAMETER,
            )
    finally:
        painter.restore()
    try:
        widget._gallery_dot_geometry = {  # type: ignore[attr-defined]
            "centers": tuple((float(cx), float(cy)) for cx, cy in centers),
            "x_centers": tuple(float(cx) for cx, _cy in centers),
            "pitch": float(DOT_PITCH),
            "infos": tuple(infos),
            "y_center": float(y_center),
        }
    except Exception:
        pass


def _list_row_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Activity pill (thumb) + metric dots (meta) + rejected dim wash."""
    try:
        _list_activity_overlay(painter, ctx)
    except Exception:
        pass
    try:
        _list_metric_dots_overlay(painter, ctx)
    except Exception:
        pass
    try:
        widget = getattr(ctx, "widget", None)
        item = getattr(widget, "_gallery_item", None) if widget is not None else None
        if not bool(getattr(item, "rejected", False)):
            return
        base = _list_substrate_color(tm)
        if base is None:
            return
        from PySide6.QtGui import QColor as _QC

        wash = _QC(base)
        try:
            wash.setAlphaF(_REJECTED_DIM_ALPHA)
        except Exception:
            return
        _paint_capsule(painter, ctx, wash)
    except Exception:
        pass


def _paint_capsule(painter, ctx, color) -> None:  # type: ignore[no-untyped-def]
    """Fill the row rect with *color* (row is square; corners are rounded
    by the thumb/delete regions themselves)."""
    try:
        from PySide6.QtGui import QBrush as _QBrush

        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        painter.save()
        try:
            from PySide6.QtGui import QPainter

            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_QBrush(color))
            painter.drawRect(rect)
        finally:
            painter.restore()
    except Exception:
        pass
