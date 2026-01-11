import logging
import sys
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer
from PyQt6.QtGui import QPainter, QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import QWidget, QLabel

from ui.icon_manager import AppIcon, get_app_icon
from toolkit.managers.theme_manager import ThemeManager
from toolkit.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)

logger = logging.getLogger("ImproveImgSLI")

class ToggleScrollableIconButton(QWidget):
    valueChanged = pyqtSignal(int)
    toggled = pyqtSignal(bool)
    rightClicked = pyqtSignal()
    middleClicked = pyqtSignal()
    clicked = pyqtSignal()

    def __init__(self, icon_unchecked, icon_checked=None, min_val=0, max_val=10, show_underline=True, parent=None):
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
        self._scroll_end_timer = QTimer(self)
        self._scroll_end_timer.setSingleShot(True)
        self._scroll_end_timer.setInterval(800)
        self._scroll_end_timer.timeout.connect(self._on_scroll_ended)

        self.setFixedSize(36, 36)
        self.setMouseTracking(True)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

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
        logger.debug(f"ToggleScrollableIconButton.mousePressEvent: button={event.button()}, pos={event.pos()}, rect={self.rect()}, contains={self.rect().contains(event.pos())}")
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self.update()
        elif event.button() == Qt.MouseButton.MiddleButton:
            logger.debug("ToggleScrollableIconButton: Middle button pressed, accepting event")
            event.accept()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        logger.debug(f"ToggleScrollableIconButton.mouseReleaseEvent: button={event.button()}, pos={event.pos()}, rect={self.rect()}, contains={self.rect().contains(event.pos())}, is_pressed={self._is_pressed}")

        if self._is_pressed and event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                logger.debug("ToggleScrollableIconButton: Left button released, toggling and emitting clicked")
                self.setChecked(not self.isChecked())
                self.clicked.emit()

        elif event.button() == Qt.MouseButton.RightButton:
            if self.rect().contains(event.pos()):
                logger.debug("ToggleScrollableIconButton: Right button released, emitting rightClicked")
                self.rightClicked.emit()

        elif event.button() == Qt.MouseButton.MiddleButton:
            if self.rect().contains(event.pos()):
                logger.debug("ToggleScrollableIconButton: Middle button released, emitting middleClicked")
                self.middleClicked.emit()
                event.accept()
                return
            else:
                logger.debug(f"ToggleScrollableIconButton: Middle button released but pos {event.pos()} not in rect {self.rect()}")

        super().mouseReleaseEvent(event)

    def click(self):
        self.setChecked(not self.isChecked())
        self.clicked.emit()

    def wheelEvent(self, event):
        logger.debug(f"ToggleScrollableIconButton.wheelEvent: enabled={self.isEnabled()}, delta={event.angleDelta().y()}, pos={event.position()}, rect={self.rect()}, contains={self.rect().contains(event.position().toPoint())}")
        if not self.isEnabled():
            logger.debug("ToggleScrollableIconButton: wheelEvent ignored - button disabled")
            return
        delta = event.angleDelta().y()
        if delta == 0:
            logger.debug("ToggleScrollableIconButton: wheelEvent ignored - delta is 0")
            return

        logger.debug(f"ToggleScrollableIconButton: Processing wheel event, delta={delta}, current_value={self._current_value}, min={self._min_value}, max={self._max_value}")
        self._is_scrolling = True
        self._scroll_end_timer.start()

        step = 1 if delta > 0 else -1
        old_value = self._current_value
        new_val = max(self._min_value, min(self._max_value, self._current_value + step))

        logger.debug(f"ToggleScrollableIconButton: Calculated new_val={new_val} (old={self._current_value}, step={step}, min={self._min_value}, max={self._max_value})")

        if old_value > 0 and new_val == 0:
            if self._saved_value is None:
                self._saved_value = old_value
                logger.debug(f"ToggleScrollableIconButton: Saved value {old_value} before going to 0")

        elif old_value == 0 and new_val > 0:
            if self._saved_value is not None and self._saved_value > 0:
                restored_value = self._saved_value
                self._saved_value = None
                new_val = restored_value
                logger.debug(f"ToggleScrollableIconButton: Restored value {restored_value} from saved")
            else:

                new_val = 3
                logger.debug(f"ToggleScrollableIconButton: No saved value, using default 3")

        if new_val != self._current_value:
            self._current_value = new_val
            logger.debug(f"ToggleScrollableIconButton: Value changed to {new_val}, emitting valueChanged")
            self.valueChanged.emit(new_val)
            self.update()
        else:
            logger.debug(f"ToggleScrollableIconButton: Value unchanged ({new_val})")

        self._show_value_popup(new_val)
        event.accept()

    def _show_value_popup(self, val=None):
        if not self.isVisible():
            return
        if val is None:
            val = self._current_value

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

    def _hide_value_popup(self):
        if self._value_popup:
            self._value_popup.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = self.theme_manager
        if self._is_pressed:
            bg_color = tm.get_color("button.toggle.background.pressed")
        elif self.isChecked():
            if self._is_hovered:
                bg_color = tm.get_color("button.toggle.background.checked.hover")
            else:
                bg_color = tm.get_color("button.toggle.background.checked")
        elif self._is_hovered:
            bg_color = tm.get_color("button.toggle.background.hover")
        else:
            bg_color = tm.get_color("button.toggle.background.normal")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(self.rect(), 6, 6)

        current_icon_enum = self._icon_checked if self.isChecked() else self._icon_unchecked

        painter.setOpacity(0.4 if self._current_value == 0 else 1.0)

        bottom_padding = 0
        vertical_shift = 0

        if self._show_underline:
            bottom_padding = 1
            vertical_shift = 2

        if self._is_hovered and not self._is_scrolling:

            icon_pixmap = get_app_icon(current_icon_enum).pixmap(16, 16)

            painter.drawPixmap(int((self.width() - 16) / 2), 2, icon_pixmap)

            painter.setOpacity(1.0)

            value_y = 28 - bottom_padding
            self._draw_value_at(painter, QPoint(int(self.rect().center().x()), value_y), 9)

        else:

            icon_pixmap = get_app_icon(current_icon_enum).pixmap(22, 22)

            icon_y = int((self.height() - 22 - bottom_padding) / 2) - vertical_shift
            painter.drawPixmap(int((self.width() - 22) / 2), icon_y, icon_pixmap)

        if self._show_underline and self._underline_color is not None:
            config = UnderlineConfig(
                thickness=1.0,
                vertical_offset=1.0,
                arc_radius=2.0,
                alpha=self._underline_color.alpha() if self._underline_color.alpha() < 255 else 200,
                color=self._underline_color
            )
            draw_bottom_underline(painter, self.rect(), self.theme_manager, config)

    def _draw_value_at(self, painter, pos, size):
        font = QFont()
        font.setPixelSize(size)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(self.theme_manager.get_color("dialog.text"))

        if self._current_value == 0:

            eye_pixmap = get_app_icon(AppIcon.DIVIDER_HIDDEN).pixmap(size+2, size+2)
            painter.drawPixmap(pos.x() - int(eye_pixmap.width()/2), pos.y() - int(eye_pixmap.height()/2) - 2, eye_pixmap)
        else:
            painter.drawText(QRect(pos.x() - 15, pos.y() - 10, 30, 20), Qt.AlignmentFlag.AlignCenter, str(self._current_value))

    def set_color(self, color: QColor):
        if not self._show_underline:
            self._underline_color = None
        else:
            self._underline_color = color
        self.update()

    def set_show_underline(self, show: bool):
        if self._show_underline != show:
            self._show_underline = show
            self.update()

    def get_saved_value(self):
        return self._saved_value

    def set_saved_value(self, value):
        self._saved_value = value

    def restore_saved_value(self):
        if self._saved_value is not None:
            saved = self._saved_value
            self._saved_value = None
            return saved
        return None

