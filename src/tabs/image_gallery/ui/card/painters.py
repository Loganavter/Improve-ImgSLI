"""Painters for gallery card — badge + dots overlay (painter pipeline only)."""

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
    """Draw pill badge at preview left 8 top 6 (card 8+6=14) per real_design.md:2.5 and svg x52 y206."""
    try:
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPen

        filled, bg, border, txt_col = style
        f = ui_font(pixel_size=10, bold=True)
        painter.save()
        try:
            painter.setFont(f)
            fm = painter.fontMetrics()
            w = max(28, fm.horizontalAdvance(text) + 12)
            h = 18
            x = rect.x() + 8
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
            painter.drawRoundedRect(r, 9, 9)
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
        colors = getattr(widget, "_gallery_dot_colors", None)
        if not isinstance(colors, (list, tuple)) or len(colors) < 3:
            return
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
        # Import here to avoid cycle; dots helper provides constant.
        from tabs.image_gallery.ui.card.dots import _DOTS_ROW_GAP, _DOTS_TEXT

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
        # Reference: dots r=4 diameter 8, distance 14 between centers, right aligned 4px pad, centered on filename line
        y_center = y_dots + h_dots // 2
        x_right = padded.x() + padded.width() - 4 - 4  # 4px inner pad + 4 radius
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            # Draw up to 3 dots, right-aligned, left to right order as per colors
            for idx in range(min(3, len(colors))):
                color = colors[idx]
                if color is None:
                    continue
                # idx 0 leftmost at x_right-28, idx1 middle at x_right-14, idx2 rightmost at x_right
                x_center = x_right - (2 - idx) * 14 if len(colors) >= 3 else x_right - (len(colors) - 1 - idx) * 14
                # For fewer than 3 dots, still right-aligned: last dot at x_right
                if len(colors) < 3:
                    x_center = x_right - (len(colors) - 1 - idx) * 14
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(int(x_center - 4), int(y_center - 4), 8, 8)
        finally:
            painter.restore()
        # Hovered blue bar 234×3 r1.5 at 8,159 inside card per svg x874 y359 (card 250×170, 8 left/right, 3 height)
        try:
            if getattr(widget, "_hover_blue_bar", False):
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
    except Exception:
        pass
