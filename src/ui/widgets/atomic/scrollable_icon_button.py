\
\

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton

from shared_toolkit.ui.managers.theme_manager import ThemeManager
from ui.icon_manager import AppIcon, get_app_icon

class ScrollableIconButton(QPushButton):
    """
    Квадратная кнопка с иконкой, которая поддерживает изменение значения скроллингом мыши.
    При клике также можно вызвать дополнительное действие.
    """
    valueChanged = pyqtSignal(int)

    def __init__(self, icon: AppIcon, min_value: int = 1, max_value: int = 20, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = min_value

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
        """Устанавливает текущее значение"""
        value = max(self._min_value, min(self._max_value, value))
        if self._current_value != value:
            self._current_value = value
            self.update()

    def get_value(self) -> int:
        """Возвращает текущее значение"""
        return self._current_value

    def set_range(self, min_value: int, max_value: int):
        """Устанавливает диапазон значений"""
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = max(self._min_value, min(self._max_value, self._current_value))

    def wheelEvent(self, event):
        """Обработка скроллинга мыши для изменения значения"""
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
        """Показывает всплывающую подсказку с текущим значением"""
        if self._value_popup is None:
            self._value_popup = QLabel(parent=self.window())
            self._value_popup.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)

            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)

        is_dark = self.theme_manager.is_dark()

        if is_dark:
            bg_color = "#3c3c3c"
            text_color = "#ffffff"
            border_color = "#666666"
        else:
            bg_color = "#ffffff"
            text_color = "#2d2d2d"
            border_color = "#d0d0d0"

        self._value_popup.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 6px;
                padding: 4px 6px;
                font-size: 13px;
                font-weight: 600;
                font-family: "Segoe UI", Arial, sans-serif;
            }}
        """)

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
        """Скрывает всплывающую подсказку"""
        if self._value_popup is not None:
            self._value_popup.hide()

    def paintEvent(self, event):
        """Переопределяем paintEvent для рисования иконки выше и счётчика внизу"""
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

        painter.end()

    def _update_style(self):
        """Обновляет стиль и иконку"""
        self.setIcon(get_app_icon(self._icon))
        self.setIconSize(QSize(18, 18))

        is_dark = self.theme_manager.is_dark()

        if is_dark:
            bg_normal = "#3c3c3c"
            bg_hover = "#4a4a4a"
            bg_pressed = "#353535"
        else:
            bg_normal = "#f0f0f0"
            bg_hover = "#e6e6e6"
            bg_pressed = "#dcdcdc"

        style = f"""
            QPushButton {{
                background-color: {bg_normal};
                border: none;
                border-radius: 6px;
                padding: 0px;
                padding-top: 0px;
                padding-bottom: 12px;
            }}
            QPushButton:hover {{
                background-color: {bg_hover};
            }}
            QPushButton:pressed {{
                background-color: {bg_pressed};
            }}
        """

        self.setStyleSheet(style)

