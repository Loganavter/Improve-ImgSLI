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
_MARK_FONT_PX = 10


def _colors() -> tuple[QColor, QColor]:
    from tabs.image_gallery.ui.card.dots import _accent_color, _token_color

    bg = QColor(_token_color("gallery.card.background", "#383838"))
    bg.setAlpha(210)
    return bg, QColor(_accent_color())


def accent_for(is_ai: bool) -> QColor:
    """The accent used for the AI token (kept here so both surfaces agree)."""
    _bg, accent = _colors()
    return accent


def _label_color() -> QColor:
    """Readable secondary text on the card (NOT the 120-alpha dot neutral).

    Owner 2026-10-22: the first marker used the muted dot colour and read as
    washed-out; the caption uses the same token as the stats strip text at full
    alpha, so it carries contrast in both themes.
    """
    from tabs.image_gallery.ui.card.dots import _token_color

    col = QColor(_token_color("gallery.stats.text", "#dfdfdf"))
    col.setAlpha(255)
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
    """Draw the marker as plain text at *box*'s bottom-left (no pill, no image).

    Owner 2026-10-22: the first version was a pill INSIDE the cover — it covered
    the image while the strip under the filename was empty. The marker is now a
    small caption in the card's TEXT zone (grid) / text region (list): no
    background chip, no overlap with the preview.
    """
    text = marker_text(item, translate)
    if not text:
        return
    from tabs.image_gallery.analysis.read import SOURCE_AI, analysis_source

    is_ai = analysis_source(item) == SOURCE_AI
    font = ui_font(pixel_size=_MARK_FONT_PX, bold=True)
    metrics = QFontMetrics(font)
    pad = float(scaled_px(_MARK_PAD))
    height = float(max(metrics.height(), scaled_px(11)))
    width = float(metrics.horizontalAdvance(text) + 1.0)
    if width > box.width() or height > box.height():
        return
    rect = QRectF(box.left() + pad, box.bottom() - height - pad / 2.0, width, height)
    painter.save()
    try:
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setFont(font)
        painter.setPen(accent_for(is_ai) if is_ai else _label_color())
        painter.drawText(
            rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
    finally:
        painter.restore()
