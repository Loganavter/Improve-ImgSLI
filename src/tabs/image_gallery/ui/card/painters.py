"""Painters for gallery card — badge + dots overlay (painter pipeline only).

Audit-Meta: pattern=thin-owner-target size=exempt reason="one painters concern: badge/dots overlay recipes share one stroke-alignment contract (half-pixel inset mirrors across painters so borders stay pixel-crisp)"
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from sli_ui_toolkit.managers import ui_font


def _theme_is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True


def _resolve_badge_accent() -> object:
    """Accent for badge filled background via theme token.

    Chain (frozen seam): ``gallery.accent.bar`` → ``accent`` →
    ``#0078D4`` (light) / ``#0096FF`` (dark).
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from PySide6.QtGui import QColor

        from ui.theming import try_resolve_theme_color

        for tok in ("gallery.accent.bar", "accent"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), tok)
            if c is not None:
                return QColor(c) if isinstance(c, str) else c
    except Exception:
        pass
    from PySide6.QtGui import QColor as _QC

    if _theme_is_dark():
        return _QC("#0096FF")
    return _QC("#0078D4")


def _resolve_unfilled_bg() -> object:
    """Unfilled badge background via surface tokens with light/dark fallback.

    Chain: ``surface.background`` → ``gallery.card.background`` → light
    gray (light) / dark gray (dark). NOTE: the historical dark-only
    ``QColor(43, 43, 43)`` default is kept for the dark theme only.
    """
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from PySide6.QtGui import QColor

        from ui.theming import try_resolve_theme_color

        for tok in ("surface.background", "gallery.card.background"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), tok)
            if c is not None:
                return QColor(c) if isinstance(c, str) else c
    except Exception:
        pass
    from PySide6.QtGui import QColor as _QC

    if _theme_is_dark():
        return _QC(43, 43, 43)
    return _QC("#cecece")


def _resolve_badge_text() -> object:
    """Badge text color via theme token."""
    try:
        from sli_ui_toolkit.managers import ThemeManager
        from PySide6.QtGui import QColor

        from ui.theming import try_resolve_theme_color

        for tok in ("button.primary.text", "WindowText"):
            c = try_resolve_theme_color(ThemeManager.get_instance(), tok)
            if c is not None:
                return QColor(c) if isinstance(c, str) else c
    except Exception:
        pass
    from PySide6.QtGui import QColor as _QC

    return _QC("#ffffff")


def _left_badge_painter(painter, rect, text: str, style: tuple) -> None:  # type: ignore[no-untyped-def]
    """Draw pill badge at preview left 13 top 6 per real_design.md:2.5 and svg x52 y206."""
    try:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPen

        filled, bg, border, txt_col = style
        f = ui_font(pixel_size=13, bold=False)
        painter.save()
        try:
            from tabs.image_gallery.services.rank_badge import (
                BADGE_H_PAD,
                BADGE_HEIGHT,
                BADGE_MIN_WIDTH,
                BADGE_RADIUS,
            )

            painter.setFont(f)
            fm = painter.fontMetrics()
            w = max(BADGE_MIN_WIDTH, fm.horizontalAdvance(text) + BADGE_H_PAD)
            h = BADGE_HEIGHT
            x = rect.x() + 13
            y = rect.y() + 8 + 6
            r = QRectF(x, y, w, h)
            # background via theme tokens
            if filled:
                painter.setBrush(bg if isinstance(bg, QColor) else _resolve_badge_accent())
            else:
                painter.setBrush(_resolve_unfilled_bg())
            # border
            if border is not None:
                painter.setPen(QPen(border, 1))
            else:
                painter.setPen(QColor(0, 0, 0, 0))
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.drawRoundedRect(r, BADGE_RADIUS, BADGE_RADIUS)
            painter.setPen(txt_col if isinstance(txt_col, QColor) else _resolve_badge_text())
            painter.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)
        finally:
            painter.restore()
    except Exception:
        pass


