from PyQt6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QGuiApplication, QIcon, QPainter, QBrush, QPen, QColor
from PyQt6.QtWidgets import QWidget, QGraphicsDropShadowEffect, QVBoxLayout

from core.constants import AppConstants
from toolkit.managers.theme_manager import ThemeManager
from ui.icon_manager import AppIcon, get_app_icon

class _MenuItem(QWidget):
    clicked = pyqtSignal()

    def __init__(self, text: str, is_current: bool, parent=None):
        super().__init__(parent)
        self._text = text
        self._is_current = is_current
        self._hovered = False
        self._check_icon = None

        self.setFixedHeight(40)
        self.setMouseTracking(True)

        if is_current:
            check_icon = get_app_icon(AppIcon.CHECK)
            self._check_icon = check_icon.pixmap(20, 20)

    def set_current(self, is_current: bool):
        self._is_current = is_current
        if is_current:
            check_icon = get_app_icon(AppIcon.CHECK)
            self._check_icon = check_icon.pixmap(20, 20)
        else:
            self._check_icon = None
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = ThemeManager.get_instance()

        if self._is_current:
            bg_color = tm.get_color("list_item.background.hover")
        elif self._hovered:
            bg_color = tm.get_color("list_item.background.hover")
        else:
            bg_color = tm.get_color("list_item.background.normal")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 4, 4)

        text_color = tm.get_color("dialog.text")

        if self._check_icon:
            icon_rect = QRect(10, (self.height() - 20) // 2, 20, 20)
            painter.drawPixmap(icon_rect, self._check_icon)

        painter.setPen(QPen(text_color))
        painter.setFont(self.font())

        text_x = 40 if self._check_icon else 12
        text_y = self.rect().center().y() + 5

        painter.drawText(text_x, text_y, self._text)

class _DropdownMenu(QWidget):
    item_selected = pyqtSignal(QAction)

    MARGIN = 8
    DROP_OFFSET_PX = 80
    APPEAR_EXTRA_Y = 6
    _move_duration_ms = AppConstants.FLYOUT_ANIMATION_DURATION_MS
    _move_easing = QEasingCurve.Type.OutQuad

    def __init__(self, parent=None):
        super().__init__(parent)
        self._actions = []
        self._menu_items = []
        self._current_index = -1
        self._anim = None

        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)

        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("menuContainer")

        shadow = QGraphicsDropShadowEffect(self.container_widget)
        shadow.setBlurRadius(10)
        shadow.setOffset(1, 2)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container_widget.setGraphicsEffect(shadow)

        self.main_layout.addWidget(self.container_widget)

        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(2)

        self.content_widget = QWidget(self.container_widget)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.container_layout.addWidget(self.content_widget)

        self._apply_style()

    def set_actions(self, actions: list[tuple[str, any]]):
        self._actions = actions
        self._current_index = -1

    def set_current_by_data(self, data: any):
        for i, (_, action_data) in enumerate(self._actions):
            if action_data == data:
                self._current_index = i
                break

    def show_at(self, pos: QPoint):
        if not self._actions:
            return

        if self._anim:
            self._anim.stop()

        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._menu_items.clear()

        max_width = 180
        for i, (text, data) in enumerate(self._actions):
            item = _MenuItem(text, i == self._current_index, self.content_widget)
            item.set_current(i == self._current_index)
            item.clicked.connect(lambda checked=False, idx=i: self._on_item_clicked(idx))
            self._menu_items.append(item)
            self.content_layout.addWidget(item)

            fm = item.fontMetrics()
            text_width = fm.boundingRect(text).width()
            max_width = max(max_width, text_width + 60)

        item_height = 40
        content_height = len(self._actions) * item_height + max(0, len(self._actions) - 1) * self.content_layout.spacing()
        container_height = content_height + 8

        self.container_widget.setFixedSize(max_width, container_height)
        self.setFixedSize(max_width + 16, container_height + 16)

        final_pos = QPoint(pos.x(), pos.y() + self.APPEAR_EXTRA_Y)
        start_pos = QPoint(final_pos.x(), final_pos.y() - self.DROP_OFFSET_PX)

        try:
            screen = QGuiApplication.screenAt(pos)
            if screen:
                avail = screen.availableGeometry()
                final_pos.setX(max(avail.left(), min(final_pos.x(), avail.right() - (max_width + 16))))
                final_pos.setY(max(avail.top(), min(final_pos.y(), avail.bottom() - (container_height + 16))))
                start_pos = QPoint(final_pos.x(), final_pos.y() - self.DROP_OFFSET_PX)
        except Exception:
            pass

        self.move(start_pos)
        self.show()

        anim_pos = QPropertyAnimation(self, b"pos", self)
        anim_pos.setDuration(self._move_duration_ms)
        anim_pos.setStartValue(start_pos)
        anim_pos.setEndValue(final_pos)
        anim_pos.setEasingCurve(self._move_easing)
        anim_pos.finished.connect(self._on_animation_finished)

        self._anim = anim_pos
        anim_pos.start()

    def _on_animation_finished(self):
        if self._anim:
            anim_obj = self._anim
            self._anim = None
            anim_obj.deleteLater()

    def _on_item_clicked(self, index: int):
        if 0 <= index < len(self._actions):
            _, data = self._actions[index]
            action = QAction(self)
            action.setData(data)
            self.item_selected.emit(action)
        self.hide()

    def _apply_style(self):

        pass

    def hideEvent(self, event):
        if self._anim:
            self._anim.stop()

        if self.parent() and hasattr(self.parent(), '_menu_visible'):
            self.parent()._menu_visible = False
        super().hideEvent(event)

class ToolButtonWithMenu(QWidget):
    triggered = pyqtSignal(QAction)

    def __init__(self, icon: AppIcon, parent=None):
        super().__init__(parent)
        self._icon = icon
        self._actions = []
        self._current_action = None
        self._hovered = False
        self._pressed = False
        self._menu_visible = False

        self.setFixedSize(36, 36)

        self.menu = _DropdownMenu(self)
        self.menu.item_selected.connect(self._on_action_triggered)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self.update)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.pos()):
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.show_menu()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tm = self.theme_manager

        if self._pressed:
            bg_color = tm.get_color("button.toggle.background.pressed")
        elif self._hovered:
            bg_color = tm.get_color("button.toggle.background.hover")
        else:
            bg_color = tm.get_color("button.toggle.background.normal")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(self.rect(), 6, 6)

        icon = get_app_icon(self._icon)
        icon_size = int(self.width() * 0.6)
        icon_rect = QRect(
            (self.width() - icon_size) // 2,
            (self.height() - icon_size) // 2,
            icon_size,
            icon_size
        )
        painter.drawPixmap(icon_rect, icon.pixmap(icon_size, icon_size))

    def set_actions(self, actions: list[tuple[str, any]]):
        self._actions = actions
        self.menu.set_actions(actions)

    def set_current_by_data(self, data: any):
        for text, action_data in self._actions:
            if action_data == data:

                for i, (t, d) in enumerate(self._actions):
                    if d == data:
                        self._current_action = (text, data)
                        self.menu.set_current_by_data(data)
                        break
                break

    def show_menu(self):
        if not self._actions:
            return

        offset = QPoint(-8, self.height() - 4)
        global_pos = self.mapToGlobal(offset)

        self._menu_visible = True
        self.menu.show_at(global_pos)

    def _on_action_triggered(self, action: QAction):
        self.set_current_by_data(action.data())
        self.triggered.emit(action)

    def hide_menu(self):
        if self._menu_visible:
            self._menu_visible = False
            self.menu.hide()

    def is_menu_visible(self):
        return self._menu_visible

