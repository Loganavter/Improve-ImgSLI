"""Dropdown menu widget used by Button when menu mode is active."""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QEvent, QPoint, QPropertyAnimation, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.in_window_surface import (
    attach_in_window_widget,
    paint_shadowed_surface,
)

class _MenuItem(QWidget):
    clicked = pyqtSignal()

    def __init__(self, text: str, is_current: bool, parent=None):
        super().__init__(parent)
        self._text = text
        self._is_current = is_current
        self._hovered = False
        self._check_icon = None
        self._foreground_color = None
        self.setFixedHeight(40)
        self.setMouseTracking(True)
        if is_current:
            self._check_icon = resolve_icon("check").pixmap(20, 20)

    def event(self, event):
        if event.type() == QEvent.Type.DynamicPropertyChange:
            if event.propertyName().data().decode("utf-8", errors="ignore") == "foregroundColor":
                self._foreground_color = self.property("foregroundColor") or self._foreground_color
                self.update()
        return super().event(event)

    def set_current(self, is_current: bool):
        self._is_current = is_current
        self._check_icon = resolve_icon("check").pixmap(20, 20) if is_current else None
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
        bg_color = tm.get_color("list_item.background.hover" if (self._is_current or self._hovered) else "list_item.background.normal")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(self.rect().adjusted(2, 2, -2, -2), 4, 4)
        text_color = self._foreground_color or tm.get_color("dialog.text")
        if self._check_icon:
            icon_rect = QRect(10, (self.height() - 20) // 2, 20, 20)
            painter.drawPixmap(icon_rect, self._check_icon)
        painter.setPen(QPen(text_color))
        painter.setFont(self.font())
        text_x = 40 if self._check_icon else 12
        text_y = self.rect().center().y() + 5
        painter.drawText(text_x, text_y, self._text)

class DropdownMenu(QWidget):
    item_selected = pyqtSignal(QAction)

    MARGIN = 8
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 8
    DROP_OFFSET_PX = 80
    APPEAR_EXTRA_Y = 6
    _move_duration_ms = 240
    _move_easing = QEasingCurve.Type.OutQuad

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner_button = parent
        self._actions = []
        self._menu_items = []
        self._current_index = -1
        self._anim = None
        self.overlay_layer = attach_in_window_widget(self, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(8, 8, 8, 8)
        self.container_widget = QWidget(self)
        self.container_widget.setObjectName("menuContainer")
        self.container_widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.main_layout.addWidget(self.container_widget)
        self.container_layout = QVBoxLayout(self.container_widget)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(2)
        self.content_widget = QWidget(self.container_widget)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.container_layout.addWidget(self.content_widget)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        paint_shadowed_surface(
            painter,
            self.container_widget.geometry(),
            shadow_radius=self.SHADOW_RADIUS,
            corner_radius=self.CONTENT_RADIUS,
        )
        painter.end()

    def _ensure_overlay_parent(self, anchor_widget: QWidget):
        if self.overlay_layer is None:
            self.overlay_layer = attach_in_window_widget(self, anchor_widget)
        if self.overlay_layer is not None and self.parentWidget() is not self.overlay_layer.host:
            was_visible = self.isVisible()
            self.overlay_layer.attach(self)
            if was_visible:
                self.show()
                self.raise_()

    def set_actions(self, actions: list[tuple[str, any]]):
        self._actions = actions
        self._current_index = -1

    def set_current_by_data(self, data: any):
        for i, (_, action_data) in enumerate(self._actions):
            if action_data == data:
                self._current_index = i
                break

    def show_for_anchor(self, anchor_widget: QWidget):
        self._ensure_overlay_parent(anchor_widget)
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
            item.clicked.connect(lambda checked=False, idx=i: self._on_item_clicked(idx))
            self._menu_items.append(item)
            self.content_layout.addWidget(item)
            fm = item.fontMetrics()
            max_width = max(max_width, fm.boundingRect(text).width() + 60)
        item_height = 40
        content_height = len(self._actions) * item_height + max(0, len(self._actions) - 1) * self.content_layout.spacing()
        container_height = content_height + 8
        self.container_widget.setFixedSize(max_width, container_height)
        self.setFixedSize(max_width + 16, container_height + 16)
        use_overlay_coords = self.overlay_layer is not None
        anchor_rect = self.overlay_layer.anchor_rect(anchor_widget) if use_overlay_coords else QRect(anchor_widget.mapToGlobal(QPoint(0, 0)), anchor_widget.size())
        final_pos = QPoint(anchor_rect.x() - 8, anchor_rect.bottom() - 4 + self.APPEAR_EXTRA_Y)
        start_pos = QPoint(final_pos.x(), final_pos.y() - self.DROP_OFFSET_PX)
        if use_overlay_coords:
            final_rect = self.overlay_layer.clamp_rect(QRect(final_pos, QSize(max_width + 16, container_height + 16)))
            final_pos = final_rect.topLeft()
            start_pos = QPoint(final_pos.x(), final_pos.y() - self.DROP_OFFSET_PX)
        else:
            try:
                screen = QGuiApplication.screenAt(anchor_widget.mapToGlobal(QPoint(0, 0)))
                if screen:
                    avail = screen.availableGeometry()
                    final_pos.setX(max(avail.left(), min(final_pos.x(), avail.right() - (max_width + 16))))
                    final_pos.setY(max(avail.top(), min(final_pos.y(), avail.bottom() - (container_height + 16))))
                    start_pos = QPoint(final_pos.x(), final_pos.y() - self.DROP_OFFSET_PX)
            except Exception:
                pass
        self.move(start_pos)
        self.show()
        self.raise_()
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
            self._current_index = index
            _, data = self._actions[index]
            action = QAction(self)
            action.setData(data)
            self.item_selected.emit(action)
        self.hide()

    def hideEvent(self, event):
        if self._anim:
            self._anim.stop()
        if self._owner_button is not None and hasattr(self._owner_button, "_menu_visible"):
            self._owner_button._menu_visible = False
        super().hideEvent(event)
