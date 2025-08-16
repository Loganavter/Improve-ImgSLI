

from enum import Enum
from functools import lru_cache
import sys
from PyQt6.QtCore import (
    Qt, QSize, QTimer, pyqtSignal, QPointF, QPropertyAnimation,
    QEasingCurve, QRect, QRectF, QPoint, pyqtProperty, QAbstractAnimation, QObject, QEvent
)
from PyQt6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPolygon, QFont,
    QMouseEvent, QCursor, QPixmap, QFontMetrics
)
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
    QScrollArea, QScrollBar, QApplication, QGraphicsDropShadowEffect, QPushButton, QColorDialog,
    QButtonGroup,
)
from ui.widgets import ToolButton, FluentSlider, FluentSwitch, FluentRadioButton

from core.theme import ThemeManager
from events.drag_drop_handler import DragAndDropService
from ui.icon_manager import get_icon, AppIcon
from resources import translations as translations_mod
import logging
from .helpers.underline_painter import draw_bottom_underline, UnderlineConfig
from ui.gesture_resolver import RatingGestureTransaction

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

logger = logging.getLogger("ImproveImgSLI")

class PathTooltip(QWidget):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PathTooltip()
        return cls._instance

    def __init__(self):
        if PathTooltip._instance is not None:
            raise RuntimeError("This class is a singleton!")

        super().__init__(None, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.main_layout = QVBoxLayout(self)
        self.SHADOW_WIDTH = 8
        self.main_layout.setContentsMargins(self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH, self.SHADOW_WIDTH)

        self.content_widget = QLabel(self)
        self.content_widget.setObjectName("TooltipContentWidget")
        self.main_layout.addWidget(self.content_widget)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(self.SHADOW_WIDTH * 2)
        self.shadow.setColor(QColor(0, 0, 0, 100))
        self.shadow.setOffset(1, 2)
        self.content_widget.setGraphicsEffect(self.shadow)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_style)
        self._apply_style()

    def _apply_style(self):

        self.style().unpolish(self.content_widget)
        self.style().polish(self.content_widget)
        self.update()

    def show_tooltip(self, pos: QPoint, text: str):
        if not text:
            return
        self.content_widget.setText(text)
        self.adjustSize()

        self.move(pos + QPoint(15, 15))
        self.show()

    def hide_tooltip(self):
        self.hide()

