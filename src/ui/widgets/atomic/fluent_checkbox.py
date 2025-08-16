from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize, QPropertyAnimation, QEasingCurve, pyqtProperty, QEvent
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFontMetrics, QPainterPath
from PyQt6.QtWidgets import QCheckBox, QSizePolicy

from core.theme import ThemeManager

class FluentCheckBox(QCheckBox):
    INDICATOR_SIZE = 20
    INDICATOR_RADIUS = 4
    OUTLINE_WIDTH = 1
    SPACING = 8
    PADDING_H = 2
    PADDING_V = 5

    CHECK_ROTATION_DEG = -21.0
    CHECK_STROKE_WIDTH = 1.1
    CHECK_X1 = 0.26
    CHECK_Y1_NORM = 0.42
    CHECK_X2 = 0.36
    CHECK_Y2_PRE = 0.63
    CHECK_X3 = 0.82
    CHECK_Y3_PRE = 0.34
    CHECK_BOTTOM_FACTOR = 0.75
    CHECK_TOP_FACTOR = 0.55

    ACTIVE_EDGE_STROKE_ALPHA = 110

    def __init__(self, text: str | None = None, parent=None):
        super().__init__(parent)
        if text:
            self.setText(text)
        self.setMouseTracking(True)

        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

        self._hover_progress = 0.0
        self._checked_progress = 1.0 if self.isChecked() else 0.0

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._checked_anim = QPropertyAnimation(self, b"checkedProgress", self)
        self._checked_anim.setDuration(150)
        self._checked_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.stateChanged.connect(self._on_state_changed)

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = pyqtProperty(float, fget=get_hover_progress, fset=set_hover_progress)

    def get_checked_progress(self) -> float:
        return self._checked_progress

    def set_checked_progress(self, value: float):
        self._checked_progress = max(0.0, min(1.0, float(value)))
        self.update()

    checkedProgress = pyqtProperty(float, fget=get_checked_progress, fset=set_checked_progress)

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
                self.setChecked(not self.isChecked())
                e.accept()
                return

        super().mouseReleaseEvent(e)

    def focusInEvent(self, e):
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self.update()
        super().focusOutEvent(e)

    def changeEvent(self, e):
        self.update()
        super().changeEvent(e)

    def _on_state_changed(self, _):

        target = 1.0 if self.checkState() != Qt.CheckState.Unchecked else 0.0
        self._checked_anim.stop()
        self._checked_anim.setStartValue(self._checked_progress)
        self._checked_anim.setEndValue(target)
        self._checked_anim.start()

    def _animate_hover(self, hovered: bool):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0 if hovered else 0.0)
        self._hover_anim.start()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(self.font())
        text_width = fm.horizontalAdvance(self.text()) if self.text() else 0
        h = max(self.INDICATOR_SIZE + 2 * self.PADDING_V, fm.height() + 2 * self.PADDING_V)
        w = self.PADDING_H + self.INDICATOR_SIZE + (self.SPACING if text_width else 0) + text_width + self.PADDING_H
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

        theme = ThemeManager.get_instance()
        accent = theme.get_color("accent")
        border = theme.get_color("dialog.border")
        text_color = theme.get_color("dialog.text")
        neutral_hover = theme.get_color("dialog.button.hover")
        disabled_alpha = 110

        is_disabled = not self.isEnabled()
        is_checked = self.checkState() == Qt.CheckState.Checked
        is_indeterminate = self.checkState() == Qt.CheckState.PartiallyChecked

        if is_checked or is_indeterminate:

            border_color = border if not is_disabled else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            painter.setPen(QPen(border_color, self.OUTLINE_WIDTH))
            accent_fill = QColor(accent)

            base_alpha = int(120 + 135 * self._checked_progress)
            if is_disabled:
                base_alpha = int(base_alpha * 0.6)
            accent_fill.setAlpha(max(0, min(255, base_alpha)))
            painter.setBrush(QBrush(accent_fill))
            painter.drawRoundedRect(indicator_rect, self.INDICATOR_RADIUS, self.INDICATOR_RADIUS)
        else:

            painter.setPen(QPen(border if not is_disabled else QColor(border.red(), border.green(), border.blue(), disabled_alpha), self.OUTLINE_WIDTH))
            if self._hover_progress > 0.001 and not is_disabled:
                hover_fill = QColor(neutral_hover)
                alpha = int(40 + 100 * self._hover_progress)
                hover_fill.setAlpha(max(0, min(255, alpha)))
                painter.setBrush(QBrush(hover_fill))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(indicator_rect, self.INDICATOR_RADIUS, self.INDICATOR_RADIUS)

        if is_checked or is_indeterminate:
            glyph_color = QColor(Qt.GlobalColor.white)
            if is_disabled:
                glyph_color.setAlpha(disabled_alpha)

            if is_checked:
                painter.save()
                center = indicator_rect.center()
                painter.translate(center)
                painter.rotate(self.CHECK_ROTATION_DEG)
                painter.translate(-center)

                painter.setPen(QPen(glyph_color, self.CHECK_STROKE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))

                x1 = indicator_rect.left() + indicator_rect.width() * self.CHECK_X1
                y1 = indicator_rect.top() + indicator_rect.height() * self.CHECK_Y1_NORM
                x2 = indicator_rect.left() + indicator_rect.width() * self.CHECK_X2
                y2_pre = indicator_rect.top() + indicator_rect.height() * self.CHECK_Y2_PRE
                x3 = indicator_rect.left() + indicator_rect.width() * self.CHECK_X3
                y3_pre = indicator_rect.top() + indicator_rect.height() * self.CHECK_Y3_PRE

                cx = indicator_rect.center().y()
                y2 = cx + self.CHECK_BOTTOM_FACTOR * (y2_pre - cx)
                y3 = cx + self.CHECK_TOP_FACTOR * (y3_pre - cx)

                p1 = QPointF(x1, y1)
                p2 = QPointF(x2, y2)
                p3 = QPointF(x3, y3)
                path = QPainterPath()
                path.moveTo(p1)
                path.lineTo(p2)
                path.lineTo(p3)
                painter.drawPath(path)
                painter.restore()
            else:
                painter.setPen(QPen(glyph_color, self.CHECK_STROKE_WIDTH, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.MiterJoin))
                line_margin = indicator_rect.height() * 0.32
                y = indicator_rect.center().y()
                x1 = indicator_rect.left() + line_margin
                x2 = indicator_rect.right() - line_margin
                painter.drawLine(QPointF(x1, y), QPointF(x2, y))

        if self.text():
            painter.setPen(QPen(QColor(text_color) if not is_disabled else QColor(text_color.red(), text_color.green(), text_color.blue(), disabled_alpha)))

            elided = fm.elidedText(self.text(), Qt.TextElideMode.ElideRight, int(text_rect_avail.width()))
            painter.drawText(text_rect_avail, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)

        painter.end()
