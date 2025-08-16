from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QPropertyAnimation, QEasingCurve, pyqtProperty, QEvent
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFontMetrics, QPainterPath
from PyQt6.QtWidgets import QRadioButton, QSizePolicy

from core.theme import ThemeManager

class FluentRadioButton(QRadioButton):
    INDICATOR_SIZE = 20
    OUTLINE_WIDTH = 1
    SPACING = 8
    PADDING_H = 2
    PADDING_V = 5

    INNER_HOLE_FACTOR_BASE = 0.50
    INNER_HOLE_FACTOR_HOVER = 0.60

    def __init__(self, text: str | None = None, parent=None):
        super().__init__(parent)
        if text:
            self.setText(text)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self._hover_progress = 0.0

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.theme_manager = ThemeManager.get_instance()
        try:
            self.theme_manager.theme_changed.connect(self.update)
        except Exception:
            pass

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = pyqtProperty(float, fget=get_hover_progress, fset=set_hover_progress)

    def _indicator_rect(self, full_rect: QRectF) -> QRectF:
        return QRectF(
            full_rect.x() + self.PADDING_H,
            full_rect.y() + (full_rect.height() - self.INDICATOR_SIZE) / 2,
            self.INDICATOR_SIZE,
            self.INDICATOR_SIZE,
        )

    def _text_rect_available(self, full_rect: QRectF, indicator_rect: QRectF) -> QRectF:
        text_left = indicator_rect.right() + self.SPACING
        available_w = max(0.0, full_rect.width() - (text_left - full_rect.left()) - self.PADDING_H)
        return QRectF(text_left, full_rect.y(), available_w, full_rect.height())

    def _text_rect_content(self, full_rect: QRectF, indicator_rect: QRectF, fm: QFontMetrics) -> QRectF:
        avail = self._text_rect_available(full_rect, indicator_rect)
        text = self.text() or ""
        content_w = min(avail.width(), float(fm.horizontalAdvance(text)))
        return QRectF(avail.left(), avail.top(), content_w, avail.height())

    def event(self, e):

        if e.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverMove):
            r = QRectF(self.rect())
            ind = self._indicator_rect(r)
            fm = self.fontMetrics()
            tx = self._text_rect_content(r, ind, fm)
            p = e.position()
            hovered = ind.contains(p) or tx.contains(p)
            if hovered and self._hover_progress < 1.0:
                self._animate_hover(True)
            elif (not hovered) and self._hover_progress > 0.0:
                self._animate_hover(False)
            return True
        if e.type() == QEvent.Type.HoverLeave:
            if self._hover_progress > 0.0:
                self._animate_hover(False)
            return True
        return super().event(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:

            r = QRectF(self.rect())
            ind = self._indicator_rect(r)
            fm = self.fontMetrics()
            tx = self._text_rect_content(r, ind, fm)

            if ind.contains(e.position()) or tx.contains(e.position()):

                self.setChecked(True)
                e.accept()
                return

        super().mouseReleaseEvent(e)

    def enterEvent(self, e):

        super().enterEvent(e)

    def leaveEvent(self, e):
        super().leaveEvent(e)

    def focusInEvent(self, e):
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.update()
        super().focusOutEvent(e)

    def changeEvent(self, e):
        self.update()
        super().changeEvent(e)

    def _animate_hover(self, hovered: bool):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0 if hovered else 0.0)
        self._hover_anim.start()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text()) if self.text() else 0

        extra = 4
        h = max(self.INDICATOR_SIZE + 2 * self.PADDING_V, fm.height() + 2 * self.PADDING_V)
        w = self.PADDING_H + self.INDICATOR_SIZE + (self.SPACING if text_width else 0) + text_width + self.PADDING_H + extra
        return QSize(w, h)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(self.rect())
        fm = QFontMetrics(self.font())

        indicator_rect = self._indicator_rect(rect)
        text_rect_avail = self._text_rect_available(rect, indicator_rect)
        text_rect = self._text_rect_content(rect, indicator_rect, fm)

        theme = self.theme_manager
        accent = theme.get_color("accent")
        border = theme.get_color("dialog.border")
        text_color = theme.get_color("dialog.text")
        neutral_hover = theme.get_color("dialog.button.hover")
        disabled_alpha = 110

        is_disabled = not self.isEnabled()
        is_checked = self.isChecked()

        center = indicator_rect.center()
        radius = indicator_rect.width() / 2.0

        if is_checked:
            inner_factor = self.INNER_HOLE_FACTOR_BASE + (self.INNER_HOLE_FACTOR_HOVER - self.INNER_HOLE_FACTOR_BASE) * self._hover_progress
            inner_r = radius * inner_factor

            path = QPainterPath()
            path.addEllipse(center, radius, radius)
            path.addEllipse(center, inner_r, inner_r)
            path.setFillRule(Qt.FillRule.OddEvenFill)

            fill_color = QColor(accent)
            if is_disabled:
                fill_color.setAlpha(disabled_alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawPath(path)

            border_color = border if not is_disabled else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            painter.setPen(QPen(border_color, self.OUTLINE_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)
        else:
            border_color = border if not is_disabled else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            painter.setPen(QPen(border_color, self.OUTLINE_WIDTH))
            if self._hover_progress > 0.001 and not is_disabled:
                hover_fill = QColor(neutral_hover)
                alpha = int(40 + 100 * self._hover_progress)
                hover_fill.setAlpha(max(0, min(255, alpha)))
                painter.setBrush(QBrush(hover_fill))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)

        if self.text():
            painter.setPen(QPen(QColor(text_color) if not is_disabled else QColor(text_color.red(), text_color.green(), text_color.blue(), disabled_alpha)))
            full_text = self.text()

            if fm.horizontalAdvance(full_text) > text_rect_avail.width():
                full_text = fm.elidedText(full_text, Qt.TextElideMode.ElideRight, int(text_rect_avail.width()))

                draw_rect = text_rect_avail
            else:
                draw_rect = text_rect
            painter.drawText(draw_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), full_text)

        painter.end()
