from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.tooltips import install_custom_tooltip
from sli_ui_toolkit.ui.widgets.helpers import (
    UnderlineConfig,
    draw_bottom_underline,
)
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style, update_widget_style

class ScrollableIconButton(QPushButton):
    valueChanged = pyqtSignal(int)

    def __init__(self, icon, min_value: int = 1, max_value: int = 20, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._min_value = min_value
        self._max_value = max_value
        self._current_value = min_value
        self._current_color = None
        self._value_popup = None
        self._variant = "default"
        self._density = "normal"
        self._foreground_color = None
        self._background_color = None
        self._accent_color = None
        self._icon_size_px = 18
        self._corner_radius_px = 6
        self._show_underline = True

        self._is_pressed = False
        self._is_hovered = False

        self.setFixedSize(36, 36)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._update_style)

        self._popup_timer = QTimer(self)
        self._popup_timer.setSingleShot(True)
        self._popup_timer.setInterval(1000)
        self._popup_timer.timeout.connect(self._hide_value_popup)
        install_custom_tooltip(self)
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
        self.setProperty("underlineColor", color)
        self.update()

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "accentColor":
                self._accent_color = self.property("accentColor") or self._accent_color
            elif name == "backgroundColor":
                self._background_color = self.property("backgroundColor") or self._background_color
            elif name in {"foregroundColor", "textColor"}:
                self._foreground_color = self.property(name) or self._foreground_color
            elif name == "underlineColor":
                self._current_color = self.property("underlineColor") or self._current_color
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self._update_style()
                self.updateGeometry()
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
            elif name == "showUnderline":
                self._show_underline = bool(self.property("showUnderline"))
            update_widget_style(self)
        return super().event(event)

    def wheelEvent(self, event):
        if not self.isEnabled():
            event.ignore()
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        step = 1
        new_value = min(self._max_value, self._current_value + step) if delta > 0 else max(self._min_value, self._current_value - step)

        if new_value != self._current_value:
            self._current_value = new_value
            self.valueChanged.emit(new_value)
            self._show_value_popup(new_value)
            self.update()
            event.accept()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self._popup_timer.stop()
            self._hide_value_popup()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def _show_value_popup(self, value: int):
        if not self.isVisible():
            return
        popup_size = QSize(26, 24) if value < 10 else QSize(32, 24)
        if self._value_popup is None:
            self._value_popup = QLabel(parent=self.window())
            self._value_popup.setObjectName("ValuePopupLabel")
            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_popup.setText(str(value))
        self._value_popup.setFixedSize(popup_size)
        window = self.window()
        pos = self.mapToGlobal(QPoint(0, 0))
        local_pos = window.mapFromGlobal(pos) if window is not None else pos
        popup_x = local_pos.x() + (self.width() - self._value_popup.width()) // 2
        popup_y = local_pos.y() - self._value_popup.height() - 10
        self._value_popup.move(popup_x, popup_y)
        if not self._value_popup.isVisible():
            self._value_popup.show()
        self._value_popup.raise_()

    def _hide_value_popup(self):
        if self._value_popup:
            self._value_popup.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = read_widget_style(self, default_icon_size=self._icon_size_px, default_corner_radius=self._corner_radius_px)

        if style.background_color is not None:
            bg_color = style.background_color
        elif style.variant == "primary" and style.accent_color is not None:
            bg_color = style.accent_color
        elif style.variant == "ghost":
            bg_color = QColor(0, 0, 0, 0)
        elif style.variant == "subtle":
            bg_color = self.theme_manager.get_color("Window")
        else:
            bg_color = self.theme_manager.get_color("button.toggle.background.normal")

        if self.isEnabled():
            if self._is_pressed:
                bg_color = self.theme_manager.get_color("button.toggle.background.pressed")
            elif self.isChecked():
                bg_color = self.theme_manager.get_color(
                    "button.toggle.background.checked.hover" if self._is_hovered else "button.toggle.background.checked"
                )
            elif self._is_hovered:
                bg_color = self.theme_manager.get_color("button.toggle.background.hover")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        radius = max(0, int(style.corner_radius_px or 6))
        painter.drawRoundedRect(self.rect(), radius, radius)

        icon = self.icon()
        if not icon.isNull():
            icon_size = int(style.icon_size_px or 18)
            mode = QIcon.Mode.Active if self._is_hovered else QIcon.Mode.Normal
            pixmap = icon.pixmap(QSize(icon_size, icon_size), mode)
            icon_x = (self.width() - pixmap.width()) // 2
            icon_y = max(2, (self.height() - 12 - pixmap.height()) // 2)
            painter.drawPixmap(icon_x, icon_y, pixmap)

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(style.foreground_color or QColor(self.theme_manager.get_color("dialog.text")))

        text_rect = QRect(0, 24, 36, 12)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(self._current_value))

        underline_color = style.underline_color or style.accent_color or self._current_color
        if self._show_underline and underline_color is not None:
            config = UnderlineConfig(
                thickness=2.0,
                vertical_offset=0.0,
                arc_radius=2.0,
                alpha=underline_color.alpha() if underline_color.alpha() < 255 else 40,
                color=underline_color,
            )
            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)

        painter.end()

    def _update_style(self):
        self.setIcon(resolve_icon(self._icon))
        self.setIconSize(QSize(18, 18))
