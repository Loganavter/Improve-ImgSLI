from enum import Flag, auto
import sys
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QPoint, QSize
from PyQt6.QtGui import QPainter, QMouseEvent, QColor, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QWidget, QLabel

from ui.icon_manager import AppIcon, get_app_icon
from toolkit.managers.theme_manager import ThemeManager
from .button_painter import ButtonPainter

class ButtonMode(Flag):
    SIMPLE = auto()
    TOGGLE = auto()
    SCROLL = auto()
    LONG_PRESS = auto()
    NUMBERED = auto()

class UnifiedIconButton(QWidget):

    clicked = pyqtSignal()
    toggled = pyqtSignal(bool)
    valueChanged = pyqtSignal(int)
    longPressed = pyqtSignal()
    rightClicked = pyqtSignal()

    def __init__(self, icon_unchecked: AppIcon,
                 icon_checked: AppIcon = None,
                 mode: ButtonMode = ButtonMode.SIMPLE,
                 parent=None):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.mode = mode
        self._icon_unchecked = icon_unchecked
        self._icon_checked = icon_checked if icon_checked else icon_unchecked

        self._checked = False
        self._hovered = False
        self._pressed = False
        self._custom_color = None

        self._value = 1
        self._min_val = 0
        self._max_val = 10
        self._is_scrolling = False
        self._value_popup = None
        self._scroll_end_timer = QTimer(self)
        self._scroll_end_timer.setSingleShot(True)
        self._scroll_end_timer.setInterval(800)
        self._scroll_end_timer.timeout.connect(self._on_scroll_ended)

        self._display_number = None

        self._lp_timer = QTimer(self)
        self._lp_timer.setInterval(600)
        self._lp_timer.setSingleShot(True)
        self._lp_timer.timeout.connect(self._on_long_press_timeout)
        self._lp_triggered = False

        self.setMouseTracking(True)
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def setChecked(self, checked: bool, emit: bool = True):
        if not (self.mode & ButtonMode.TOGGLE):
            return
        if self._checked != checked:
            self._checked = checked
            self.update()
            if emit:
                self.toggled.emit(checked)

    def isChecked(self) -> bool:
        return self._checked

    def setValue(self, val: int):
        if not (self.mode & ButtonMode.SCROLL):
            return
        self._value = max(self._min_val, min(self._max_val, val))
        self.update()

    def getValue(self) -> int:
        return self._value

    def setRange(self, min_v: int, max_v: int):
        self._min_val = min_v
        self._max_val = max_v
        self._value = max(self._min_val, min(self._max_val, self._value))

    def setDisplayNumber(self, num: int | None):
        self._display_number = num
        self.update()

    def set_color(self, color: QColor):
        self._custom_color = color
        self.update()

    def is_strike_through(self) -> bool:
        return (self.mode & ButtonMode.NUMBERED) and self._checked and self._display_number is None

    def mousePressEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            if self.mode & ButtonMode.LONG_PRESS:
                self._lp_triggered = False
                self._lp_timer.start()
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        if e.button() == Qt.MouseButton.LeftButton:
            self._lp_timer.stop()
            self._pressed = False
            self.update()

            if self.rect().contains(e.pos()) and not self._lp_triggered:

                if self.mode & ButtonMode.TOGGLE:
                    self.setChecked(not self._checked)

                self.clicked.emit()

        elif e.button() == Qt.MouseButton.RightButton:
            if self.rect().contains(e.pos()):
                self.rightClicked.emit()

        self._lp_triggered = False
        super().mouseReleaseEvent(e)

    def _on_long_press_timeout(self):
        if self._pressed:
            self._lp_triggered = True
            self.longPressed.emit()

    def wheelEvent(self, e: QWheelEvent):
        if not (self.mode & ButtonMode.SCROLL) or not self.isEnabled():
            return super().wheelEvent(e)

        delta = e.angleDelta().y()
        if delta == 0:
            return

        self._is_scrolling = True
        self._scroll_end_timer.start()

        step = 1 if delta > 0 else -1
        new_val = max(self._min_val, min(self._max_val, self._value + step))

        if new_val != self._value:
            self._value = new_val
            self.valueChanged.emit(new_val)
            self._show_scroll_popup(new_val)
            self.update()
        e.accept()

    def _on_scroll_ended(self):
        self._is_scrolling = False
        self._hide_scroll_popup()
        self.update()

    def enterEvent(self, e):
        self._hovered = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hovered = False
        self._pressed = False
        self._hide_scroll_popup()
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        painter = QPainter(self)

        badge = str(self._display_number) if self._display_number is not None else None

        scroll_value = self._value if (self.mode & ButtonMode.SCROLL) else None

        scroll_always_visible = (self.mode & ButtonMode.SCROLL) and not (self.mode & ButtonMode.TOGGLE)

        ButtonPainter.paint(
            widget=self,
            painter=painter,
            icon_unchecked=self._icon_unchecked,
            icon_checked=self._icon_checked,
            is_checked=self._checked,
            is_pressed=self._pressed,
            is_hovered=self._hovered,
            is_scrolling=self._is_scrolling,
            badge_text=badge,
            scroll_value=scroll_value,
            scroll_value_always_visible=scroll_always_visible,
            underline_color=self._custom_color,
            show_strike_through=self.is_strike_through()
        )
        painter.end()

    def _show_scroll_popup(self, val: int):
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

        if val == 0:
            pixmap = get_app_icon(AppIcon.DIVIDER_HIDDEN).pixmap(18, 18)
            self._value_popup.setPixmap(pixmap)
            self._value_popup.setText("")
            self._value_popup.setFixedSize(32, 28)
        else:
            self._value_popup.setPixmap(QPixmap())
            self._value_popup.setText(str(val))
            self._value_popup.setFixedSize(32 if val >= 10 else 26, 28)

        pos = self.mapToGlobal(QPoint(0, 0))
        popup_x = pos.x() + (self.width() - self._value_popup.width()) // 2
        popup_y = pos.y() - self._value_popup.height() - 6
        self._value_popup.move(popup_x, popup_y)

        if not self._value_popup.isVisible():
            self._value_popup.show()

        self._value_popup.raise_()

    def _hide_scroll_popup(self):
        if self._value_popup:
            self._value_popup.hide()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if not enabled:
            self._hide_scroll_popup()
        self.update()