def _dots_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """S2-1 + left badge: dots right, badge left 8 top6 per real_design.md:2.5."""
    try:
        from PySide6.QtGui import QFontMetrics

        widget = getattr(ctx, "widget", None)
        if widget is None:
            return
        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        # Left badge (rank) per real_design.md:2.5 left 8 top 6
        try:
            b_text = getattr(widget, "_gallery_badge", None)
            b_style = getattr(widget, "_gallery_badge_style", None)
            if b_text and b_style is not None:
                _left_badge_painter(painter, rect, str(b_text), b_style)
        except Exception:
            pass
        try:
            widget._gallery_dot_geometry = None  # type: ignore[attr-defined]
        except Exception:
            pass
        colors = getattr(widget, "_gallery_dot_colors", None)
        if not isinstance(colors, (list, tuple)) or not colors:
            return
        infos = getattr(widget, "_gallery_dot_infos", ()) or ()
        regions = []
        try:
            regions = list(widget.regions())
        except Exception:
            regions = []
        if len(regions) < 2:
            return
        # Region rect for id="text" (VerticalSplit weights math).
        total_weight = sum(
            max(0.0, float(getattr(r, "weight", 1.0) or 1.0)) for r in regions
        )
        if total_weight <= 0:
            return
        y = float(rect.top())
        text_region = None
        for index, region in enumerate(regions):
            if index == len(regions) - 1:
                h = float(rect.bottom()) - y + 1.0
            else:
                h = float(rect.height()) * (
                    max(0.0, float(getattr(region, "weight", 1.0) or 1.0)) / total_weight
                )
            if getattr(region, "id", "") == "text":
                text_region = (float(rect.left()), y, float(rect.width()), h)
                break
            y += h
        if text_region is None:
            return
        rows = None
        for region in regions:
            if getattr(region, "id", "") == "text":
                rows = getattr(region, "rows", None)
                break
        if not rows:
            return
        try:
            left, top, right, bottom = widget.getContentPadding()
        except Exception:
            left = top = right = bottom = 0
        rx, ry, rw, rh = text_region
        padded = QRect(
            int(rx) + int(left),
            int(ry) + int(top),
            int(rw) - int(left) - int(right),
            int(rh) - int(top) - int(bottom),
        )
        if padded.width() <= 0 or padded.height() <= 0:
            return
        # Compact rows layout: heights from line spacing, block centered.
        heights: list[int] = []
        for row in rows:
            try:
                f = ui_font(
                    pixel_size=getattr(row, "size", None),
                    bold=(getattr(row, "weight", "normal") == "bold"),
                )
                heights.append(QFontMetrics(f).lineSpacing())
            except Exception:
                heights.append(12)
        # Import here to avoid cycle; dots helper provides constants.
        from tabs.image_gallery.ui.card.dots import (
            _DOTS_ROW_GAP,
            DOT_DIAMETER,
            DOT_PITCH,
            layout_dots,
        )

        total_h = sum(heights) + _DOTS_ROW_GAP * max(0, len(heights) - 1)
        y_rows = padded.y() + max(0, (padded.height() - total_h) // 2)
        # real_design.md:2.4 — dots on same row as filename, right aligned
        # If filename row exists, draw dots at its y and right edge, not centered bottom
        if len(heights) >= 2:
            y_dots = y_rows
            h_dots = heights[0]
        else:
            y_dots = y_rows + sum(heights[:-1]) + _DOTS_ROW_GAP * (len(heights) - 1)
            h_dots = heights[-1]
        # Reference: dots r=4 diameter 8, distance 14 between centers, right
        # aligned 4px pad, centered on the filename line. ONE dot per metric
        # axis (camera 8 / fidelity 14 / batch 7). Too many dots to fit the
        # card WRAP into right-aligned rows at the full pitch — never shrink.
        y_center = y_dots + h_dots // 2
        x_right = padded.x() + padded.width() - 4 - 4  # 4px inner pad + 4 radius
        count = len(colors)
        avail = max(0.0, float(padded.width()) - 8.0)
        centers = layout_dots(count, x_right, y_center, avail)
        if len(centers) != count:
            return
        radius = DOT_DIAMETER / 2.0
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            for idx, color in enumerate(colors):
                if color is None:
                    continue
                painter.setPen(Qt.PenStyle.NoPen)
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
        # Stashed for the per-dot ToolTip filter (ui/card/dot_tooltip.py).
        # ``"centers"`` carries both axes (wrapped rows); ``"x_centers"`` is
        # kept for older readers.
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
        # Hovered blue bar 234×3 r1.5 at 8,159 inside card per svg x874 y359 (card 250×170, 8 left/right, 3 height)
        try:
            if getattr(widget, "_hover_blue_bar", False):
                try:  # B1: selection fill already signals selection — skip the bar on locked cards
                    if bool(widget.is_bg_locked()):
                        return
                except Exception:  # noqa: BLE001 - fail-open: paint bar if lock state unknown
                    pass
                from PySide6.QtCore import QRectF as _QRF2
                painter.save()
                try:
                    painter.setRenderHint(painter.RenderHint.Antialiasing, True)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(_resolve_badge_accent())
                    # 8 from left/right, 8 from bottom, 3 height, r1.5
                    bar_rect = _QRF2(rect.x() + 8, rect.y() + rect.height() - 8 - 3, 234, 3)
                    painter.drawRoundedRect(bar_rect, 1.5, 1.5)
                finally:
                    painter.restore()
        except Exception:
            pass
        # NOTE: the outer card outline is painted by toolkit BorderLayer
        # (widget scope, honors setBorderColor + borderWidth) — no app-side
        # stroke here. BackgroundLayer skips borders on region-composed
        # buttons, which is exactly why BorderLayer exists.
    except Exception:
        pass


def _gallery_hover_wash_color(tm=None):  # type: ignore[no-untyped-def]
    """Hover wash color — SAME token as the recent-projects shelf.

    Single token with per-theme hex: light ``#1a000000`` (26 alpha black),
    dark ``#26ffffff`` (38 alpha white). Regions keep a transparent
    ``hover_color`` so the stock ``BackgroundLayer`` hover stays off — this
    wash is the only hover effect.
    """
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
            try:
                dark = bool(tm.is_dark())
            except Exception:
                dark = _theme_is_dark()
        else:
            dark = _theme_is_dark()
        fallback = "#26ffffff" if dark else "#1a000000"
        if tm is not None:
            try:
                resolved = try_resolve_theme_color(tm, "recent.card.hover_wash")
                if resolved is not None:
                    return resolved if not isinstance(resolved, str) else _QC(resolved)
            except Exception:
                pass
        return _QC(fallback)
    except Exception:
        return None


def _gallery_hover_wash(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """``overlay_painter=`` callback: translucent wash over the whole card.

    Same recipe as the recent-projects shelf
    (``tabs.session_picker.recent.cards._card_hover_wash``): runs in the
    widget-scoped pass, after every region layer, so the wash sits over the
    preview pixmap and the text rows instead of being hidden behind them.
    """
    try:
        if getattr(ctx, "effective_bg_locked", False) or getattr(ctx, "hovered_region_id", None) is None:
            return
        color = _gallery_hover_wash_color(tm)
        if color is None:
            return
        radii = getattr(ctx, "corner_radii", None) or (0, 0, 0, 0)
        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        from PySide6.QtGui import QBrush as _QBrush
        from PySide6.QtGui import QPainterPath as _QPath

        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_QBrush(color))
            try:
                path = _QPath()
                path.addRoundedRect(rect, radii[0], radii[0])
                painter.drawPath(path)
            except Exception:
                painter.drawRect(rect)
        finally:
            painter.restore()
    except Exception:
        pass


def _gallery_activity_overlay(painter, ctx) -> None:  # type: ignore[no-untyped-def]
    """Activity pill over the cover's top-right (cover = card minus 8px inset)."""
    from PySide6.QtCore import QRectF

    from tabs.image_gallery.ui.card.activity_pill import paint_item_activity

    widget = getattr(ctx, "widget", None)
    rect = getattr(ctx, "rect", None)
    if widget is None or rect is None:
        return
    box = QRectF(rect.x() + 8, rect.y() + 8, rect.width() - 16, 110)
    paint_item_activity(painter, widget, box, corner="top_right")


def _gallery_card_overlay_painter(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Combined card overlay: shelf-style hover wash first, then dots/badge."""
    try:
        _gallery_hover_wash(painter, ctx, tm)
    except Exception:
        pass
    try:
        _dots_overlay_painter(painter, ctx, tm)
    except Exception:
        pass
    try:
        _gallery_activity_overlay(painter, ctx)
    except Exception:
        pass
    try:
        _gallery_rejected_dim(painter, ctx, tm)
    except Exception:
        pass


def _rejected_substrate_color(tm=None):  # type: ignore[no-untyped-def]
    """Grid substrate behind the cards (same chain as the grid host fill).

    Chain: ``gallery.grid.background`` → ``surface.background`` →
    ``#ffffff`` (light) / ``#2b2b2b`` (dark). Duplicated from
    ``grid_view._grid_substrate_color`` (importing the grid here would
    cycle: grid → card → painters).
    """
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

        return _QC2("#2b2b2b") if _theme_is_dark() else _QC2("#ffffff")
    except Exception:
        return None


# Effect-equivalent alpha: QGraphicsOpacityEffect(0.38) blends src*0.38 +
# dst*0.62; the wash over the card reaches the same mix with the substrate
# at 0.62 while the backdrop behind the card is the grid substrate.
_REJECTED_DIM_ALPHA = 0.62


def _gallery_rejected_dim(painter, ctx, tm) -> None:  # type: ignore[no-untyped-def]
    """Painter-level rejected dim (no QGraphicsOpacityEffect).

    The effect dimmed the whole subtree INCLUDING the hover capsule (a
    child of the card) — on rejected cards the capsule washed out to
    near-invisible. The overlay wash dims only the card's own paint
    (pixmap, text, dots, hover bar); children (capsule flyout, delete
    badge) stay crisp. Runs last so it covers dots/badge like the effect
    did. Clickability is untouched (no setEnabled games, no effect).
    """
    try:
        widget = getattr(ctx, "widget", None)
        if widget is None:
            return
        item = getattr(widget, "_gallery_item", None)
        if not bool(getattr(item, "rejected", False)):
            return
        rect = getattr(ctx, "rect", None)
        if rect is None:
            return
        base = _rejected_substrate_color(tm)
        if base is None:
            return
        from PySide6.QtGui import QBrush as _QBrush
        from PySide6.QtGui import QColor as _QC
        from PySide6.QtGui import QPainterPath as _QPath

        wash = _QC(base)
        try:
            wash.setAlphaF(_REJECTED_DIM_ALPHA)
        except Exception:
            return
        radii = getattr(ctx, "corner_radii", None) or (10, 10, 10, 10)
        try:
            radius = float(radii[0])
        except Exception:
            radius = 10.0
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_QBrush(wash))
            try:
                path = _QPath()
                path.addRoundedRect(rect, radius, radius)
                painter.drawPath(path)
            except Exception:
                painter.drawRect(rect)
        finally:
            painter.restore()
    except Exception:
        pass
