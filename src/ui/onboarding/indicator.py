from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, pyqtProperty
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager


class DotIndicator(QWidget):
    def __init__(self, count=3, parent=None):
        super().__init__(parent)
        self._count = count
        self._current = 0
        self._animated_position = 0.0
        self._previous_position = 0.0
        self.setMinimumSize(60, 15)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.theme_manager = ThemeManager.get_instance()

        self._animation = QPropertyAnimation(self, b"animatedPosition")
        self._animation.setDuration(150)
        self._animation.setEasingCurve(QEasingCurve.Type.OutQuad)

    def get_animated_position(self):
        return self._animated_position

    def set_animated_position(self, value):
        self._previous_position = self._animated_position
        self._animated_position = value
        self.update()

    animatedPosition = pyqtProperty(float, get_animated_position, set_animated_position)

    def set_current(self, index):
        old_pos = self._current
        self._current = index

        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
            old_pos = self._animated_position

        self._animation.setStartValue(float(old_pos))
        self._animation.setEndValue(float(index))
        self._animation.start()

    def sizeHint(self):
        if self.parent():
            width = min(200, self.parent().width() // 3)
            height = 20
        else:
            width = 100
            height = 20
        return QSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        accent = self.theme_manager.get_color("accent")
        inactive = self.theme_manager.get_color("dialog.text")
        inactive.setAlpha(60)

        dot_size = max(6, min(10, self.width() // 15))
        spacing = max(10, min(16, self.width() // 10))
        total_width = (self._count * dot_size) + ((self._count - 1) * spacing)
        start_x = (self.width() - total_width) // 2
        y = (self.height() - dot_size) // 2

        animated_x = start_x + self._animated_position * (dot_size + spacing)
        step = dot_size + spacing

        for i in range(self._count):
            x = start_x + i * (dot_size + spacing)
            painter.setBrush(inactive)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(x), int(y), dot_size, dot_size)

        if (
            abs(self._animated_position - self._previous_position) > 0.01
            and self._animation.state() == QPropertyAnimation.State.Running
        ):
            animation_progress = (
                self._animation.currentTime() / self._animation.duration()
                if self._animation.duration() > 0
                else 1.0
            )
            direction = -1 if self._animated_position > self._previous_position else 1

            trail_steps = 3
            for i in range(trail_steps):
                trail_offset = (i + 1) * step * 0.17
                trail_x = animated_x + trail_offset * direction

                if (
                    trail_x < start_x - step
                    or trail_x > start_x + (self._count - 1) * step + step
                ):
                    continue

                base_alpha = 120 * (1.0 - (i + 1) / (trail_steps + 1))
                fade_alpha = base_alpha * (1.0 - animation_progress)
                alpha = int(fade_alpha)

                if alpha <= 0:
                    continue

                trail_size = max(4, dot_size - i * 1.2)
                trail_color = QColor(accent)
                trail_color.setAlpha(alpha)

                painter.setBrush(trail_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(
                    int(trail_x) - 1,
                    int(y) - 1,
                    int(trail_size) + 2,
                    int(trail_size) + 2,
                )

        painter.setBrush(accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(animated_x) - 1, int(y) - 1, dot_size + 2, dot_size + 2)
