"""
Контейнер для группы кнопок с подписью, врезанной в нижнюю линию
"""
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from shared_toolkit.ui.managers.theme_manager import ThemeManager

class ButtonGroupContainer(QWidget):
    """
    Контейнер для группы кнопок с границей и подписью, врезанной в нижнюю линию.
    """

    def __init__(self, buttons: list, label_text: str = "", parent=None):
        super().__init__(parent)
        self._label_text = label_text
        self._border_width = 1
        self._border_radius = 8

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        self._buttons_layout = QHBoxLayout(self)
        self._buttons_layout.setContentsMargins(10, 8, 10, 18)
        self._buttons_layout.setSpacing(2)

        for btn in buttons:
            self._buttons_layout.addWidget(btn)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def set_label_text(self, text: str):
        """Устанавливает текст подписи"""
        if self._label_text != text:
            self._label_text = text
            self.update()

    def _get_label_height(self):
        """Возвращает высоту текста подписи"""
        if not self._label_text:
            return 0
        font_metrics = QFontMetrics(self.font())
        return font_metrics.height()

    def _get_label_width(self):
        """Возвращает ширину текста подписи"""
        if not self._label_text:
            return 0
        font_metrics = QFontMetrics(self.font())
        return font_metrics.horizontalAdvance(self._label_text)

    def paintEvent(self, event):
        """Рисует границу с врезанной подписью"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self.theme_manager.is_dark()
        if is_dark:
            border_color = self.theme_manager.get_color("dialog.border")
            bg_color = self.theme_manager.get_color("Window")
            text_color = self.theme_manager.get_color("WindowText")
        else:
            border_color = self.theme_manager.get_color("dialog.border")
            bg_color = self.theme_manager.get_color("Window")
            text_color = self.theme_manager.get_color("WindowText")

        rect = self.rect()
        label_height = self._get_label_height()
        label_width = self._get_label_width()

        pen = QPen(border_color, self._border_width)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.translate(0.5, 0.5)

        margin_v = 3
        margin_h = 6
        bottom_y = rect.height() - label_height // 2
        draw_rect = QRect(margin_h, margin_v, rect.width() - margin_h * 2 - 1, bottom_y - margin_v * 2)
        painter.drawRoundedRect(draw_rect, self._border_radius, self._border_radius)

        painter.translate(-0.5, -0.5)

        if self._label_text:
            label_padding = 3
            center_x = rect.width() // 2

            font = painter.font()
            font.setPointSize(max(8, font.pointSize() - 2))
            painter.setFont(font)

            font_metrics = QFontMetrics(font)
            actual_label_width = font_metrics.horizontalAdvance(self._label_text)
            actual_label_height = font_metrics.height()

            actual_bottom_y = bottom_y - margin_v
            gap_y = actual_bottom_y - self._border_width
            gap_height = self._border_width * 2 + 1

            painter.setPen(Qt.PenStyle.NoPen)
            gap_rect = QRect(
                center_x - actual_label_width // 2 - label_padding,
                gap_y,
                actual_label_width + label_padding * 2,
                gap_height
            )
            painter.fillRect(gap_rect, bg_color)

            text_rect = QRect(
                center_x - actual_label_width // 2,
                rect.height() - actual_label_height - 2,
                actual_label_width,
                actual_label_height
            )
            painter.setPen(text_color)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self._label_text)

