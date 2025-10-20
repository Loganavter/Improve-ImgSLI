import logging
from enum import Enum

from PyQt6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygon,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollBar,
    QSizePolicy,
    QWidget,
)

from events.drag_drop_handler import DragAndDropService
from resources import translations as translations_mod
from src.shared_toolkit.ui.managers.theme_manager import ThemeManager
from src.shared_toolkit.ui.widgets.helpers.underline_painter import (
    UnderlineConfig,
    draw_bottom_underline,
)
from ui.gesture_resolver import RatingGestureTransaction
from src.shared_toolkit.ui.managers.icon_manager import AppIcon, get_app_icon
from ui.widgets import ToolButton

tr = getattr(translations_mod, "tr", lambda text, lang="en", *args, **kwargs: text)

logger = logging.getLogger("ImproveImgSLI")

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
    def _style_prefix(self) -> str:
        """Возвращает префикс для ключей стиля в зависимости от класса виджета."""
        btn_class = str(self.property("class") or "")
        return "button.primary" if "primary" in btn_class else "button.default"
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

        prefix = self._style_prefix()
        border_color = QColor(self.theme_manager.get_color(f"{prefix}.border"))
        pen_border = QPen(border_color)
        pen_border.setWidthF(1.0)
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

        self.style().unpolish(self)
        self.style().polish(self)
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

        self.setToolTip(full_path)

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

        self.btn_minus = AutoRepeatButton(get_app_icon(AppIcon.REMOVE), self)
        self.btn_plus = AutoRepeatButton(get_app_icon(AppIcon.ADD), self)
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

        self.style().unpolish(self)
        self.style().polish(self)
        self.btn_minus.setIcon(get_app_icon(AppIcon.REMOVE))
        self.btn_plus.setIcon(get_app_icon(AppIcon.ADD))
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
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):

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
