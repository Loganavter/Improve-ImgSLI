from enum import Enum

from PyQt6.QtCore import (
    QPoint,
    QSize,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QMouseEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from toolkit.managers.theme_manager import ThemeManager
from ui.icon_manager import AppIcon, get_app_icon
from toolkit.widgets.atomic.tool_button import ToolButton

class ButtonType(Enum):
    DEFAULT = 0
    DELETE = 1

class AutoRepeatButton(ToolButton):

    INITIAL_DELAY = 400
    REPEAT_INTERVAL = 80

    def __init__(self, icon, parent=None):
        super().__init__(parent)
        self.setIcon(icon)

        self._initial_delay_timer = QTimer(self)
        self._initial_delay_timer.setSingleShot(True)
        self._initial_delay_timer.setInterval(self.INITIAL_DELAY)
        self._initial_delay_timer.timeout.connect(self._start_repeating)

        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(self.REPEAT_INTERVAL)
        self._repeat_timer.timeout.connect(self.clicked.emit)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._initial_delay_timer.start()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._initial_delay_timer.stop()
            self._repeat_timer.stop()
        super().mouseReleaseEvent(event)

    def _start_repeating(self):
        self.clicked.emit()
        self._repeat_timer.start()

class IconButton(QWidget):
    clicked = pyqtSignal()

    def __init__(self, icon: AppIcon, button_type: ButtonType, parent: QWidget = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setProperty("class", "icon-button")

        if button_type == ButtonType.DELETE:
            self.setProperty("variant", "delete")
        else:
            self.setProperty("variant", "default")

        self.setFixedSize(33, 33)

        self._icon_size = QSize(22, 22)
        self._icon = icon
        self.button_type = button_type
        self._flyout_is_open = False

        self.theme_manager = ThemeManager.get_instance()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.setProperty("state", "normal")

        self._update_icon()
        self.theme_manager.theme_changed.connect(self._update_icon)

        self.style().polish(self)

    def setFlyoutOpen(self, is_open: bool):
        if self._flyout_is_open != is_open:
            self._flyout_is_open = is_open
            if not is_open:
                should_be_hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
                new_state = "hover" if should_be_hovered else "normal"
                self.setProperty("state", new_state)
            else:
                self.setProperty("state", "normal")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def setIconSize(self, size: QSize):
        self._icon_size = size
        self._update_icon()

    def _update_icon(self):

        pixmap = get_app_icon(self._icon).pixmap(self._icon_size, QIcon.Mode.Normal, QIcon.State.Off)
        self.icon_label.setPixmap(pixmap)

    def enterEvent(self, event):
        if not self._flyout_is_open:
            self.setProperty("state", "hover")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._flyout_is_open:
            self.setProperty("state", "normal")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if not self._flyout_is_open:
            self.setProperty("state", "pressed")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self.setProperty("state", "hover" if self.rect().contains(event.pos()) else "normal")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        if self.rect().contains(event.pos()) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

class LongPressIconButton(QWidget):
    shortClicked = pyqtSignal()
    longPressed = pyqtSignal()

    def __init__(self, icon: AppIcon, button_type: ButtonType, parent: QWidget = None):
        super().__init__(parent)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.setProperty("class", "long-press-icon-button")

        if button_type == ButtonType.DELETE:
            self.setProperty("variant", "delete")
        else:
            self.setProperty("variant", "default")

        self.setFixedSize(33, 33)

        self._icon_size = QSize(22, 22)
        self._icon = icon
        self.button_type = button_type
        self._flyout_is_open = False

        self.theme_manager = ThemeManager.get_instance()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon_label = QLabel(self)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        self.setProperty("state", "normal")

        self._update_icon()
        self.theme_manager.theme_changed.connect(self._update_icon)

        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer.setInterval(600)
        self._long_press_timer.timeout.connect(self._on_long_press)
        self._long_press_triggered = False

        self.style().polish(self)

    def setIconSize(self, size: QSize):
        self._icon_size = size
        self._update_icon()

    def _update_icon(self):

        pixmap = get_app_icon(self._icon).pixmap(self._icon_size, QIcon.Mode.Normal, QIcon.State.Off)
        self.icon_label.setPixmap(pixmap)

    def enterEvent(self, event):
        self.setProperty("state", "hover")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setProperty("state", "normal")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setProperty("state", "pressed")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

            self._long_press_triggered = False
            self._long_press_timer.start()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._long_press_timer.stop()

            is_hovered = self.rect().contains(event.pos())
            self.setProperty("state", "hover" if is_hovered else "normal")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

            if not self._long_press_triggered and is_hovered:
                self.shortClicked.emit()

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _on_long_press(self):
        self._long_press_triggered = True
        self.longPressed.emit()

