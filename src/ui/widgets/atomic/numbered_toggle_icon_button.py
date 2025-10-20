"""
Кнопка-переключатель с иконкой лупы и числовым оверлеем.
Основана на ToggleIconButton, поверх иконки отрисовывает номер и перечеркивание когда выключена.
Важно: инвертирована семантика checked — checked=True означает "выключено" (OFF), checked=False — "включено" (ON),
чтобы OFF выглядел как selected/демпфированный.
"""
from PyQt6.QtCore import QSize, Qt, QRect
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QPushButton

from ui.widgets.atomic.toggle_icon_button import ToggleIconButton
from src.shared_toolkit.ui.managers.icon_manager import AppIcon, get_app_icon
from src.shared_toolkit.ui.managers.theme_manager import ThemeManager

class NumberedToggleIconButton(ToggleIconButton):
    """
    Квадратная кнопка-переключатель с иконкой (лупы) и динамическим числом поверх.
    Когда кнопка в состоянии OFF (checked=True) — рисуется диагональное перечеркивание и более "selected" фон (от базового ToggleIconButton).
    Номер может скрываться (None) для визуального "сжатия" номеров активных луп (например, 1 и 2 при выключенном центре).
    """
    def __init__(self, number: int, parent=None):
        super().__init__(AppIcon.MAGNIFIER, AppIcon.MAGNIFIER, parent)
        self._slot_index = int(number)
        self._display_number: int | None = None
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

        self.setIcon(get_app_icon(AppIcon.MAGNIFIER))
        self.setIconSize(QSize(18, 18))

    def set_number(self, n: int):
        """Устанавливает логический слот (1/2/3). Обычно не меняется после создания."""
        self._slot_index = int(n)
        self.update()

    def set_display_number(self, n: int | None):
        """Устанавливает отображаемый номер (1..N) или None для скрытия цифры."""
        self._display_number = n
        self.update()

    def _on_theme_changed(self):

        self.update()

    def paintEvent(self, event):

        super().paintEvent(event)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self._theme_manager.is_dark()
        text_color = QColor("#ffffff" if is_dark else "#2d2d2d")

        if self.isChecked():
            text_color.setAlpha(140)

        if self._display_number is not None:
            font = QFont()
            font.setBold(True)
            font.setPixelSize(9)
            painter.setFont(font)
            painter.setPen(text_color)

            text_rect = QRect(self.width() - 12, 1, 10, 10)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(self._display_number))

        if self.isChecked():
            strike_color = QColor("#ff4444") if is_dark else QColor("#cc0000")
            strike_color.setAlpha(180)
            pen = QPen(strike_color, 2)
            painter.setPen(pen)
            painter.drawLine(4, self.height() - 4, self.width() - 4, 4)

        painter.end()
