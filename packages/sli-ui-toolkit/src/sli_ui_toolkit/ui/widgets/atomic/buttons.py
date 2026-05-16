from enum import Enum

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QIcon, QMouseEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.tool_button import ToolButton
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style, update_widget_style

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

    def __init__(self, icon, button_type: ButtonType, parent: QWidget = None):
        super().__init__(parent)
        self._variant = "default"
        self._density = "normal"
        self._icon_size_px = 22
        self._corner_radius_px = 6
        self._foreground_color = None
        self._background_color = None
        self._accent_color = None
        self._underline_color = None
        self._show_underline = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("class", "icon-button")
        self.setProperty(
            "variant", "delete" if button_type == ButtonType.DELETE else "default"
        )
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
                hovered = self.rect().contains(self.mapFromGlobal(QCursor.pos()))
                self.setProperty("state", "hover" if hovered else "normal")
            else:
                self.setProperty("state", "normal")
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def setIconSize(self, size: QSize):
        self._icon_size = size
        self._update_icon()

    def _update_icon(self):
        pixmap = resolve_icon(self._icon).pixmap(
            self._icon_size, QIcon.Mode.Normal, QIcon.State.Off
        )
        self.icon_label.setPixmap(pixmap)

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self._icon_size = QSize(self._icon_size_px, self._icon_size_px)
                self._update_icon()
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
            elif name == "foregroundColor":
                self._foreground_color = self.property("foregroundColor") or self._foreground_color
            elif name == "backgroundColor":
                self._background_color = self.property("backgroundColor") or self._background_color
            elif name == "accentColor":
                self._accent_color = self.property("accentColor") or self._accent_color
            elif name == "underlineColor":
                self._underline_color = self.property("underlineColor") or self._underline_color
            elif name == "showUnderline":
                self._show_underline = bool(self.property("showUnderline"))
            update_widget_style(self)
        return super().event(event)

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
        self.setProperty(
            "state", "hover" if self.rect().contains(event.pos()) else "normal"
        )
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        if self.rect().contains(event.pos()) and event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

    def getVariant(self) -> str:
        return getattr(self, "_variant", "default")

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getDensity(self) -> str:
        return getattr(self, "_density", "normal")

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self)

    def getForegroundColor(self):
        return getattr(self, "_foreground_color", None)

    def setForegroundColor(self, color):
        self._foreground_color = color
        self.setProperty("foregroundColor", color)
        update_widget_style(self)

    def getIconSizePx(self) -> int:
        return int(getattr(self, "_icon_size_px", 22))

    def setIconSizePx(self, size_px: int):
        size_px = max(1, int(size_px))
        self._icon_size_px = size_px
        self._icon_size = QSize(size_px, size_px)
        self.setProperty("iconSizePx", size_px)
        self._update_icon()
        update_widget_style(self, update_geometry=True)

class LongPressIconButton(QWidget):
    shortClicked = pyqtSignal()
    longPressed = pyqtSignal()

    def __init__(self, icon, button_type: ButtonType, parent: QWidget = None):
        super().__init__(parent)
        self._variant = "default"
        self._density = "normal"
        self._foreground_color = None
        self._icon_size_px = 22
        self._corner_radius_px = 6
        self._underline_color = None
        self._show_underline = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("class", "long-press-icon-button")
        self.setProperty(
            "variant", "delete" if button_type == ButtonType.DELETE else "default"
        )
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
        pixmap = resolve_icon(self._icon).pixmap(
            self._icon_size, QIcon.Mode.Normal, QIcon.State.Off
        )
        self.icon_label.setPixmap(pixmap)

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                self._icon_size = QSize(self._icon_size_px, self._icon_size_px)
                self._update_icon()
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
            elif name == "foregroundColor":
                self._foreground_color = self.property("foregroundColor") or self._foreground_color
            elif name == "underlineColor":
                self._underline_color = self.property("underlineColor") or self._underline_color
            elif name == "showUnderline":
                self._show_underline = bool(self.property("showUnderline"))
            update_widget_style(self)
        return super().event(event)

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

    def paintEvent(self, event):
        super().paintEvent(event)
