from PyQt6.QtCore import Qt, QRect, QPoint
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import draw_bottom_underline, UnderlineConfig
from ui.icon_manager import AppIcon, get_app_icon

class ButtonPainter:

    @staticmethod
    def paint(widget, painter: QPainter,
              icon_unchecked: AppIcon,
              icon_checked: AppIcon = None,
              is_checked: bool = False,
              is_pressed: bool = False,
              is_hovered: bool = False,
              is_scrolling: bool = False,
              badge_text: str = None,
              scroll_value: int = None,
              scroll_value_always_visible: bool = False,
              underline_color: QColor = None,
              icon_size: int = 22,
              show_strike_through: bool = False):
        """
        Рисует кнопку с учетом всех состояний и опций

        Args:
            widget: Виджет для отрисовки
            painter: QPainter для рисования
            icon_unchecked: Иконка для unchecked состояния
            icon_checked: Иконка для checked состояния (если None, используется icon_unchecked)
            is_checked: Состояние checked
            is_pressed: Состояние pressed
            is_hovered: Состояние hover
            is_scrolling: Состояние scrolling (для scroll mode)
            badge_text: Текст бейджа (цифра в углу)
            scroll_value: Значение для scroll mode (отображается при hover)
            underline_color: Цвет подчеркивания
            icon_size: Размер иконки
            show_strike_through: Показать перечеркивание (для numbered mode)
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()

        current_icon = icon_checked if (icon_checked and is_checked) else icon_unchecked

        bg_color = tm.get_color("button.toggle.background.normal")
        if is_pressed:
            bg_color = tm.get_color("button.toggle.background.pressed")
        elif is_checked:
            if is_hovered:
                bg_color = tm.get_color("button.toggle.background.checked.hover")
            else:
                bg_color = tm.get_color("button.toggle.background.checked")
        elif is_hovered:
            bg_color = tm.get_color("button.toggle.background.hover")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(widget.rect(), 6, 6)

        if current_icon:

            is_toggle_scroll = scroll_value is not None and not scroll_value_always_visible

            if is_toggle_scroll and is_hovered and not is_scrolling:

                icon_pixmap = get_app_icon(current_icon).pixmap(16, 16)
                painter.drawPixmap(int((widget.width() - 16) / 2), 2, icon_pixmap)

                ButtonPainter._draw_scroll_value(painter, widget, scroll_value, tm)
            else:

                actual_icon_size = 18 if scroll_value_always_visible else icon_size
                icon_pixmap = get_app_icon(current_icon).pixmap(actual_icon_size, actual_icon_size)

                opacity = 1.0
                if is_toggle_scroll and scroll_value == 0:
                    opacity = 0.4

                painter.setOpacity(opacity)
                x = (widget.width() - actual_icon_size) // 2
                y = (widget.height() - actual_icon_size) // 2 - 2
                painter.drawPixmap(x, y, icon_pixmap)
                painter.setOpacity(1.0)

                if scroll_value is not None and scroll_value_always_visible:
                    ButtonPainter._draw_scroll_value_always(painter, widget, scroll_value, tm)

        if badge_text is not None:
            ButtonPainter._draw_badge(painter, widget, badge_text, is_checked, tm)

        if underline_color:
            config = UnderlineConfig(
                thickness=2.0 if scroll_value is not None else 1.0,
                vertical_offset=0.0 if scroll_value is not None else 1.0,
                arc_radius=2.0,
                alpha=underline_color.alpha() if underline_color.alpha() < 255 else (40 if scroll_value is not None else 200),
                color=underline_color
            )
            draw_bottom_underline(painter, widget.rect(), tm, config)

        if show_strike_through:
            is_dark = tm.is_dark()
            strike_color = QColor("#ff4444") if is_dark else QColor("#cc0000")
            strike_color.setAlpha(180)
            pen = QPen(strike_color, 2)
            painter.setPen(pen)
            painter.drawLine(4, widget.height() - 4, widget.width() - 4, 4)

    @staticmethod
    def _draw_badge(painter: QPainter, widget, text: str, is_checked: bool, tm: ThemeManager):
        is_dark = tm.is_dark()
        text_color = QColor("#ffffff" if is_dark else "#2d2d2d")
        if is_checked:
            text_color.setAlpha(140)

        font = QFont()
        font.setBold(True)
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(text_color)

        text_rect = QRect(widget.width() - 14, 1, 12, 10)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(text))

    @staticmethod
    def _draw_scroll_value(painter: QPainter, widget, value: int, tm: ThemeManager):
        if value == 0:

            eye_pixmap = get_app_icon(AppIcon.DIVIDER_HIDDEN).pixmap(11, 11)
            center_x = widget.width() // 2
            painter.drawPixmap(center_x - 5, 28, eye_pixmap)
        else:
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(tm.get_color("dialog.text"))
            text_rect = QRect(0, 28, widget.width(), 10)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))

    @staticmethod
    def _draw_scroll_value_always(painter: QPainter, widget, value: int, tm: ThemeManager):
        is_dark = tm.is_dark()
        text_color_str = "#ffffff" if is_dark else "#2d2d2d"

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(text_color_str))

        text_rect = QRect(0, 24, widget.width(), 12)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))