def lerp_color(c1: QColor, c2: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    r = int(c1.red() + (c2.red() - c1.red()) * t)
    g = int(c1.green() + (c2.green() - c1.green()) * t)
    b = int(c1.blue() + (c2.blue() - c1.blue()) * t)
    a = int(c1.alpha() + (c2.alpha() - c1.alpha()) * t)
    return QColor(r, g, b, a)

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

        self.setFixedSize(36, 36)

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
        pixmap = get_icon(self._icon).pixmap(self._icon_size)
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

        self.setFixedSize(36, 36)

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
        pixmap = get_icon(self._icon).pixmap(self._icon_size)
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

class ScrollableComboBox(QWidget):
    currentIndexChanged = pyqtSignal(int)
    clicked = pyqtSignal()
    wheelScrolledToIndex = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_index = -1
        self._count = 0
        self._text = ""
        self._items = []

        self._hovered = False
        self._pressed = False
        self._flyout_is_open = False
        self._auto_width = False

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._apply_debounced_index)
        self._pending_index = -1

        self.setFixedHeight(33)
        self.setMinimumWidth(0)
        self.setStyleSheet("background: transparent; border: none;")
        self.setProperty("class", "primary")
        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)
        self.setMouseTracking(True)
        self._pressed = False

    def setAutoWidthEnabled(self, enabled: bool):
        self._auto_width = bool(enabled)
        if self._auto_width:
            self._adjustWidthToContent()

    def _adjustWidthToContent(self):
        if not self._auto_width:
            return
        try:
            font = self.getItemFont()
        except Exception:
            font = QApplication.font(self)
        fm = QFontMetrics(font)
        text = self._text or ""

        needed = fm.horizontalAdvance(text) + 8 + 22 + 4
        needed = max(1, needed)
        try:
            self.setFixedWidth(int(needed))
        except Exception:
            self.setMinimumWidth(int(needed))

    def count(self):
        return self._count

    def currentIndex(self):
        return self._current_index

    def currentText(self):
        return self._text

    def setText(self, text: str):
        self._text = text
        self.update()
        self._adjustWidthToContent()

    def setCurrentIndex(self, index: int):
        if 0 <= index < self._count and index != self._current_index:
            self._current_index = index
            if 0 <= index < len(self._items):
                self._text = self._items[index]
            self.update()
            self._adjustWidthToContent()
            self.currentIndexChanged.emit(index)

    def _apply_debounced_index(self):
        if self._pending_index != -1 and self._pending_index != self.currentIndex():
            self.wheelScrolledToIndex.emit(self._pending_index)
        self._pending_index = -1

    def updateState(
        self, count: int, current_index: int, text: str = "", items: list = None
    ):
        self._count = count
        self._current_index = current_index
        if text:
            self._text = text
        if items is not None:
            self._items = items[:]
        self.update()
        self._adjustWidthToContent()

    def addItem(self, text: str):
        self._items.append(text)
        self._count = len(self._items)

    def clear(self):
        self._items.clear()
        self._count = 0
        self._current_index = -1
        self._text = ""
        self.update()
        self._adjustWidthToContent()

    def setHovered(self, hovered: bool):
        effective_hovered = hovered and not self._flyout_is_open

        if self._hovered != effective_hovered:
            self._hovered = effective_hovered
            self.update()

    def setFlyoutOpen(self, is_open: bool):
        if self._flyout_is_open != is_open:
            self._flyout_is_open = is_open

            should_be_hovered_now = self.rect().contains(self.mapFromGlobal(QCursor.pos()))

            if not is_open:
                self._pressed = False

            self.setHovered(should_be_hovered_now)

            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_dark = self.theme_manager.is_dark()

        if not self.isEnabled():
            bg_key = "button.primary.background"
            bg_color = QColor(self.theme_manager.get_color(bg_key))
            text_color = QColor(131, 131, 131) if not is_dark else QColor(161, 161, 161)
        elif self._pressed:
            bg_key = "button.primary.background.pressed"
            bg_color = QColor(self.theme_manager.get_color(bg_key))
            text_color = QColor(self.theme_manager.get_color("button.primary.text"))
        elif self._flyout_is_open:

            bg_key = "button.primary.background"
            bg_color = QColor(self.theme_manager.get_color(bg_key))
            text_color = QColor(self.theme_manager.get_color("button.primary.text"))
        elif self._hovered:
            bg_key = "button.primary.background.hover"
            bg_color = QColor(self.theme_manager.get_color(bg_key))
            text_color = QColor(self.theme_manager.get_color("button.primary.text"))
        else:
            bg_key = "button.primary.background"
            bg_color = QColor(self.theme_manager.get_color(bg_key))
            text_color = QColor(self.theme_manager.get_color("button.primary.text"))

        rect = self.rect()
        rectf = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rectf, 6, 6)

        thin = QColor(self.theme_manager.get_color("input.border.thin"))
        alpha = max(8, int(thin.alpha() * 0.33))
        thin.setAlpha(alpha)
        pen_border = QPen(thin)
        pen_border.setWidthF(0.66)
        pen_border.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, 6, 6)

        draw_bottom_underline(painter, rect, self.theme_manager, UnderlineConfig(alpha=255))

        painter.setPen(QPen(text_color))
        font = self.getItemFont()
        painter.setFont(font)
        fm = QFontMetrics(font)
        text = self._text
        text_rect = rect.adjusted(8, 0, -22, 0)
        elided_text = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, elided_text)

        arrow_rect = rect.adjusted(rect.width() - 18, 0, -6, 0)

        arrow_color = text_color
        painter.setPen(QPen(arrow_color, 1.5))
        center_x, center_y = arrow_rect.center().x(), arrow_rect.center().y()
        chevron_width, chevron_height = 4, 2
        p1 = QPoint(center_x - chevron_width, center_y - chevron_height // 2)
        p2 = QPoint(center_x, center_y + chevron_height)
        p3 = QPoint(center_x + chevron_width, center_y - chevron_height // 2)
        painter.drawPolyline(QPolygon([p1, p2, p3]))

    def enterEvent(self, event):
        self.setHovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setHovered(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if not self.isEnabled() or self.count() <= 1:
            event.ignore()
            return
        start_index = self._pending_index if self._debounce_timer.isActive() else self.currentIndex()

        delta = event.angleDelta().y()
        if delta > 0:
            new_index = (start_index - 1 + self.count()) % self.count()
        elif delta < 0:
            new_index = (start_index + 1) % self.count()
        else:
            return

        if new_index != start_index:
            self._pending_index = new_index
            if 0 <= new_index < len(self._items):
                self.setText(self._items[new_index])

            self._debounce_timer.start()
            event.accept()

    def getItemHeight(self) -> int:
        return self.height() - 2

    def getItemFont(self) -> QFont:
        base_font = QApplication.font(self)
        return QFont(base_font)

class MinimalistScrollBar(QScrollBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._hover_progress = 0.0
        self.animation = None
        self._idle_thickness = 4
        self._hover_thickness = 4
        self._idle_color = QColor()
        self._hover_color = QColor()
        self._update_colors()
        self.theme_manager.theme_changed.connect(self._update_colors)
        self._is_dragging_visual = False

    def setDraggingState(self, is_dragging: bool):
        self._is_dragging_visual = is_dragging

    def _update_colors(self):
        if self.theme_manager.is_dark():
            self._idle_color = QColor(255, 255, 255, 60)
            self._hover_color = self._idle_color
        else:
            self._idle_color = QColor(0, 0, 0, 70)
            self._hover_color = self._idle_color
        self.update()

    @pyqtProperty(float)
    def hoverProgress(self): return self._hover_progress
    @hoverProgress.setter
    def hoverProgress(self, value):
        self._hover_progress = 0.0

    def enterEvent(self, event):
        super().enterEvent(event)

    def leaveEvent(self, event):
        super().leaveEvent(event)

    def paintEvent(self, event):
        if self.minimum() == self.maximum(): return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        handle_rect = self._get_handle_rect()
        if handle_rect.isEmpty(): return
        current_color = self._idle_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(current_color)
        radius = handle_rect.width() // 2
        painter.drawRoundedRect(handle_rect, radius, radius)

    def _get_handle_rect(self):
        if self.minimum() == self.maximum(): return QRect()
        current_thickness = self._idle_thickness
        v_padding = 8
        groove_height = self.height() - v_padding * 2
        total_range = self.maximum() - self.minimum() + self.pageStep()
        if total_range <= 0 or groove_height <= 0: return QRect()
        handle_height = max((self.pageStep() / total_range) * groove_height, 20)
        scroll_range = self.maximum() - self.minimum()
        track_height = groove_height - handle_height
        handle_y_relative = ((self.value() - self.minimum()) / scroll_range * track_height if scroll_range > 0 else 0)
        handle_y = handle_y_relative + v_padding
        handle_x = (self.width() - current_thickness) // 2
        return QRect(handle_x, int(handle_y), current_thickness, int(handle_height))

    def mousePressEvent(self, event: QMouseEvent):
        event.ignore()

class OverlayScrollArea(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.custom_v_scrollbar = MinimalistScrollBar(self)

        self.verticalScrollBar().valueChanged.connect(self.custom_v_scrollbar.setValue)
        self.custom_v_scrollbar.valueChanged.connect(self.verticalScrollBar().setValue)

        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)

        self.custom_v_scrollbar.setVisible(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self):
        if self.widget():
            content_height = self.widget().height()
            viewport_height = self.viewport().height()
            self.custom_v_scrollbar.setVisible(content_height > viewport_height)

    def _position_scrollbar(self):
        width = 14
        self.custom_v_scrollbar.setGeometry(
            self.width() - width, 0, width, self.height()
        )
        self.custom_v_scrollbar.raise_()

class RatingListItem(QWidget):
    itemSelected = pyqtSignal(int)
    itemRightClicked = pyqtSignal(int)

    def __init__(
        self,
        index,
        text,
        rating,
        full_path: str,
        app_ref,
        owner_flyout,
        parent,
        is_current: bool = False,
        item_height: int = 36,
        item_font: QFont = None,
    ):
        super().__init__(parent=parent)

        self.index = index
        self.full_path = full_path
        self.app_ref = app_ref
        self.owner_flyout = owner_flyout
        self.is_current = is_current
        self.setMinimumHeight(item_height)
        self.setFixedHeight(item_height)
        self.setMouseTracking(True)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update_styles)

        self.drag_start_pos = QPoint()
        self._drag_start_pos_global = QPointF()
        self._is_being_dragged = False

        self.tooltip_timer = QTimer(self)
        self.tooltip_timer.setSingleShot(True)
        self.tooltip_timer.setInterval(500)
        self.tooltip_timer.timeout.connect(self._show_tooltip)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(8, 3, 8, 3)
        self.layout.setSpacing(8)

        self.rating_label = QLabel(str(rating), self)
        self.rating_label.setFixedWidth(25)
        self.rating_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rating_label.setObjectName("ratingLabel")

        self.name_label = QLabel(text, self)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        base_font = item_font if item_font else QApplication.font(self)
        self.name_label.setFont(base_font)

        base_px = base_font.pixelSize()
        if base_px <= 0:
            base_px = QFontMetrics(base_font).height()
        rating_font = QFont(base_font)
        rating_font.setPixelSize(max(8, base_px - 3))
        self.rating_label.setFont(rating_font)

        self.btn_minus = AutoRepeatButton(get_icon(AppIcon.REMOVE), self)
        self.btn_plus = AutoRepeatButton(get_icon(AppIcon.ADD), self)
        for btn in [self.btn_minus, self.btn_plus]:
            btn.setFixedSize(22, 22)

        self.btn_minus.setStyleSheet(
            "ToolButton { qproperty-iconSize: 9px; border-radius: 11px; padding: 0px; }"
        )
        self.btn_plus.setStyleSheet(
            "ToolButton { qproperty-iconSize: 9px; border-radius: 11px; padding: 0px; margin-top: -1px; }"
        )

        self.layout.addWidget(self.rating_label)
        self.layout.addWidget(self.name_label, 1)
        self.layout.addWidget(self.btn_minus)
        self.layout.addWidget(self.btn_plus)

        self.btn_plus.clicked.connect(self._on_plus_clicked)
        self.btn_minus.clicked.connect(self._on_minus_clicked)

        self._active_button = None
        self._is_drag_initiated = False
        self._gesture_tx: RatingGestureTransaction | None = None

        try:
            self.btn_plus.installEventFilter(self)
            self.btn_minus.installEventFilter(self)
        except Exception:
            pass

        self.update_styles()

    def set_dragging_state(self, is_dragging: bool):
        if self._is_being_dragged != is_dragging:
            self._is_being_dragged = is_dragging
            self.update()

    def eventFilter(self, obj, event):
        if obj in (self.btn_plus, self.btn_minus):
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:

                self._active_button = obj

                self.drag_start_pos = self.mapFromGlobal(event.globalPosition().toPoint())
                self._drag_start_pos_global = event.globalPosition()

                image_number = self.owner_flyout.image_number
                target_list = (
                    self.app_ref.app_state.image_list1
                    if image_number == 1
                    else self.app_ref.app_state.image_list2
                )
                starting_score = 0
                if 0 <= self.index < len(target_list):
                    starting_score = target_list[self.index][3]
                self._gesture_tx = RatingGestureTransaction(
                    main_controller=self.app_ref.main_controller,
                    image_number=image_number,
                    item_index=self.index,
                    starting_score=starting_score,
                )
            elif event.type() == QEvent.Type.MouseMove and (event.buttons() & Qt.MouseButton.LeftButton):

                if self._active_button is obj and not self._is_drag_initiated:
                    try:
                        obj._initial_delay_timer.stop()
                        obj._repeat_timer.stop()
                    except Exception:
                        pass
                    distance = (event.globalPosition() - self._drag_start_pos_global).manhattanLength()
                    if distance >= QApplication.startDragDistance():
                        if self._gesture_tx is not None:
                            self._gesture_tx.rollback()
                            self._gesture_tx = None

            elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:

                if self._gesture_tx is not None and not self._is_drag_initiated:
                    self._gesture_tx.commit()
                    self._gesture_tx = None

        return super().eventFilter(obj, event)

    def update_styles(self):

        self.btn_minus.setIcon(get_icon(AppIcon.REMOVE))
        self.btn_plus.setIcon(get_icon(AppIcon.ADD))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = self.theme_manager

        if self._is_being_dragged:
            painter.setOpacity(0.35)

        under_mouse = self.underMouse()

        if self.is_current or under_mouse:
            bg_color = tm.get_color("list_item.background.hover")
        else:
            bg_color = tm.get_color("list_item.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        background_rect = self.rect().adjusted(2, 2, -2, -2)
        painter.drawRoundedRect(background_rect, 5, 5)

        if self.is_current:
            indicator_pen = QPen(tm.get_color("accent"))
            indicator_pen.setWidth(3)
            indicator_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(indicator_pen)
            y1, y2 = self.rect().top() + 7, self.rect().bottom() - 7
            x = self.rect().left() + indicator_pen.width()
            painter.drawLine(x, y1, x, y2)

        separator_color = tm.get_color("separator.color")
        painter.setPen(QPen(separator_color, 1))
        x_pos = self.rating_label.geometry().right() + self.layout.spacing() // 2
        painter.drawLine(x_pos, 6, x_pos, self.height() - 6)

        if self._is_being_dragged:
            painter.setOpacity(1.0)

    def enterEvent(self, event):
        self.tooltip_timer.start()
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        self.tooltip_timer.stop()
        PathTooltip.get_instance().hide_tooltip()

        if event.button() == Qt.MouseButton.LeftButton:

            is_on_plus = self.btn_plus.geometry().contains(event.pos())
            is_on_minus = self.btn_minus.geometry().contains(event.pos())

            if not is_on_plus and not is_on_minus:

                self._active_button = None

            self.drag_start_pos = event.pos()

            image_number = self.owner_flyout.image_number
            target_list = (
                self.app_ref.app_state.image_list1
                if image_number == 1
                else self.app_ref.app_state.image_list2
            )
            current_rating = 0
            if 0 <= self.index < len(target_list):
                current_rating = target_list[self.index][3]

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or self._is_drag_initiated:
            return

        current_global_pos = self.mapToGlobal(event.pos())
        start_global_pos = self.mapToGlobal(self.drag_start_pos)
        distance = (current_global_pos - start_global_pos).manhattanLength()

        if distance >= QApplication.startDragDistance():
            if self._active_button:
                try:
                    self._active_button._initial_delay_timer.stop()
                    self._active_button._repeat_timer.stop()
                except Exception:
                    pass

                if self._gesture_tx is not None:
                    self._gesture_tx.rollback()
                    self._gesture_tx = None
            self.tooltip_timer.stop()
            PathTooltip.get_instance().hide_tooltip()

            self._is_drag_initiated = True
            service = DragAndDropService.get_instance()
            if not service.is_dragging():
                service.start_drag(self, event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self._is_drag_initiated:
            if self.rect().contains(event.pos()):
                if event.button() == Qt.MouseButton.LeftButton:
                    is_on_plus = self.btn_plus.geometry().contains(event.pos())
                    is_on_minus = self.btn_minus.geometry().contains(event.pos())
                    if not is_on_plus and not is_on_minus:
                        self.itemSelected.emit(self.index)
                elif event.button() == Qt.MouseButton.RightButton:
                    self.itemRightClicked.emit(self.index)

        if self._gesture_tx is not None:
            self._gesture_tx.commit()
            self._gesture_tx = None
        image_number = self.owner_flyout.image_number
        target_list = (
            self.app_ref.app_state.image_list1
            if image_number == 1
            else self.app_ref.app_state.image_list2
        )
        current_rating = 0
        if 0 <= self.index < len(target_list):
            current_rating = target_list[self.index][3]

        self._is_drag_initiated = False
        self._active_button = None
        super().mouseReleaseEvent(event)

    def _on_plus_clicked(self):
        if self._is_drag_initiated:
             return

        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(+1)
        else:

            self.app_ref.main_controller.increment_rating(self.owner_flyout.image_number, self.index)

        image_number = self.owner_flyout.image_number
        target_list = (
            self.app_ref.app_state.image_list1
            if image_number == 1
            else self.app_ref.app_state.image_list2
        )
        if 0 <= self.index < len(target_list):
            new_rating = target_list[self.index][3]
            self.rating_label.setText(str(new_rating))

    def _on_minus_clicked(self):
        if self._is_drag_initiated:
             return

        if self._gesture_tx is not None:
            self._gesture_tx.apply_delta(-1)
        else:
            self.app_ref.main_controller.decrement_rating(self.owner_flyout.image_number, self.index)

        image_number = self.owner_flyout.image_number
        target_list = (
            self.app_ref.app_state.image_list1
            if image_number == 1
            else self.app_ref.app_state.image_list2
        )
        if 0 <= self.index < len(target_list):
            new_rating = target_list[self.index][3]
            self.rating_label.setText(str(new_rating))

    def _show_tooltip(self):
        PathTooltip.get_instance().show_tooltip(self.mapToGlobal(self.rect().center()), self.full_path)

class _FlyoutInnerContentWidget(QWidget):

    def __init__(self, owner_flyout, parent=None):
        super().__init__(parent)
        self.owner_flyout = owner_flyout

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.owner_flyout.drop_indicator_y >= 0:
            painter = QPainter(self)
            pen_color = self.owner_flyout.theme_manager.get_color("accent")
            pen = QPen(pen_color, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawLine(8, self.owner_flyout.drop_indicator_y, self.width() - 8, self.owner_flyout.drop_indicator_y)

class FlyoutContentWidget(QWidget):
    item_chosen = pyqtSignal(int)
    closing_animation_finished = pyqtSignal()

    SHADOW_RADIUS = 10
    MARGIN = 8

    def __init__(self, app_ref):
        super().__init__(None)
        self.app_ref = app_ref
        self.image_number = -1
        self.item_height = 36
        self.item_font = QFont(QApplication.font(self))
        self._is_closing = False
        self.selected_index_to_apply = -1
        self.drop_indicator_y = -1

        if sys.platform in ('linux', 'darwin'):
            window_flags = Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        else:
            window_flags = Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint

        self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.container_widget = QWidget(self)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(self.SHADOW_RADIUS)
        shadow.setOffset(1, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container_widget.setGraphicsEffect(shadow)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(
            self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN
        )
        self.main_layout.addWidget(self.container_widget)

        container_layout = QVBoxLayout(self.container_widget)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(0)

        self.scroll_area = OverlayScrollArea(self.container_widget)
        container_layout.addWidget(self.scroll_area)

        self.theme_manager = ThemeManager.get_instance()

        self.content_widget = _FlyoutInnerContentWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.scroll_area.setWidget(self.content_widget)

        DragAndDropService.get_instance().register_drop_target(self)
        self.theme_manager.theme_changed.connect(self._update_style)
        self._update_style()
        self.hide()

    def _on_destroyed(self):
        if DragAndDropService._instance is not None:
            try:
                DragAndDropService.get_instance().unregister_drop_target(self)
            except Exception as e:
                pass
    def can_accept_drop(self, payload: dict) -> bool:
        if not payload:
            return False
        return payload.get('list_num') == self.image_number

    def _find_drop_target(self, local_pos_y: int) -> tuple[int, int]:
        service = DragAndDropService.get_instance()
        source_widget = service._source_widget

        if self.content_layout.count() <= 1 and source_widget:
            return 0, 0

        closest_item = None
        min_distance = float('inf')

        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i).widget()
            if not item or item is source_widget:
                continue

            item_mid_y = item.y() + item.height() / 2
            distance = abs(local_pos_y - item_mid_y)

            if distance < min_distance:
                min_distance = distance
                closest_item = item

        if closest_item is None:
             return 0, 0

        closest_item_mid_y = closest_item.y() + closest_item.height() / 2

        closest_visual_index = self.content_layout.indexOf(closest_item)

        if local_pos_y < closest_item_mid_y:
            return closest_visual_index, closest_item.y()
        else:
            return closest_visual_index + 1, closest_item.y() + closest_item.height()

    def update_drop_indicator(self, global_pos: QPointF):
        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())

        _, indicator_y = self._find_drop_target(local_pos.y())

        if self.drop_indicator_y != indicator_y:
            self.drop_indicator_y = indicator_y
            self.content_widget.update()

    def clear_drop_indicator(self):
        if self.drop_indicator_y != -1:
            self.drop_indicator_y = -1
            self.content_widget.update()

    def handle_drop(self, payload: dict, global_pos: QPointF):
        self.clear_drop_indicator()

        source_list_num = payload.get('list_num', -1)
        source_index = payload.get('index', -1)
        if source_index == -1 or source_list_num == -1:
            return

        local_pos = self.content_widget.mapFromGlobal(global_pos.toPoint())

        dest_index, _ = self._find_drop_target(local_pos.y())

        if source_list_num == self.image_number:
            QTimer.singleShot(0, lambda: self.app_ref.main_controller.reorder_item_in_list(
                image_number=self.image_number,
                source_index=source_index,
                dest_index=dest_index
            ))
        else:
            QTimer.singleShot(0, lambda: self.app_ref.main_controller.move_item_between_lists(
                source_list_num=source_list_num,
                source_index=source_index,
                dest_list_num=self.image_number,
                dest_index=dest_index
            ))

    def _update_style(self):
        tm = self.theme_manager
        bg_color = tm.get_color("flyout.background").name(QColor.NameFormat.HexArgb)
        border_color = tm.get_color("flyout.border").name(QColor.NameFormat.HexArgb)
        border_radius = 8
        self.container_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {border_radius}px;
            }}
        """)
        self.scroll_area.setStyleSheet("background-color: transparent; border: none;")
        self.content_widget.setStyleSheet("background: transparent;")

    def repopulate_from_state(self):
        image_list = self.app_ref.app_state.image_list1 if self.image_number == 1 else self.app_ref.app_state.image_list2
        self._clear_layout_and_rebuild(image_list)

    def populate(self, image_list, content_width: int):
        self.container_widget.setFixedWidth(content_width)
        self._clear_layout_and_rebuild(image_list)

    def _clear_layout_and_rebuild(self, image_list):
        PathTooltip.get_instance().hide_tooltip()
        while item := self.content_layout.takeAt(0):
            if widget := item.widget():
                widget.deleteLater()

        current_app_index = (
            self.app_ref.app_state.current_index1
            if self.image_number == 1
            else self.app_ref.app_state.current_index2
        )

        for i, item_data in enumerate(image_list):
            full_path, name, rating = (
                item_data[1], item_data[2] or "-----", item_data[3],
            )
            list_item_widget = RatingListItem(
                index=i, text=name, rating=rating, full_path=full_path,
                app_ref=self.app_ref, owner_flyout=self, parent=self.content_widget,
                is_current=(i == current_app_index), item_height=self.item_height,
                item_font=self.item_font,
            )
            list_item_widget.itemSelected.connect(
                lambda idx=i: self.item_chosen.emit(idx)
            )
            list_item_widget.itemRightClicked.connect(self._on_item_right_clicked)
            self.content_layout.addWidget(list_item_widget)

        QTimer.singleShot(0, self._update_flyout_size)

    def update_current_selection(self, new_index: int):
        for i in range(self.content_layout.count()):
            item = self.content_layout.itemAt(i).widget()
            if isinstance(item, RatingListItem):
                is_now_current = item.index == new_index
                if item.is_current != is_now_current:
                    item.is_current = is_now_current
                    item.update()

    def start_closing_animation(self):
        PathTooltip.get_instance().hide_tooltip()
        if self._is_closing or not self.isVisible():
            return
        self._is_closing = True
        self.hide()
        self.closing_animation_finished.emit()

    def hideEvent(self, event):
        PathTooltip.get_instance().hide_tooltip()
        super().hideEvent(event)

    def _on_item_right_clicked(self, index: int):
        self.app_ref.main_controller.remove_specific_image_from_list(self.image_number, index)

        updated_list = self.app_ref.app_state.image_list1 if self.image_number == 1 else self.app_ref.app_state.image_list2

        if not updated_list:
            self.start_closing_animation()
            return

        self.populate(updated_list, self.container_widget.width())

    def _update_flyout_size(self):
        num_items = self.content_layout.count()
        if num_items == 0 and self.isVisible():
             self.hide()
             return

        spacing = self.content_layout.spacing()
        content_height = num_items * self.item_height + max(0, num_items - 1) * spacing

        max_items_visible = 7.5
        max_content_height = int(max_items_visible * self.item_height)

        target_content_height = min(content_height, max_content_height)

        container_height = target_content_height + 4 + 4
        self.container_widget.setFixedHeight(container_height)

        self.setFixedHeight(container_height + self.MARGIN * 2)

        QTimer.singleShot(0, self._check_scrollbar_visibility)

    def _check_scrollbar_visibility(self):
        if not self.isVisible(): return
        content_height_actual = self.content_widget.sizeHint().height()
        viewport_height_actual = self.scroll_area.viewport().height()
        is_needed = content_height_actual > viewport_height_actual
        self.scroll_area.custom_v_scrollbar.setVisible(is_needed)
