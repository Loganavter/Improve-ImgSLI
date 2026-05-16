from enum import Flag, auto

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QMouseEvent, QPainter, QPixmap, QWheelEvent
from PyQt6.QtWidgets import QLabel, QWidget

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.button_painter import ButtonPainter
from sli_ui_toolkit.ui.widgets.style_bridge import update_widget_style

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

    def __init__(
        self,
        icon_unchecked,
        icon_checked=None,
        mode: ButtonMode = ButtonMode.SIMPLE,
        parent=None,
    ):
        super().__init__(parent)
        self.setFixedSize(36, 36)
        self.mode = mode
        self._icon_unchecked = icon_unchecked
        self._icon_checked = icon_checked if icon_checked else icon_unchecked
        self._popup_controller = None

        self._checked = False
        self._hovered = False
        self._pressed = False
        self._custom_color = None
        self._variant = "default"
        self._tone = "neutral"
        self._density = "normal"
        self._shape = "rounded"
        self._icon_size_px = 22
        self._corner_radius_px = 6

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

    def set_popup_controller(self, popup_controller):
        self._popup_controller = popup_controller

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

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            name = event.propertyName().data().decode("utf-8", errors="ignore")
            if name == "variant":
                self._variant = str(self.property("variant") or self._variant)
            elif name == "tone":
                self._tone = str(self.property("tone") or self._tone)
            elif name == "density":
                self._density = str(self.property("density") or self._density)
            elif name == "shape":
                self._shape = str(self.property("shape") or self._shape)
            elif name == "iconSizePx":
                self._icon_size_px = max(1, int(self.property("iconSizePx") or self._icon_size_px))
                update_widget_style(self, update_geometry=True)
            elif name == "cornerRadiusPx":
                self._corner_radius_px = max(0, int(self.property("cornerRadiusPx") or self._corner_radius_px))
                update_widget_style(self)
            elif name in {"accentColor", "backgroundColor", "foregroundColor", "underlineColor", "showUnderline"}:
                update_widget_style(self)
        return super().event(event)

    def is_strike_through(self) -> bool:
        return (
            (self.mode & ButtonMode.NUMBERED)
            and self._checked
            and self._display_number is None
        )

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_scrolling = False
            self._scroll_end_timer.stop()
            self._hide_scroll_popup()
            self._pressed = True
            if self.mode & ButtonMode.LONG_PRESS:
                self._lp_triggered = False
                self._lp_timer.start()
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._lp_timer.stop()
            self._pressed = False
            self.update()

            if self.rect().contains(event.pos()) and not self._lp_triggered:
                if self.mode & ButtonMode.TOGGLE:
                    self.setChecked(not self._checked)
                self.clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            if self.rect().contains(event.pos()):
                self.rightClicked.emit()

        self._lp_triggered = False
        super().mouseReleaseEvent(event)

    def _on_long_press_timeout(self):
        if self._pressed:
            self._lp_triggered = True
            self.longPressed.emit()

    def wheelEvent(self, event: QWheelEvent):
        if not (self.mode & ButtonMode.SCROLL) or not self.isEnabled():
            return super().wheelEvent(event)

        delta = event.angleDelta().y()
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
        event.accept()

    def _on_scroll_ended(self):
        self._is_scrolling = False
        self._hide_scroll_popup()
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self._hide_scroll_popup()
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        badge = str(self._display_number) if self._display_number is not None else None
        scroll_value = self._value if (self.mode & ButtonMode.SCROLL) else None
        scroll_always_visible = (self.mode & ButtonMode.SCROLL) and not (
            self.mode & ButtonMode.TOGGLE
        )

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
            show_strike_through=self.is_strike_through(),
            icon_size=self._icon_size_px,
        )
        painter.end()

    def getVariant(self) -> str:
        return self._variant

    def setVariant(self, variant: str):
        self._variant = str(variant or "default")
        self.setProperty("variant", self._variant)
        update_widget_style(self)

    def getTone(self) -> str:
        return self._tone

    def setTone(self, tone: str):
        self._tone = str(tone or "neutral")
        self.setProperty("tone", self._tone)
        update_widget_style(self)

    def getDensity(self) -> str:
        return self._density

    def setDensity(self, density: str):
        self._density = str(density or "normal")
        self.setProperty("density", self._density)
        update_widget_style(self, update_geometry=True)

    def getShape(self) -> str:
        return self._shape

    def setShape(self, shape: str):
        self._shape = str(shape or "rounded")
        self.setProperty("shape", self._shape)
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
        radius_px = max(0, int(radius_px))
        if self._corner_radius_px != radius_px:
            self._corner_radius_px = radius_px
            self.setProperty("cornerRadiusPx", radius_px)
            update_widget_style(self)

    def _show_scroll_popup(self, val: int):
        if not self.isVisible():
            return

        if val == 0:
            pixmap = resolve_icon(get_named_icon("divider_hidden")).pixmap(18, 18)
            popup_text = ""
            popup_size = QSize(32, 28)
        else:
            pixmap = None
            popup_text = str(val)
            popup_size = QSize(32 if val >= 10 else 26, 28)

        popup_id = f"unified_icon_button:{id(self)}"
        popup_controller = self._popup_controller
        if popup_controller is not None:
            popup_controller.show_popup(
                popup_id,
                self,
                text=popup_text,
                pixmap=pixmap,
                size=popup_size,
                position="top",
                offset=6,
                timeout_ms=self._scroll_end_timer.interval(),
            )
            return

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

    def _hide_scroll_popup(self):
        popup_id = f"unified_icon_button:{id(self)}"
        popup_controller = self._popup_controller
        if popup_controller is not None:
            popup_controller.hide_popup(popup_id)
        if self._value_popup:
            self._value_popup.hide()

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        if not enabled:
            self._hide_scroll_popup()
        self.update()
