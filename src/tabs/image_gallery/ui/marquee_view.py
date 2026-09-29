"""Band visual layer for the gallery marquee (viewport-space, over cards).

Thin consumer shell per CODE_PATTERNS: the mechanism (tracker, paint,
scroll compensation) is canonical in ``sli_ui_toolkit``; this module only
owns the gallery-specific wiring — band widget parent (the scroll
viewport), accent source, and press-time scroll/pos bookkeeping fields.
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
    """Scroll-compensated (viewport_rect, content_rect); toolkit math."""
    try:
        from sli_ui_toolkit.widgets import resolve_band_rects

        return resolve_band_rects(
            getattr(view, "_marquee_press_pos", None),
            getattr(view, "_marquee_press_scroll", None),
            rect,
            scroll_offset(view),
        )
    except Exception:
        return QRect(rect), QRect(rect)
