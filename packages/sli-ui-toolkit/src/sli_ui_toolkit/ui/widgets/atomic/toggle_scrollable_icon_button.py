from __future__ import annotations

from PyQt6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.tooltips import install_custom_tooltip
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style, update_widget_style

class ToggleScrollableIconButton(QWidget):
    valueChanged = pyqtSignal(int)
    toggled = pyqtSignal(bool)
    rightClicked = pyqtSignal()
    middleClicked = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(
        self,
        icon_unchecked,
        icon_checked=None,
        min_val=0,
        max_val=10,
        show_underline=True,
        parent=None,
    ):
        super().__init__(parent)
        self._icon_unchecked = icon_unchecked
        self._icon_checked = icon_checked or icon_unchecked
        self._min_value = min_val
        self._max_value = max_val
        self._current_value = 1
        self._checked = False
        self._is_hovered = False
        self._is_pressed = False
        self._is_scrolling = False
        self._value_popup = None
        self._variant = "default"
        self._density = "normal"
        self._accent_color = None
        self._background_color = None
        self._foreground_color = None
        self._icon_size_px = 22
        self._corner_radius_px = 6
        self._scroll_end_timer = QTimer(self)
        self._scroll_end_timer.setSingleShot(True)
        self._scroll_end_timer.setInterval(800)
        self._scroll_end_timer.timeout.connect(self._on_scroll_ended)
        self.setFixedSize(36, 36)
        self.setMouseTracking(True)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        install_custom_tooltip(self)
        self._underline_color = None
        self._show_underline = show_underline
        self._saved_value = None

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, emit_signal: bool = True):
        checked = bool(checked)
        if self._checked != checked:
            self._checked = checked
            self.update()
            if emit_signal:
                self.toggled.emit(checked)

    def set_value(self, val):
        new_val = max(self._min_value, min(self._max_value, val))
        if new_val != self._current_value:
            old_value = self._current_value
            self._current_value = new_val
            if new_val == 0 and old_value > 0 and self._saved_value is None:
                self._saved_value = old_value
            if new_val == 0:
                self._show_value_popup(0)
                self._scroll_end_timer.start()
            self.update()

    def get_value(self) -> int:
        return self._current_value

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
                self._underline_color = self.property("underlineColor") or self._underline_color
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self.updateGeometry()
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
            elif name == "showUnderline":
                self._show_underline = bool(self.property("showUnderline"))
            update_widget_style(self)
        return super().event(event)

    def _on_scroll_ended(self):
        self._is_scrolling = False
        self._hide_value_popup()
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self._is_scrolling = False
        self._hide_value_popup()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_scrolling = False
            self._scroll_end_timer.stop()
            self._hide_value_popup()
            self._is_pressed = True
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            event.accept()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_pressed and event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self._do_toggle_click()
                self.clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.rect().contains(event.pos()):
                self.rightClicked.emit()
        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.rect().contains(event.pos()):
                self.middleClicked.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def _do_toggle_click(self):
        if not self._checked:

            if self._current_value > 0:
                self._saved_value = self._current_value
            self._current_value = 0
            self._checked = True
            self.update()
            self.toggled.emit(True)
            self.valueChanged.emit(0)
        else:

            restored = self._saved_value if self._saved_value and self._saved_value > 0 else 1
            self._saved_value = None
            self._current_value = restored
            self._checked = False
            self.update()
            self.toggled.emit(False)
            self.valueChanged.emit(restored)

    def click(self):
        self._do_toggle_click()
        self.clicked.emit()

    def wheelEvent(self, event):
        if not self.isEnabled():
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return

        self._is_scrolling = True
        self._scroll_end_timer.start()

        if self._checked:
            restored = self._saved_value if self._saved_value and self._saved_value > 0 else 1
            self._saved_value = None
            self._current_value = restored
            self._checked = False
            self.toggled.emit(False)
            self.valueChanged.emit(restored)
            self.update()
            self._show_value_popup(restored)
            event.accept()
            return

        step = 1 if delta > 0 else -1
        old_value = self._current_value
        new_val = max(self._min_value, min(self._max_value, self._current_value + step))
        if old_value > 0 and new_val == 0:

            self._saved_value = old_value
            self._current_value = 0
            self._checked = True
            self.toggled.emit(True)
            self.valueChanged.emit(0)
            self.update()
            self._show_value_popup(0)
            event.accept()
            return
        if new_val != self._current_value:
            self._current_value = new_val
            self.valueChanged.emit(new_val)
            self.update()
        self._show_value_popup(new_val)
        event.accept()

    def _show_value_popup(self, val=None):
        if not self.isVisible():
            return
        if val is None:
            val = self._current_value
        if val == 0:
            pixmap = resolve_icon(get_named_icon("divider_hidden")).pixmap(18, 18)
            popup_text = ""
            popup_size = QSize(32, 28)
        else:
            pixmap = None
            popup_text = str(val)
            popup_size = QSize(32 if val >= 10 else 26, 28)
        if self._value_popup is None:
            self._value_popup = QLabel(parent=self.window())
            self._value_popup.setObjectName("ValuePopupLabel")
            self._value_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._value_popup.setPixmap(pixmap if pixmap is not None else QPixmap())
        self._value_popup.setText(popup_text)
        self._value_popup.setFixedSize(popup_size)
        window = self.window()
        pos = self.mapToGlobal(QPoint(0, 0))
        local_pos = window.mapFromGlobal(pos) if window is not None else pos
        popup_x = local_pos.x() + (self.width() - self._value_popup.width()) // 2
        popup_y = local_pos.y() - self._value_popup.height() - 6
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
        tm = self.theme_manager
        style = read_widget_style(
            self,
            default_icon_size=self._icon_size_px,
            default_corner_radius=self._corner_radius_px,
        )
        if style.background_color is not None:
            bg_color = style.background_color
        elif style.variant == "primary" and style.accent_color is not None:
            bg_color = style.accent_color
        elif style.variant == "ghost":
            bg_color = QColor(0, 0, 0, 0)
        elif style.variant == "subtle":
            bg_color = tm.get_color("Window")
        elif self._is_pressed:
            bg_color = tm.get_color("button.toggle.background.pressed")
        elif self.isChecked():
            bg_color = tm.get_color(
                "button.toggle.background.checked.hover"
                if self._is_hovered
                else "button.toggle.background.checked"
            )
        elif self._is_hovered:
            bg_color = tm.get_color("button.toggle.background.hover")
        else:
            bg_color = tm.get_color("button.toggle.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        radius = max(0, int(style.corner_radius_px or 6))
        painter.drawRoundedRect(self.rect(), radius, radius)

        current_icon_enum = self._icon_checked if self.isChecked() else self._icon_unchecked
        painter.setOpacity(0.4 if self._current_value == 0 else 1.0)
        bottom_padding = 0
        vertical_shift = 0
        if self._show_underline:
            bottom_padding = 1
            vertical_shift = 2
        if self._is_hovered and not self._is_scrolling:
            hover_icon_size = max(12, int(style.icon_size_px or self._icon_size_px) - 6)
            icon_pixmap = resolve_icon(current_icon_enum).pixmap(hover_icon_size, hover_icon_size)
            painter.drawPixmap(int((self.width() - hover_icon_size) / 2), 2, icon_pixmap)
            painter.setOpacity(1.0)
            value_y = 28 - bottom_padding
            self._draw_value_at(
                painter,
                QPoint(int(self.rect().center().x()), value_y),
                9,
                style,
            )
        else:
            actual_icon_size = int(style.icon_size_px or self._icon_size_px)
            icon_pixmap = resolve_icon(current_icon_enum).pixmap(actual_icon_size, actual_icon_size)
            icon_y = int((self.height() - actual_icon_size - bottom_padding) / 2) - vertical_shift
            painter.drawPixmap(int((self.width() - actual_icon_size) / 2), icon_y, icon_pixmap)
        underline_color = style.underline_color or style.accent_color or self._underline_color
        if self._show_underline and underline_color is not None:
            config = UnderlineConfig(
                thickness=1.0,
                vertical_offset=1.0,
                arc_radius=2.0,
                alpha=underline_color.alpha() if underline_color.alpha() < 255 else 200,
                color=underline_color,
            )
            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)

    def _draw_value_at(self, painter, pos, size, style):
        font = QFont()
        font.setPixelSize(size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(style.foreground_color or self.theme_manager.get_color("dialog.text"))
        if self._current_value == 0:
            eye_pixmap = resolve_icon(get_named_icon("divider_hidden")).pixmap(size + 2, size + 2)
            painter.drawPixmap(
                pos.x() - int(eye_pixmap.width() / 2),
                pos.y() - int(eye_pixmap.height() / 2) - 2,
                eye_pixmap,
            )
        else:
            painter.drawText(
                QRect(pos.x() - 15, pos.y() - 10, 30, 20),
                Qt.AlignmentFlag.AlignCenter,
                str(self._current_value),
            )

    def set_color(self, color: QColor | None):
        if not self._show_underline:
            self._underline_color = None
        else:
            self._underline_color = color
        self.setProperty("underlineColor", color)
        self.update()

    def set_show_underline(self, show: bool):
        if self._show_underline != show:
            self._show_underline = show
            self.setProperty("showUnderline", show)
            self.update()

    def get_saved_value(self):
        return self._saved_value

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self)

    def getIconSizePx(self) -> int:
        return int(self._icon_size_px)

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        if self._icon_size_px != size_px:
            self._icon_size_px = size_px
            self.setProperty("iconSizePx", size_px)
            update_widget_style(self, update_geometry=True)

    def getCornerRadiusPx(self) -> int:
        return int(self._corner_radius_px)

    def setCornerRadiusPx(self, radius_px: int):
        self._corner_radius_px = max(0, int(radius_px))
        self.setProperty("cornerRadiusPx", self._corner_radius_px)
        update_widget_style(self)

    def set_saved_value(self, value):
        self._saved_value = value

    def restore_saved_value(self):
        if self._saved_value is not None:
            saved = self._saved_value
            self._saved_value = None
            return saved
        return None
