from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from toolkit.managers.theme_manager import ThemeManager

class FluentSwitch(QWidget):
    checkedChanged = pyqtSignal(bool)
    toggled = checkedChanged

    TRACK_WIDTH = 44
    TRACK_HEIGHT = 22
    KNOB_DIAMETER = 12
    PADDING = 2
    KNOB_MARGIN = 2

    TEXT_SPACING = 6

    TRACK_RADIUS = TRACK_HEIGHT // 2

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

        self._theme = ThemeManager.get_instance()
        self._checked: bool = False
        self._hover: float = 0.0
        self._progress: float = 0.0

        self._show_text: bool = True

        self._on_text: str = "On"
        self._off_text: str = "Off"
        self._initialize_translations()

        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._hover_anim = QPropertyAnimation(self, b"hover", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._theme.theme_changed.connect(self.update)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, v: float):
        self._progress = max(0.0, min(1.0, float(v)))
        self.update()

    progress = pyqtProperty(float, fget=get_progress, fset=set_progress)

    def get_hover(self) -> float:
        return self._hover

    def set_hover(self, v: float):
        self._hover = max(0.0, min(1.0, float(v)))
        self.update()

    hover = pyqtProperty(float, fget=get_hover, fset=set_hover)

    def isChecked(self) -> bool:  # noqa: N802 (совместимость с Qt)
        return self._checked

    def setChecked(self, checked: bool):  # noqa: N802
        checked = bool(checked)
        if self._checked == checked:
            return
        self._checked = checked
        self._animate_to_state(checked)

        if checked and self._hover > 0.01:
            self._animate_hover(False)

        self.checkedChanged.emit(checked)

    def set_state_texts(self, on_text: str, off_text: str):
        if on_text != self._on_text or off_text != self._off_text:
            self._on_text = str(on_text)
            self._off_text = str(off_text)
            self.updateGeometry()
            self.update()

    def set_show_state_text(self, show: bool):
        if bool(show) != self._show_text:
            self._show_text = bool(show)
            self.updateGeometry()
            self.update()

    def _initialize_translations(self):
        from resources.translations import tr
        self._on_text = tr("common.switch.switch_on")
        self._off_text = tr("common.switch.switch_off")

    def update_translations(self):
        from resources.translations import tr
        self.set_state_texts(tr("common.switch.switch_on"), tr("common.switch.switch_off"))

    def sizeHint(self) -> QSize:
        base_w = self.TRACK_WIDTH
        base_h = self.TRACK_HEIGHT
        if self._show_text:
            fm = QFontMetrics(self.font())
            text_w = max(fm.horizontalAdvance(self._on_text), fm.horizontalAdvance(self._off_text))
            base_w += self.TEXT_SPACING + text_w

            base_h = max(base_h, fm.height())
        return QSize(base_w, base_h)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.pos()):
            self.setChecked(not self._checked)
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def enterEvent(self, e):

        if not self._checked:
            self._animate_hover(True)
        super().enterEvent(e)

    def leaveEvent(self, e):

        if not self._checked:
            self._animate_hover(False)
        super().leaveEvent(e)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = self._theme.get_color('accent')

        track_on = accent
        track_off = QColor(0, 0, 0, 0)
        track_hover_overlay = self._theme.get_color("dialog.button.hover")
        track_hover_overlay.setAlpha(int(100 * self._hover))

        knob_on = self._theme.get_color("switch.knob.on")
        knob_off = self._theme.get_color("switch.knob.off")
        knob_border = self._theme.get_color("switch.knob.border")

        w = self.width()
        h = self.height()

        fm = QFontMetrics(self.font())
        text = self._on_text if self._checked else self._off_text
        text_w = fm.horizontalAdvance(text) if self._show_text else 0
        track_w = self.TRACK_WIDTH
        track_h = self.TRACK_HEIGHT
        track_rect = QRectF(0, (h - track_h) / 2.0, float(track_w), float(track_h))
        radius = track_rect.height() / 2.0

        track_color = self._lerp_color(track_off, track_on, self._progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        fill_rect = track_rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(fill_rect, radius - 0.5, radius - 0.5)

        if self._hover > 0.01 and not self._checked:
            painter.setBrush(QBrush(track_hover_overlay))
            painter.drawRoundedRect(fill_rect, radius - 0.5, radius - 0.5)

        if not self._checked:
            border_color = self._theme.get_color("switch.track.off.border")
            pen = QPen(border_color)
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(track_rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        knob_d = self.KNOB_DIAMETER
        x_min = self.PADDING + self.KNOB_MARGIN
        x_max = track_rect.width() - self.PADDING - self.KNOB_MARGIN - knob_d
        x = x_min + (x_max - x_min) * self._progress
        y = track_rect.top() + (track_rect.height() - knob_d) / 2.0

        knob_rect = QRectF(x, y, float(knob_d), float(knob_d))
        knob_color = self._lerp_color(knob_off, knob_on, self._progress)
        painter.setBrush(QBrush(knob_color))
        painter.setPen(QPen(knob_border, 1))
        painter.drawEllipse(knob_rect)

        if self._show_text and text_w > 0:
            text_color = self._theme.get_color('switch.text')
            painter.setPen(QPen(text_color))
            text_x = int(track_rect.right()) + self.TEXT_SPACING
            text_y = int((h + fm.ascent() - fm.descent()) / 2)
            painter.drawText(text_x, text_y, text)

    @staticmethod
    def _lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    @classmethod
    def _lerp_color(cls, c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(cls._lerp(c1.red(), c2.red(), t)),
            int(cls._lerp(c1.green(), c2.green(), t)),
            int(cls._lerp(c1.blue(), c2.blue(), t)),
            int(cls._lerp(c1.alpha(), c2.alpha(), t)),
        )

    def _animate_to_state(self, checked: bool):
        target = 1.0 if checked else 0.0
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

        if not checked and self.underMouse():
            self._animate_hover(True)

    def _animate_hover(self, on: bool):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(1.0 if on else 0.0)
        self._hover_anim.start()

