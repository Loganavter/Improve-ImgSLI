"""Per-card provenance marker: who analyzed THIS card — the AI or the detectors.

Owner request 2026-10-22: in grid mode a small marker sits at the card's
bottom-left; list rows carry it on the thumbnail. The decision (ai/local/empty)
lives in ``analysis.read.analysis_source`` — the UI never reads raw metrics.

Both surfaces use ONE painter helper so the marker cannot drift between them.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainterPath

from sli_ui_toolkit.managers import scaled_px, ui_font

_MARK_PAD = 4.0
_MARK_FONT_PX = 9


def _colors() -> tuple[QColor, QColor]:
    from tabs.image_gallery.ui.card.dots import _accent_color, _token_color

    bg = QColor(_token_color("gallery.card.background", "#383838"))
    bg.setAlpha(210)
    return bg, QColor(_accent_color())


def _muted() -> QColor:
    from tabs.image_gallery.ui.card.dots import _neutral_color

    col = QColor(_neutral_color())
    col.setAlpha(235)
    return col


def marker_text(item, translate=None) -> str:
    """Localized short token for this item ("" when nothing analyzed it yet)."""
    from tabs.image_gallery.analysis.read import SOURCE_AI, SOURCE_LOCAL, analysis_source

    source = analysis_source(item)
    if source == SOURCE_AI:
        key, default = "image_gallery.card.source_ai", "AI"
    elif source == SOURCE_LOCAL:
        key, default = "image_gallery.card.source_local", "ALG"
    else:
        return ""
    if callable(translate):
        try:
            return str(translate(key, default))
        except Exception:
            return default
    return default


def paint_source_marker(painter, box: QRectF, item, *, translate=None) -> None:
    """Paint the marker at *box*'s bottom-left corner (no-op when unanalyzed)."""
    text = marker_text(item, translate)
    if not text:
        return
    from tabs.image_gallery.analysis.read import SOURCE_AI, analysis_source

    is_ai = analysis_source(item) == SOURCE_AI
    font = ui_font(pixel_size=_MARK_FONT_PX)
    metrics = QFontMetrics(font)
    pad = float(scaled_px(_MARK_PAD))
    height = float(max(metrics.height() + 2.0, scaled_px(12)))
    width = float(metrics.horizontalAdvance(text) + 2.0 * pad)
    if width > box.width() or height > box.height():
        return
    rect = QRectF(box.left() + pad, box.bottom() - height - pad, width, height)
    bg, accent = _colors()
    path = QPainterPath()
    radius = height / 2.0
    path.addRoundedRect(rect, radius, radius)
    painter.save()
    try:
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawPath(path)
        painter.setFont(font)
        painter.setPen(accent if is_ai else _muted())
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignCenter),
            text,
        )
    finally:
        painter.restore()
