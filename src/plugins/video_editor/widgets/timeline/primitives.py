from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen, QPolygonF

from .i18n import localize_token

def draw_gutter_background(widget, painter: QPainter, rect: QRectF, gutter_bg: QColor, sep_soft: QColor) -> None:
    painter.save()
    painter.fillRect(rect, gutter_bg)

    accent = QColor(widget.theme_manager.get_color("accent"))
    wash = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    top = QColor(accent)
    top.setAlpha(26 if widget.theme_manager.is_dark() else 18)
    bottom = QColor(accent)
    bottom.setAlpha(8 if widget.theme_manager.is_dark() else 4)
    wash.setColorAt(0.0, top)
    wash.setColorAt(0.35, bottom)
    wash.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(rect, wash)

    edge = QLinearGradient(rect.topLeft(), rect.topRight())
    glow = QColor(accent)
    glow.setAlpha(22 if widget.theme_manager.is_dark() else 14)
    edge.setColorAt(0.0, glow)
    edge.setColorAt(0.18, QColor(0, 0, 0, 0))
    painter.fillRect(rect, edge)
    painter.restore()

def draw_group_header_label(widget, painter: QPainter, rect: QRectF, group, label: str, text_col: QColor, sep_soft: QColor) -> None:
    painter.save()
    accent = widget._group_accent_color(group)
    collapsed = widget._is_group_collapsed(group)
    gradient = QLinearGradient(rect.topLeft(), rect.topRight())
    start = QColor(accent)
    start.setAlpha(70 if widget.theme_manager.is_dark() else 52)
    end = QColor(accent)
    end.setAlpha(12 if widget.theme_manager.is_dark() else 18)
    gradient.setColorAt(0.0, start)
    gradient.setColorAt(0.6, end)
    gradient.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(gradient))
    painter.drawRoundedRect(rect.adjusted(4, 1, -8, -1), 7, 7)

    accent_bar = QRectF(rect.left() + 4, rect.top() + 2, 3, rect.height() - 4)
    accent_fill = QColor(accent)
    accent_fill.setAlpha(210)
    painter.setBrush(accent_fill)
    painter.drawRoundedRect(accent_bar, 1.5, 1.5)

    font = painter.font()
    font.setPointSize(max(8, font.pointSize() - 1))
    font.setBold(True)
    painter.setFont(font)

    chevron_rect = widget._group_chevron_rect(rect)
    chevron_x = chevron_rect.left() + 5
    center_y = rect.center().y()
    if collapsed:
        chevron = QPolygonF([QPointF(chevron_x, center_y - 4), QPointF(chevron_x + 6, center_y), QPointF(chevron_x, center_y + 4)])
    else:
        chevron = QPolygonF([QPointF(chevron_x - 1, center_y - 3), QPointF(chevron_x + 5, center_y - 3), QPointF(chevron_x + 2, center_y + 3)])
    chevron_fill = QColor(text_col)
    chevron_fill.setAlpha(230)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(chevron_fill)
    painter.drawPolygon(chevron)

    text_rect = QRectF(rect.left() + 30, rect.top(), max(10.0, rect.width() - 42), rect.height())
    painter.setPen(QPen(text_col, 1))
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(str(label), Qt.TextElideMode.ElideRight, int(text_rect.width())),
    )
    painter.setPen(QPen(sep_soft, 1))
    painter.drawLine(int(rect.left() + 12), int(rect.bottom()), int(rect.right() - 12), int(rect.bottom()))
    painter.restore()

def draw_track_title_label(widget, painter: QPainter, rect: QRectF, label: str, text_col: QColor) -> None:
    painter.save()
    font = painter.font()
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QPen(text_col, 1))
    painter.drawText(
        rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(str(label), Qt.TextElideMode.ElideRight, int(rect.width())),
    )
    painter.restore()

def draw_channel_label(widget, painter: QPainter, rect: QRectF, label: str, text_col: QColor, dot_color: QColor) -> None:
    painter.save()
    center_y = rect.center().y()
    dot_x = rect.left() + 6
    dot = QColor(dot_color)
    dot.setAlpha(230)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(dot)
    painter.drawEllipse(QPointF(dot_x, center_y), 2.5, 2.5)

    guide_col = QColor(dot)
    guide_col.setAlpha(120)
    painter.setPen(QPen(guide_col, 1))
    painter.drawLine(int(dot_x), int(rect.top()) + 2, int(dot_x), int(rect.bottom()) - 2)

    text_rect = QRectF(rect.left() + 14, rect.top(), max(10.0, rect.width() - 14), rect.height())
    painter.setPen(QPen(text_col, 1))
    painter.drawText(
        text_rect,
        Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
        painter.fontMetrics().elidedText(localize_token(label), Qt.TextElideMode.ElideRight, int(text_rect.width())),
    )
    painter.restore()

def draw_vertical_scrollbar_track(widget, painter: QPainter, bg_color: QColor) -> None:
    if not widget._v_scrollbar.isVisible():
        return
    rect = widget._v_scrollbar.geometry().adjusted(1, 6, -1, -6)
    if rect.isEmpty():
        return
    track = QColor(bg_color)
    track.setAlpha(190 if widget.theme_manager.is_dark() else 235)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(track)
    radius = min(rect.width(), 8) / 2.0
    painter.drawRoundedRect(QRectF(rect), radius, radius)
    painter.restore()

def draw_right_gutter_background(widget, painter: QPainter, rect: QRectF, gutter_bg: QColor, sep_soft: QColor) -> None:
    if rect.isEmpty():
        return
    draw_gutter_background(widget, painter, rect, gutter_bg, sep_soft)
    painter.save()
    painter.setPen(QPen(sep_soft, 1))
    painter.drawLine(int(rect.left()), int(rect.top()), int(rect.left()), int(rect.bottom()))
    painter.restore()

def draw_playhead(widget, painter: QPainter, *, x_head: float, footer_top: int, width: int) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    extended_rect = QRectF(
        -widget.HANDLE_WIDTH,
        -widget.HANDLE_HEIGHT - 5,
        width + 2 * widget.HANDLE_WIDTH,
        widget.height() + widget.HANDLE_HEIGHT + 5,
    )
    painter.setClipRect(extended_rect, Qt.ClipOperation.ReplaceClip)

    accent_color = widget.theme_manager.get_color("accent")
    outline_color = QColor(0, 0, 0, 90)
    painter.setPen(QPen(outline_color, widget.HEAD_LINE_WIDTH + 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x_head, 0), QPointF(x_head, footer_top))
    painter.setPen(QPen(accent_color, widget.HEAD_LINE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    painter.drawLine(QPointF(x_head, 0), QPointF(x_head, footer_top))
    painter.restore()
