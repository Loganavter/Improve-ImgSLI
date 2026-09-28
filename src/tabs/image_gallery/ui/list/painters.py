"""List-row overlay painter — rejected dim only (no grid imports).

Palette parity: no shared hover wash over the row (find-action rows wash
only the hovered chrome target via the standard variant hover). The only
overlay here is the rejected dim.
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


def _list_row_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Rejected dim wash (no shared hover wash — palette parity)."""
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
