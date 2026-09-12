"""Live drag/drop overlay painter for Image Compare — canvas-only RHI.

Reuses QPainter rounded-tile logic from sli-ui-toolkit's DragDropOverlay
(``sli_ui_toolkit/ui/widgets/overlays/drag_drop_overlay.py:93``): margin=10,
QRectF tiles, ThemeManager accent fill (alpha 153), white text, paint_font 20px bold.

Unlike the QWidget overlay which painted into self.rect(), the RHI pass paints
into a framebuffer-sized QImage scaled by DPR, using widget logical coordinates.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from PySide6.QtGui import QPalette

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from ui.theming import try_resolve_theme_color

try:
    from sli_ui_toolkit.managers import ThemeManager as _ThemeManager
except Exception:  # toolkit not installed editable
    _ThemeManager = None  # type: ignore


def _accent_color(host=None) -> QColor:
    # Prefer palette Highlight (already theme-resolved, no manual get_color call
    # so test_no_manual_theming allowlist is not tripped). Fallback to
    # ThemeManager token via ui.theming helper which is the single infra
    # indirection for get_color (see ui/theming.py).
    if host is not None:
        try:
            c = host.palette().color(QPalette.ColorRole.Highlight)
            if c.isValid() and c.alpha() > 0:
                return c
        except Exception:
            pass
    if _ThemeManager is not None:
        try:
            tm = _ThemeManager.get_instance()
            c = try_resolve_theme_color(tm, "accent")
            if c is not None and c.isValid():
                return c
        except Exception:
            pass
    return QColor(64, 156, 255)


def _text_and_border_colors(host=None) -> tuple[QColor, QColor]:
    if _ThemeManager is not None:
        try:
            tm = _ThemeManager.get_instance()
            cand = try_resolve_theme_color(tm, "HighlightedText")
            if cand is not None and hasattr(cand, "isValid") and cand.isValid():
                q = cand if isinstance(cand, QColor) else QColor(cand)
                lum = (q.red() * 299 + q.green() * 587 + q.blue() * 114) // 1000
                if lum > 150:
                    text = QColor(q)
                    border = QColor(q)
                    border.setAlpha(179)
                    return text, border
        except Exception:
            pass
    # Also try palette HighlightedText
    if host is not None:
        try:
            c = host.palette().color(QPalette.ColorRole.HighlightedText)
            if c.isValid() and c.alpha() > 0:
                lum = (c.red() * 299 + c.green() * 587 + c.blue() * 114) // 1000
                if lum > 150:
                    text = QColor(c)
                    border = QColor(c)
                    border.setAlpha(179)
                    return text, border
        except Exception:
            pass
    border = QColor("#ffffff")
    border.setAlpha(179)
    return QColor("#ffffff"), border


def paint_drag_drop_overlay(painter: QPainter, host, horizontal: bool, text1: str, text2: str) -> None:
    """Paint the two rounded drop-target tiles into *painter*.

    *host* is the CanvasWidget (used only for width/height via rect()).
    Caller must have setRenderHint(Antialiasing) already if desired.
    Binary show (full opacity on first frame) — the Telegram-style fade
    experiment was reverted: it never addressed the display stall.
    """
    margin = 10.0
    half_margin = margin / 2.0
    width = float(host.width()) if hasattr(host, "width") else float(painter.device().width())
    height = float(host.height()) if hasattr(host, "height") else float(painter.device().height())

    # Fallback if host is fake in tests
    if width <= 0:
        width = 800
    if height <= 0:
        height = 600

    if horizontal:
        half_height = height / 2.0
        rects = [
            QRectF(margin, margin, max(1.0, width - 2.0 * margin), max(1.0, half_height - margin - half_margin)),
            QRectF(margin, half_height + half_margin, max(1.0, width - 2.0 * margin), max(1.0, half_height - margin - half_margin)),
        ]
    else:
        half_width = width / 2.0
        rects = [
            QRectF(margin, margin, max(1.0, half_width - margin - half_margin), max(1.0, height - 2.0 * margin)),
            QRectF(half_width + half_margin, margin, max(1.0, half_width - margin - half_margin), max(1.0, height - 2.0 * margin)),
        ]

    accent = _accent_color(host)
    fill = QColor(accent)
    fill.setAlpha(153)
    text_color, border = _text_and_border_colors(host)

    font = paint_font(host if hasattr(host, "font") else None, pixel_size=20, bold=True)
    # paint_font expects a widget; if host is None or fake, fallback
    if font is None or font.pixelSize() <= 0:
        from PySide6.QtGui import QFont

        font = QFont()
        font.setPixelSize(20)
        font.setBold(True)
    painter.setFont(font)

    pen = QPen(border, 1.25)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(fill)

    for rect, text in zip(rects, (text1, text2)):
        path = QPainterPath()
        path.addRoundedRect(rect, 10.0, 10.0)
        painter.drawPath(path)
        painter.setPen(text_color)
        painter.drawText(
            rect.adjusted(15.0, 15.0, -15.0, -15.0),
            Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
            text,
        )
        painter.setPen(pen)


def should_paint_drag_overlay(widget) -> bool:
    state = getattr(widget, "runtime_state", None)
    if state is None:
        return False
    return bool(getattr(state, "_drag_overlay_visible", False))
