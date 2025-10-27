from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
)
from PyQt6.QtGui import QBrush, QColor, QCursor, QPainter, QPen
from PyQt6.QtWidgets import QSlider

from shared_toolkit.ui.managers.theme_manager import ThemeManager

class FluentSlider(QSlider):
    """
    Fluent Design slider widget with smooth animations and hover effects.

    This is a shared component that provides:
    - Smooth hover and press animations
    - Custom rendering with theme support
    - Mouse wheel support
    - Click-to-position functionality
    """
    TRACK_HEIGHT = 5
    RADIUS = 8
    MARGIN_H = 10

    def __init__(self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._hovered = False
        self._pressed = False
        self._inner_scale_current = 0.50
        self._inner_anim = QPropertyAnimation(self, b"innerScale", self)
        self._inner_anim.setDuration(140)
        self._inner_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        if self.maximum() == 99 and self.minimum() == 0:
            self.setMaximum(100)

        self.valueChanged.connect(self._update_hover_from_cursor)

    def get_inner_scale(self) -> float:
        return self._inner_scale_current

    def set_inner_scale(self, v: float):
        v = max(0.0, min(1.0, float(v)))
        if abs(v - self._inner_scale_current) > 1e-4:
            self._inner_scale_current = v
            self.update()

    innerScale = pyqtProperty(float, fget=get_inner_scale, fset=set_inner_scale)

    def _target_inner_scale(self) -> float:
        if self._pressed:
            return 0.40
        if self._hovered:
            return 0.60
        return 0.50

    def _animate_inner_to_target(self):
        target = self._target_inner_scale()
        if abs(target - self._inner_scale_current) < 1e-4:
            return
        self._inner_anim.stop()
        self._inner_anim.setStartValue(self._inner_scale_current)
        self._inner_anim.setEndValue(target)
        self._inner_anim.start()

    def sizeHint(self) -> QSize:
        base = super().sizeHint()

        fm_h = self.fontMetrics().height()
        pad = 5
        h = max(base.height(), max(2 * self.RADIUS + 2, self.TRACK_HEIGHT + 2 * pad, fm_h + pad))
        return QSize(base.width(), h)

    def minimumSizeHint(self) -> QSize:
        sh = self.sizeHint()
        return QSize(60, sh.height())

    def _groove_rect(self) -> QRectF:
        r = self.rect()
        y = r.center().y() - self.TRACK_HEIGHT / 2
        return QRectF(self.MARGIN_H, y, max(1.0, r.width() - 2 * self.MARGIN_H), self.TRACK_HEIGHT)

    def _thumb_center(self) -> QPoint:
        groove = self._groove_rect()
        span = self.maximum() - self.minimum()
        t = 0.0 if span <= 0 else (self.value() - self.minimum()) / span
        x = groove.left() + groove.width() * t
        c = QPoint(int(round(x)), int(round(groove.center().y())))
        return c

    def _is_point_in_thumb(self, p: QPoint) -> bool:
        c = self._thumb_center()
        dx = p.x() - c.x()
        dy = p.y() - c.y()
        hit_r = self.RADIUS + 4
        return (dx * dx + dy * dy) <= (hit_r * hit_r)

    def _update_hover_from_cursor(self):
        pos = self.mapFromGlobal(QCursor.pos())
        new_hovered = self._is_point_in_thumb(pos)
        if new_hovered != self._hovered:
            self._hovered = new_hovered
            self._animate_inner_to_target()
            self.update()

    def event(self, e):
        if e.type() in (QEvent.Type.HoverEnter, QEvent.Type.HoverMove):
            new_hovered = self._is_point_in_thumb(e.position().toPoint())
            if new_hovered != self._hovered:
                self._hovered = new_hovered
                self._animate_inner_to_target()
                self.update()
            return True
        if e.type() == QEvent.Type.HoverLeave:
            if self._hovered:
                self._hovered = False
                self._animate_inner_to_target()
                self.update()
            return True
        return super().event(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._is_point_in_thumb(e.pos()):
                self._pressed = True
                self._animate_inner_to_target()
                e.accept()
                self.update()
                return
            else:
                self._set_value_from_pos(e.pos().x())
                self._pressed = True
                self._animate_inner_to_target()
                e.accept()
                self.update()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._pressed:
            self._set_value_from_pos(e.pos().x())
            e.accept()
            self.update()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._pressed:
            self._pressed = False
            self._animate_inner_to_target()
            self.update()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def wheelEvent(self, e):
        delta = e.angleDelta().y()
        step = max(1, (self.maximum() - self.minimum()) // 100)
        if delta > 0:
            self.setValue(min(self.maximum(), self.value() + step))
        elif delta < 0:
            self.setValue(max(self.minimum(), self.value() - step))
        e.accept()

    def _set_value_from_pos(self, x: int):
        groove = self._groove_rect()
        if groove.width() <= 0:
            return
        t = (x - groove.left()) / groove.width()
        t = max(0.0, min(1.0, t))
        span = self.maximum() - self.minimum()
        new_val = int(round(self.minimum() + t * span))
        self.setValue(new_val)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        groove = self._groove_rect()
        rectf = groove.adjusted(0.5, 0.5, -0.5, -0.5)

        tm = self.theme_manager
        gray = QColor(tm.get_color("dialog.border"))
        base_bg = QColor(tm.get_color("slider.track.unfilled"))
        accent = QColor(tm.get_color("accent"))

        pen_border = QPen(gray, 1)
        painter.setPen(pen_border)
        painter.setBrush(QBrush(base_bg))
        painter.drawRoundedRect(rectf, self.TRACK_HEIGHT / 2, self.TRACK_HEIGHT / 2)

        span = max(1, self.maximum() - self.minimum())
        t = (self.value() - self.minimum()) / span
        if t > 0.0:
            painter.save()
            clip_rect = QRectF(rectf.left(), rectf.top(), rectf.width() * t, rectf.height())
            painter.setClipRect(clip_rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(accent))
            painter.drawRoundedRect(rectf, self.TRACK_HEIGHT / 2, self.TRACK_HEIGHT / 2)
            painter.restore()

        center = self._thumb_center()
        outer_r = self.RADIUS
        inner_scale = self._inner_scale_current

        outer_color = QColor(tm.get_color("slider.thumb.outer"))
        painter.setPen(QPen(gray, 1))
        painter.setBrush(QBrush(outer_color))
        painter.drawEllipse(center, outer_r, outer_r)

        inner_r = max(1.0, float(outer_r) * float(inner_scale))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawEllipse(QPointF(float(center.x()), float(center.y())), inner_r, inner_r)

