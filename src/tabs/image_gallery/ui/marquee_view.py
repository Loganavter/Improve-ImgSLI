"""Band visual layer for the gallery marquee (viewport-space, over cards).

Split out of ``ui/marquee.py`` per CODE_PATTERNS (thin owner + split
module): the tracker state lives in ``MarqueeState`` (toolkit), hit-testing
in ``marquee.paths_for_rect``, and everything that maps drag rects to
something paintable lives here.

Coordinate contract: the tracker stores the press origin in content coords;
a mid-drag scroll would mix bases (origin old, current live). Each end is
translated by the scroll of ITS moment — the same trick Dolphin bakes into
its rubber-band positions. With no mid-drag scroll both reduce to identity.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect


def scroll_offset(view) -> QPoint:  # type: ignore[no-untyped-def]
    """Live scroll offset in content px ((h, v) scrollbar values)."""
    try:
        area = getattr(view, "scroll_area", None)
        h = v = 0
        if area is not None:
            try:
                bar_h = area.horizontalScrollBar()
                h = int(bar_h.value()) if bar_h is not None else 0
            except Exception:
                pass
            try:
                bar_v = area.verticalScrollBar()
                v = int(bar_v.value()) if bar_v is not None else 0
            except Exception:
                pass
        return QPoint(h, v)
    except Exception:
        return QPoint(0, 0)


def band_widget(view):  # type: ignore[no-untyped-def]
    """Lazy viewport band widget (floats above host + cards)."""
    band = getattr(view, "_marquee_band", None)
    if band is None:
        try:
            from sli_ui_toolkit.widgets import MarqueeBandWidget

            viewport = view.scroll_area.viewport()
            band = MarqueeBandWidget(viewport)
            try:
                accent = getattr(view, "_selection_accent", None)
                if accent is not None:
                    band.set_accent(accent)
            except Exception:
                pass
            view._marquee_band = band  # type: ignore[attr-defined]
        except Exception:
            return None
    return band


def band_rects(view, rect: QRect) -> tuple[QRect, QRect]:  # type: ignore[no-untyped-def]
    """Scroll-compensated (viewport_rect, content_rect) for a drag rect."""
    try:
        p0 = getattr(view, "_marquee_press_pos", None)
        s0 = getattr(view, "_marquee_press_scroll", None)
        s1 = scroll_offset(view)
        if p0 is None or s0 is None:
            return QRect(rect.translated(-s1.x(), -s1.y())), QRect(rect)
        # Opposite corner of the press origin inside the normalized rect.
        cx = rect.left() + rect.right() - p0.x()
        cy = rect.top() + rect.bottom() - p0.y()
        vp0 = QPoint(p0.x() - s0.x(), p0.y() - s0.y())
        vpc = QPoint(cx - s1.x(), cy - s1.y())
        viewport_rect = QRect(vp0, vpc).normalized()
        cc = QPoint(cx, cy)
        content_rect = QRect(
            QPoint(p0.x() + s1.x() - s0.x(), p0.y() + s1.y() - s0.y()), cc
        ).normalized()
        return viewport_rect, content_rect
    except Exception:
        return QRect(rect), QRect(rect)
