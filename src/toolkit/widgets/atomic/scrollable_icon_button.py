

import sys
from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton

from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)
from ui.icon_manager import AppIcon, get_app_icon

class ScrollableIconButton(QPushButton):
    valueChanged = pyqtSignal(int)

    def __init__(self, icon: AppIcon, min_value: int = 1, max_value: int = 20, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = min_value
        self._current_color = None

        self.setFixedSize(36, 36)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)

        self._value_popup = None
        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.setInterval(1000)
        self._popup_timer.timeout.connect(self._hide_value_popup)

        self._update_style()

    def set_value(self, value: int):
        value = max(self._min_value, min(self._max_value, value))
        if self._current_value != value:
            self._current_value = value
            self.update()

    def get_value(self) -> int:
        return self._current_value

    def set_range(self, min_value: int, max_value: int):
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = max(self._min_value, min(self._max_value, self._current_value))

    def set_color(self, color: QColor):
        self._current_color = color
        self.update()

    def wheelEvent(self, event):
        if not self.isEnabled():
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        step = 1

        if delta > 0:

            new_value = min(self._max_value, self._current_value + step)
        else:

            new_value = max(self._min_value, self._current_value - step)

        if new_value != self._current_value:
            self._current_value = new_value
            self.valueChanged.emit(new_value)
            self._show_value_popup(new_value)
            self.update()
            event.accept()

    def _show_value_popup(self, value: int):
        if not self.isVisible():
            return
        if self._value_popup is None:
            self._value_popup = QLabel(parent=self.window())
            self._value_popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)

            if sys.platform.startswith('linux'):
                if self._value_popup.windowHandle() is not None and self.window().windowHandle() is not None:
                    self._value_popup.windowHandle().setTransientParent(self.window().windowHandle())
            self._value_popup.setObjectName("ValuePopupLabel")
            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._value_popup.setText(str(value))

        if value < 10:

            self._value_popup.setFixedSize(26, 24)
        else:

            self._value_popup.setFixedSize(32, 24)

        button_global_pos = self.mapToGlobal(QPoint(0, 0))
        popup_x = button_global_pos.x() + (self.width() - self._value_popup.width()) // 2
        popup_y = button_global_pos.y() - self._value_popup.height() - 10

        self._value_popup.move(popup_x, popup_y)
        self._value_popup.show()
        self._value_popup.raise_()

        self._popup_timer.start()

    def _hide_value_popup(self):
        if self._value_popup is not None:
            self._value_popup.hide()

    def paintEvent(self, event):
        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self.theme_manager.is_dark()
        text_color_str = "#ffffff" if is_dark else "#2d2d2d"

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(text_color_str))

        text_rect = QRect(0, 24, 36, 12)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(self._current_value))

        if self._current_color is not None:
            config = UnderlineConfig(
                thickness=2.0,
                vertical_offset=0.0,
                arc_radius=2.0,
                alpha=40,
                color=self._current_color
            )
            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)

        painter.end()

    def _update_style(self):
        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(QSize(18, 18))

