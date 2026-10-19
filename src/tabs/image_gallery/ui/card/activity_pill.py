"""Per-item activity pill — painter-pipeline only (no QSS, no stock widgets).

Shared by grid cards (``ui/card``) and list rows (``ui/list``): both call
``paint_item_activity`` from their overlay painter with the item's own box.
Spinner angle is derived from ``time.monotonic()``, so the painter stays
stateless; ``ActivityPulse`` only decides *when* to repaint.
"""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt

from sli_ui_toolkit.managers import ui_font
from tabs.image_gallery.services.activity import ACTIVE_PHASES, activity_of
from tabs.image_gallery.models import ActivityPhase

PILL_H = 20.0
_PAD = 7.0
_GAP = 5.0
_ICON_D = 10.0
_MARGIN = 6.0
_SPIN_PERIOD_S = 0.9
_SPIN_SPAN_DEG = 270.0


def _px(value: float) -> float:
    """DESIGN px → DEVICE px at the live UiScale factor (this pill is painted chrome)."""
    from sli_ui_toolkit.managers import scaled_px

    return float(scaled_px(value))

_DONE = ActivityPhase.DONE.value
_DANGER = frozenset({ActivityPhase.ERROR.value, ActivityPhase.UNREADABLE.value})
#: Phases that draw a pill on their own (``done`` only while its fade runs).
VISIBLE_PHASES: frozenset[str] = ACTIVE_PHASES | _DANGER

_FALLBACK_LABEL: dict[str, str] = {
    ActivityPhase.QUEUED.value: "Queued",
    ActivityPhase.CLAIMED.value: "Starting",
    ActivityPhase.ANALYZING.value: "Analyzing",
    ActivityPhase.WAITING.value: "Waiting",
    ActivityPhase.DONE.value: "Done",
    ActivityPhase.ERROR.value: "Error",
    ActivityPhase.UNREADABLE.value: "Unreadable",
}


def activity_label(phase: str, translate=None) -> str:
    """Localized pill label; ``translate(key, default)`` is the tab's ``_tr``."""
    fallback = _FALLBACK_LABEL.get(phase, phase)
    if translate is None:
        return fallback
    try:
        return str(translate(f"image_gallery.activity.{phase}", fallback))
    except Exception:
        return fallback


def _pill_colors(phase: str):
    from PySide6.QtGui import QColor

    from tabs.image_gallery.ui.card.dots import (
        _accent_color,
        _error_line_color,
        _is_dark,
        _severity_color,
        _token_color,
    )

    dark = _is_dark()
    bg = QColor(_token_color("gallery.card.background", "#383838" if dark else "#ffffff"))
    bg.setAlpha(228)
    fg = QColor(_token_color("gallery.stats.text", "#dfdfdf" if dark else "#2b2b2b"))
    if phase in _DANGER:
        icon = QColor(_error_line_color())
    elif phase == _DONE:
        icon = QColor(_severity_color("clean"))
    else:
        icon = QColor(_accent_color())
    return bg, fg, icon


def _draw_spinner(painter, rect: QRectF, color) -> None:
    from PySide6.QtGui import QPen

    pen = QPen(color, _px(2.0))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    start = (time.monotonic() % _SPIN_PERIOD_S) / _SPIN_PERIOD_S * 360.0
    d = _px(1.0)
    painter.drawArc(rect.adjusted(d, d, -d, -d), int(-start * 16), int(-_SPIN_SPAN_DEG * 16))


def _draw_check(painter, rect: QRectF, color) -> None:
    from PySide6.QtGui import QPainterPath, QPen

    path = QPainterPath()
    path.moveTo(rect.left() + _px(1.5), rect.center().y())
    path.lineTo(rect.left() + _px(4.0), rect.bottom() - _px(2.5))
    path.lineTo(rect.right() - _px(1.0), rect.top() + _px(2.5))
    pen = QPen(color, _px(1.8))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def _draw_dot(painter, rect: QRectF, color) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(rect)


def draw_activity_pill(
    painter, phase: str, box: QRectF, *, corner: str, label: str, alpha: float = 1.0
) -> None:
    """Paint one pill inside ``box``: ``top_right`` (grid cover) or ``middle_left`` (list thumb)."""
    from PySide6.QtGui import QFontMetrics

    font = ui_font(pixel_size=11, bold=False)
    text_w = float(QFontMetrics(font).horizontalAdvance(label))
    pad, icon_d, gap, margin, pill_h = _px(_PAD), _px(_ICON_D), _px(_GAP), _px(_MARGIN), _px(PILL_H)
    width = pad + icon_d + gap + text_w + pad
    if corner == "top_right":
        x = box.right() - margin - width
        y = box.top() + margin
    else:
        x = box.left() + margin
        y = box.center().y() - pill_h / 2.0
    pill = QRectF(x, y, width, pill_h)
    bg, fg, icon_color = _pill_colors(phase)
    icon = QRectF(pill.left() + pad, pill.center().y() - icon_d / 2.0, icon_d, icon_d)
    painter.save()
    try:
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setOpacity(max(0.0, min(1.0, float(alpha))))
        painter.setFont(font)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(pill, pill_h / 2.0, pill_h / 2.0)
        if phase in ACTIVE_PHASES:
            _draw_spinner(painter, icon, icon_color)
        elif phase == _DONE:
            _draw_check(painter, icon, icon_color)
        else:
            _draw_dot(painter, icon, icon_color)
        painter.setPen(fg)
        text_rect = QRectF(icon.right() + gap, pill.top(), text_w + 1.0, pill_h)
        painter.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), label)
    finally:
        painter.restore()


def paint_item_activity(painter, widget, box: QRectF, *, corner: str) -> None:
    """Overlay entry: derive the widget's item phase and paint its pill if any.

    ``done`` paints only while ``ActivityPulse`` drives a fade (the card's
    ``_gallery_activity_alpha`` is set); a settled done state stays silent.
    """
    item = getattr(widget, "_gallery_item", None)
    got = activity_of(item)
    if got is None:
        return
    phase = got[0]
    if phase == _DONE:
        alpha = getattr(widget, "_gallery_activity_alpha", None)
        if alpha is None:
            return
    elif phase in VISIBLE_PHASES:
        alpha = 1.0
    else:
        return
    label = activity_label(phase, getattr(widget, "_gallery_activity_tr", None))
    draw_activity_pill(painter, phase, box, corner=corner, label=label, alpha=float(alpha))
