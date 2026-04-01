from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from PyQt6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from ...managers.theme_manager import ThemeManager
from .minimalist_scrollbar import MinimalistScrollBar
from ..helpers import (
    UnderlineConfig,
    calculate_centered_overlay_geometry,
    draw_bottom_underline,
    draw_rounded_shadow,
)

logger = logging.getLogger("ImproveImgSLI")

@dataclass
class _ComboItem:
    text: str
    data: Any = None

class _DropdownOverlay(QWidget):
    RADIUS = 8
    SHADOW = 10
    GAP = 6

    def __init__(self, owner: "FluentComboBox", parent: QWidget):
        super().__init__(parent)
        self._owner = owner
        self._theme = owner._theme
        self._hovered_row = -1
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = 10
        self._scrollbar_gap = 0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMouseTracking(True)
        self.custom_v_scrollbar.valueChanged.connect(self._on_scrollbar_value_changed)
        self.custom_v_scrollbar.setVisible(False)
        self.hide()

    def _item_height(self) -> int:
        return self._owner._item_height()

    def _visible_items(self) -> int:
        return self._owner._visible_items()

    def _list_height(self) -> int:
        return self._visible_items() * self._item_height()

    def _content_rect(self) -> QRect:
        return self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)

    def _has_scrollbar(self) -> bool:
        return self._owner.count() > self._owner.maxVisibleItems()

    def _list_rect(self) -> QRect:
        width = self._content_rect().width()
        if self._has_scrollbar():
            width -= self._scrollbar_width + self._scrollbar_gap
        return QRect(0, 0, max(0, width), self._list_height())

    def _item_rect(self, visible_index: int) -> QRect:
        list_rect = self._list_rect()
        return QRect(
            list_rect.x(),
            list_rect.y() + visible_index * self._item_height(),
            list_rect.width(),
            self._item_height(),
        )

    def show_for_owner(self):
        self._hovered_row = -1
        self._owner._ensure_current_visible()
        self._reposition()
        self._sync_scrollbar()
        self.show()
        self.raise_()
        self.update()
        logger.debug(
            "[FluentComboBox.overlay.show] object=%s current=%d scroll_offset=%d visible=%d geom=(%d,%d,%d,%d)",
            self._owner.objectName() or "<unnamed>",
            self._owner.currentIndex(),
            self._owner._scroll_offset,
            self._visible_items(),
            self.x(),
            self.y(),
            self.width(),
            self.height(),
        )

    def _reposition(self):
        owner = self._owner
        window = self.parentWidget()
        if window is None:
            return

        outer = calculate_centered_overlay_geometry(
            anchor_widget=owner,
            owner_window=window,
            content_size=QSize(max(owner.width(), owner.minimumWidth()), self._list_height()),
            shadow_radius=self.SHADOW,
            current_index=owner.currentIndex(),
            visible_index=max(0, owner.currentIndex() - owner._scroll_offset),
            row_height=self._item_height(),
            scrollable=owner.count() > owner.maxVisibleItems(),
        )
        self.setGeometry(outer)
        self._position_scrollbar()

    def _position_scrollbar(self):
        content = self._content_rect()
        if not self._has_scrollbar():
            self.custom_v_scrollbar.setVisible(False)
            return
        x = content.right() - self._scrollbar_width + 1
        self.custom_v_scrollbar.setGeometry(
            x,
            content.y(),
            self._scrollbar_width,
            content.height(),
        )
        self.custom_v_scrollbar.raise_()

    def _sync_scrollbar(self):
        max_offset = max(0, self._owner.count() - self._visible_items())
        if max_offset <= 0:
            self.custom_v_scrollbar.setVisible(False)
            return
        self.custom_v_scrollbar.blockSignals(True)
        self.custom_v_scrollbar.setRange(0, max_offset)
        self.custom_v_scrollbar.setPageStep(self._visible_items())
        self.custom_v_scrollbar.setSingleStep(1)
        self.custom_v_scrollbar.setValue(self._owner._scroll_offset)
        self.custom_v_scrollbar.blockSignals(False)
        self.custom_v_scrollbar.setVisible(True)
        self._position_scrollbar()

    def _on_scrollbar_value_changed(self, value: int):
        new_offset = max(0, min(int(value), max(0, self._owner.count() - self._visible_items())))
        if new_offset == self._owner._scroll_offset:
            return
        self._owner._scroll_offset = new_offset
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbar()
        self._sync_scrollbar()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        content = QRectF(self._content_rect())
        draw_rounded_shadow(
            painter,
            content,
            steps=self.SHADOW,
            radius=self.RADIUS,
        )

        bg = self._theme.get_color("flyout.background")
        border = self._theme.get_color("flyout.border")
        hover_bg = self._theme.get_color("list_item.background.hover")
        text = self._theme.get_color("dialog.text")

        path = QPainterPath()
        path.addRoundedRect(content.adjusted(0.5, 0.5, -0.5, -0.5), self.RADIUS, self.RADIUS)
        painter.setPen(QPen(border))
        painter.setBrush(QBrush(bg))
        painter.drawPath(path)

        visible_count = self._visible_items()
        for visible_idx in range(visible_count):
            item_index = self._owner._scroll_offset + visible_idx
            if item_index >= self._owner.count():
                break

            item = self._owner._items[item_index]
            item_rect = QRectF(
                self._item_rect(visible_idx)
                .translated(self._content_rect().topLeft())
                .adjusted(0, 1, -1, -1)
            )
            if item_index == self._hovered_row:
                item_path = QPainterPath()
                item_path.addRoundedRect(item_rect, 6, 6)
                painter.fillPath(item_path, hover_bg)

            painter.setPen(QPen(text))
            painter.drawText(
                item_rect.adjusted(
                    self._owner.TEXT_HORIZONTAL_PADDING,
                    0,
                    -self._owner.TEXT_HORIZONTAL_PADDING,
                    0,
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(self.font()).elidedText(
                    item.text,
                    Qt.TextElideMode.ElideRight,
                    max(0, int(item_rect.width()) - self._owner.TEXT_HORIZONTAL_PADDING * 2),
                ),
            )

        painter.end()

    def mouseMoveEvent(self, event):
        if self.custom_v_scrollbar.isVisible() and self.custom_v_scrollbar.geometry().contains(
            event.position().toPoint()
        ):
            scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(
                event.globalPosition().toPoint()
            )
            QApplication.sendEvent(
                self.custom_v_scrollbar,
                QMouseEvent(
                    event.type(),
                    scrollbar_pos,
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                ),
            )
            event.accept()
            return
        self._hovered_row = -1
        local_pos = event.position().toPoint() - self._content_rect().topLeft()
        for visible_idx in range(self._visible_items()):
            item_index = self._owner._scroll_offset + visible_idx
            if item_index >= self._owner.count():
                break
            if self._item_rect(visible_idx).contains(local_pos):
                self._hovered_row = item_index
                break
        self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hovered_row = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self.custom_v_scrollbar.isVisible() and self.custom_v_scrollbar.geometry().contains(
            event.position().toPoint()
        ):
            scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(
                event.globalPosition().toPoint()
            )
            QApplication.sendEvent(
                self.custom_v_scrollbar,
                QMouseEvent(
                    event.type(),
                    scrollbar_pos,
                    event.globalPosition(),
                    event.button(),
                    event.buttons(),
                    event.modifiers(),
                ),
            )
            event.accept()
            return
        clicked_row = -1
        local_pos = event.position().toPoint() - self._content_rect().topLeft()
        for visible_idx in range(self._visible_items()):
            item_index = self._owner._scroll_offset + visible_idx
            if item_index >= self._owner.count():
                break
            if self._item_rect(visible_idx).contains(local_pos):
                clicked_row = item_index
                break

        logger.debug(
            "[FluentComboBox.overlay.click] object=%s local=(%d,%d) clicked_row=%d hovered_row=%d current=%d",
            self._owner.objectName() or "<unnamed>",
            local_pos.x(),
            local_pos.y(),
            clicked_row,
            self._hovered_row,
            self._owner.currentIndex(),
        )
        if clicked_row >= 0:
            self._owner.setCurrentIndex(clicked_row)
        self._owner.hideDropdown()
        event.accept()

    def wheelEvent(self, event):
        if self._owner.count() <= self._owner._max_visible_items:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._owner._scroll_offset = max(0, self._owner._scroll_offset - 1)
        elif delta < 0:
            self._owner._scroll_offset = min(
                self._owner.count() - self._owner._max_visible_items,
                self._owner._scroll_offset + 1,
            )
        self._sync_scrollbar()
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.custom_v_scrollbar.isVisible():
            if self.custom_v_scrollbar.geometry().contains(event.position().toPoint()):
                scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(
                    event.globalPosition().toPoint()
                )
                QApplication.sendEvent(
                    self.custom_v_scrollbar,
                    QMouseEvent(
                        event.type(),
                        scrollbar_pos,
                        event.globalPosition(),
                        event.button(),
                        event.buttons(),
                        event.modifiers(),
                    ),
                )
                event.accept()
                return
        super().mousePressEvent(event)

class FluentComboBox(QWidget):
    currentIndexChanged = pyqtSignal(int)
    currentTextChanged = pyqtSignal(str)

    BASE_HEIGHT = 33
    RADIUS = 6
    ITEM_VERTICAL_PADDING = 12
    TEXT_HORIZONTAL_PADDING = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme = ThemeManager.get_instance()
        self._items: list[_ComboItem] = []
        self._current_index = -1
        self._hovered = False
        self._pressed = False
        self._expanded = False
        self._max_visible_items = 12
        self._minimum_contents_length = 0
        self._scroll_offset = 0
        self._overlay: _DropdownOverlay | None = None
        self._overlay_parent: QWidget | None = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setFixedHeight(self.BASE_HEIGHT)
        self._theme.theme_changed.connect(self.update)

    def _item_height(self) -> int:
        return max(28, QFontMetrics(self.font()).height() + self.ITEM_VERTICAL_PADDING)

    def _visible_items(self) -> int:
        return min(self.count(), self._max_visible_items)

    def _ensure_current_visible(self):
        if self.count() <= self._max_visible_items or self._current_index < 0:
            self._scroll_offset = 0
            return
        if self._current_index < self._scroll_offset:
            self._scroll_offset = self._current_index
        elif self._current_index >= self._scroll_offset + self._max_visible_items:
            self._scroll_offset = self._current_index - self._max_visible_items + 1

    def count(self) -> int:
        return len(self._items)

    def addItem(self, text: str, userData: Any = None):
        self._items.append(_ComboItem(str(text), userData))
        if self._current_index == -1:
            self._current_index = 0
        self.update()

    def clear(self):
        self.hideDropdown()
        self._items.clear()
        self._current_index = -1
        self._scroll_offset = 0
        self.update()

    def currentIndex(self) -> int:
        return self._current_index

    def currentText(self) -> str:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index].text
        return ""

    def currentData(self) -> Any:
        if 0 <= self._current_index < len(self._items):
            return self._items[self._current_index].data
        return None

    def itemText(self, index: int) -> str:
        if 0 <= index < len(self._items):
            return self._items[index].text
        return ""

    def itemData(self, index: int) -> Any:
        if 0 <= index < len(self._items):
            return self._items[index].data
        return None

    def findText(self, text: str) -> int:
        for idx, item in enumerate(self._items):
            if item.text == text:
                return idx
        return -1

    def findData(self, data: Any) -> int:
        for idx, item in enumerate(self._items):
            if item.data == data:
                return idx
        return -1

    def setCurrentText(self, text: str):
        idx = self.findText(text)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def setCurrentIndex(self, index: int):
        if not (0 <= index < len(self._items)) or index == self._current_index:
            return
        old_index = self._current_index
        self._current_index = index
        self.update()
        if self._expanded and self._overlay is not None:
            self._ensure_current_visible()
            self._overlay._sync_scrollbar()
            self._overlay.update()
        if not self.signalsBlocked():
            self.currentIndexChanged.emit(index)
            self.currentTextChanged.emit(self.currentText())

    def setMaxVisibleItems(self, count: int):
        self._max_visible_items = max(1, int(count))
        if self._expanded and self._overlay is not None:
            self._overlay.show_for_owner()

    def maxVisibleItems(self) -> int:
        return self._max_visible_items

    def setMinimumContentsLength(self, count: int):
        self._minimum_contents_length = max(0, int(count))
        self.updateGeometry()

    def setSizeAdjustPolicy(self, _policy):
        pass

    def _content_width_hint(self) -> int:
        fm = QFontMetrics(self.font())
        text_width = 0
        for item in self._items:
            text_width = max(text_width, fm.horizontalAdvance(item.text))

        if self._minimum_contents_length > 0:
            text_width = max(
                text_width,
                fm.horizontalAdvance("M" * self._minimum_contents_length),
            )

        return max(100, text_width + 24)

    def sizeHint(self) -> QSize:
        return QSize(self._content_width_hint(), self.BASE_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(max(80, self._content_width_hint()), self.BASE_HEIGHT)

    def _field_rect(self) -> QRect:
        return QRect(0, 0, self.width(), self.BASE_HEIGHT)

    def _draw_field(self, painter: QPainter):
        tm = self._theme
        is_dark = tm.is_dark()
        rect = self._field_rect()
        rectf = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)

        if not self.isEnabled():
            bg_color = tm.get_color("button.primary.background")
            text_color = QColor(tm.get_color("dialog.text"))
            text_color.setAlpha(140 if is_dark else 120)
        elif self._pressed or self._expanded:
            bg_color = tm.get_color("button.primary.background")
            text_color = tm.get_color("button.primary.text")
        elif self._hovered:
            bg_color = tm.get_color("button.primary.background.hover")
            text_color = tm.get_color("button.primary.text")
        else:
            bg_color = tm.get_color("button.primary.background")
            text_color = tm.get_color("button.primary.text")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

        border_color = QColor(tm.get_color("button.primary.border"))
        pen_border = QPen(border_color)
        pen_border.setWidthF(1.0)
        painter.setPen(pen_border)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rectf, self.RADIUS, self.RADIUS)

        draw_bottom_underline(
            painter,
            rect,
            tm,
            UnderlineConfig(alpha=40, thickness=1.0, arc_radius=4.0),
        )

        painter.setPen(QPen(text_color))
        painter.setFont(self.font())
        text_rect = rect.adjusted(
            self.TEXT_HORIZONTAL_PADDING,
            0,
            -self.TEXT_HORIZONTAL_PADDING,
            0,
        )
        elided = QFontMetrics(self.font()).elidedText(
            self.currentText(), Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._draw_field(painter)
        painter.end()

    def _ensure_overlay(self):
        window = self.window()
        if window is None:
            return
        if self._overlay is None or self._overlay_parent is not window:
            if self._overlay is not None:
                self._overlay.deleteLater()
            self._overlay_parent = window
            self._overlay = _DropdownOverlay(self, window)

    def showDropdown(self):
        if self.count() == 0:
            return
        self._ensure_overlay()
        if self._overlay is None:
            return
        self._expanded = True
        self._pressed = False
        self._ensure_current_visible()
        logger.debug(
            "[FluentComboBox.showDropdown] object=%s current=%d count=%d scroll_offset=%d",
            self.objectName() or "<unnamed>",
            self.currentIndex(),
            self.count(),
            self._scroll_offset,
        )
        self._overlay.show_for_owner()
        self.update()
        QApplication.instance().installEventFilter(self)
        window = self.window()
        if window is not None:
            window.installEventFilter(self)

    def hideDropdown(self):
        if self._overlay is not None:
            self._overlay.hide()
        self._expanded = False
        self._pressed = False
        self.update()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        window = self.window()
        if window is not None:
            window.removeEventFilter(self)

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
            self._pressed = True
            self.setFocus()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        was_pressed = self._pressed
        self._pressed = False
        if was_pressed and self._field_rect().contains(event.position().toPoint()):
            if self._expanded:
                self.hideDropdown()
            else:
                self.showDropdown()
            event.accept()
            return
        self.update()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self._expanded:
                self.hideDropdown()
            else:
                self.showDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Escape and self._expanded:
            self.hideDropdown()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Down and self.count() > 0:
            self.setCurrentIndex(min(self.count() - 1, max(0, self._current_index + 1)))
            event.accept()
            return

        if event.key() == Qt.Key.Key_Up and self.count() > 0:
            self.setCurrentIndex(max(0, self._current_index - 1))
            event.accept()
            return

        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if not self.isEnabled() or self.count() <= 1:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            new_index = (self._current_index - 1 + self.count()) % self.count()
        elif delta < 0:
            new_index = (self._current_index + 1) % self.count()
        else:
            return
        self.setCurrentIndex(new_index)
        event.accept()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        next_widget = QApplication.focusWidget()
        logger.debug(
            "[FluentComboBox.focusOut] object=%s next=%s expanded=%r overlay_visible=%r",
            self.objectName() or "<unnamed>",
            type(next_widget).__name__ if next_widget is not None else None,
            self._expanded,
            self._overlay.isVisible() if self._overlay is not None else False,
        )
        if not self._expanded:
            return
        QTimer.singleShot(0, self._hide_dropdown_if_focus_left)

    def _is_dropdown_widget(self, widget) -> bool:
        current = widget
        while current is not None:
            if current is self or current is self._overlay:
                return True
            current = current.parentWidget() if hasattr(current, "parentWidget") else None
        return False

    def _hide_dropdown_if_focus_left(self):
        if not self._expanded:
            return
        app = QApplication.instance()
        next_widget = app.focusWidget() if app is not None else None
        window = self.window()
        if next_widget is not None and self._is_dropdown_widget(next_widget):
            return
        if window is not None and window.isActiveWindow():
            return
        self.hideDropdown()

    def eventFilter(self, watched, event):
        if not self._expanded or self._overlay is None:
            return super().eventFilter(watched, event)

        if watched is self.window() and event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
            self._overlay.show_for_owner()
            return False

        if event.type() in (
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
            QEvent.Type.Hide,
            QEvent.Type.Close,
        ):
            self.hideDropdown()
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            global_pos = event.globalPosition().toPoint()
            inside_field = self.rect().contains(self.mapFromGlobal(global_pos))
            inside_overlay = self._overlay.geometry().contains(self._overlay.parentWidget().mapFromGlobal(global_pos))
            if not inside_field and not inside_overlay:
                self.hideDropdown()
        return super().eventFilter(watched, event)
