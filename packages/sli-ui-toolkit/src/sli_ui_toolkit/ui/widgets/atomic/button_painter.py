from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

class ButtonPainter:
    @staticmethod
    def paint(
        widget,
        painter: QPainter,
        icon_unchecked,
        icon_checked=None,
        is_checked: bool = False,
        is_pressed: bool = False,
        is_hovered: bool = False,
        is_scrolling: bool = False,
        badge_text: str = None,
        scroll_value: int = None,
        scroll_value_always_visible: bool = False,
        underline_color: QColor = None,
        icon_size: int = 22,
        show_strike_through: bool = False,
    ):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()
        style = read_widget_style(widget, default_icon_size=icon_size)

        current_icon = icon_checked if (icon_checked and is_checked) else icon_unchecked

        bg_color = style.background_color or tm.get_color("button.toggle.background.normal")
        if style.variant == "primary" and style.accent_color is not None:
            bg_color = style.accent_color
        elif style.variant == "ghost":
            bg_color = QColor(0, 0, 0, 0)
        elif style.variant == "subtle" and style.background_color is None:
            bg_color = tm.get_color("Window")
        if is_pressed:
            bg_color = tm.get_color("button.toggle.background.pressed")
        elif is_checked:
            bg_color = (
                tm.get_color("button.toggle.background.checked.hover")
                if is_hovered
                else tm.get_color("button.toggle.background.checked")
            )
        elif is_hovered:
            bg_color = tm.get_color("button.toggle.background.hover")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        radius = max(0, int(style.corner_radius_px or 6))
        painter.drawRoundedRect(widget.rect(), radius, radius)

        if current_icon:
            is_toggle_scroll = (
                scroll_value is not None and not scroll_value_always_visible
            )

            if is_toggle_scroll and is_hovered and not is_scrolling:
                hover_icon_size = max(12, int(style.icon_size_px or icon_size) - 6)
                icon_pixmap = resolve_icon(current_icon).pixmap(hover_icon_size, hover_icon_size)
                painter.drawPixmap(
                    int((widget.width() - hover_icon_size) / 2),
                    2,
                    icon_pixmap,
                )
                ButtonPainter._draw_scroll_value(
                    painter, widget, scroll_value, tm, style
                )
            else:
                actual_icon_size = (
                    max(12, int(style.icon_size_px or icon_size) - 4)
                    if scroll_value_always_visible
                    else int(style.icon_size_px or icon_size)
                )
                icon_pixmap = resolve_icon(current_icon).pixmap(
                    actual_icon_size, actual_icon_size
                )

                opacity = 0.4 if is_toggle_scroll and scroll_value == 0 else 1.0
                painter.setOpacity(opacity)
                x = (widget.width() - actual_icon_size) // 2
                y = (widget.height() - actual_icon_size) // 2 - 2
                painter.drawPixmap(x, y, icon_pixmap)
                painter.setOpacity(1.0)

                if scroll_value is not None and scroll_value_always_visible:
                    ButtonPainter._draw_scroll_value_always(
                        painter, widget, scroll_value, tm, style
                    )

        if badge_text is not None:
            ButtonPainter._draw_badge(
                painter, widget, badge_text, is_checked, tm, style
            )

        resolved_underline_color = (
            underline_color
            or style.underline_color
            or (style.accent_color if style.variant in {"primary", "accent"} else None)
        )
        if resolved_underline_color:
            config = UnderlineConfig(
                thickness=2.0 if scroll_value is not None else 1.0,
                vertical_offset=0.0 if scroll_value is not None else 1.0,
                arc_radius=2.0,
                alpha=(
                    resolved_underline_color.alpha()
                    if resolved_underline_color.alpha() < 255
                    else (40 if scroll_value is not None else 200)
                ),
                color=resolved_underline_color,
            )
            draw_bottom_underline(painter, widget.rect(), tm, config)

        if show_strike_through:
            strike_color = QColor("#ff4444") if tm.is_dark() else QColor("#cc0000")
            strike_color.setAlpha(180)
            pen = QPen(strike_color, 2)
            painter.setPen(pen)
            painter.drawLine(4, widget.height() - 4, widget.width() - 4, 4)

    @staticmethod
    def _draw_badge(
        painter: QPainter,
        widget,
        text: str,
        is_checked: bool,
        tm: ThemeManager,
        style,
    ):
        text_color = style.foreground_color or QColor(tm.get_color("dialog.text"))
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
    def _draw_scroll_value(
        painter: QPainter, widget, value: int, tm: ThemeManager, style
    ):
        if value == 0:
            hidden_icon = get_named_icon("divider_hidden")
            eye_pixmap = resolve_icon(hidden_icon).pixmap(11, 11)
            center_x = widget.width() // 2
            painter.drawPixmap(center_x - 5, 28, eye_pixmap)
        else:
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(style.foreground_color or tm.get_color("dialog.text"))
            text_rect = QRect(0, 28, widget.width(), 10)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))

    @staticmethod
    def _draw_scroll_value_always(
        painter: QPainter, widget, value: int, tm: ThemeManager, style
    ):
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(style.foreground_color or QColor(tm.get_color("dialog.text")))
        text_rect = QRect(0, 24, widget.width(), 12)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))
