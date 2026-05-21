from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QFontMetrics, QMouseEvent, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.helpers import (
    calculate_centered_overlay_geometry,
    draw_rounded_shadow,
)

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.comboboxes.combo_box import ComboBox

logger = logging.getLogger(__name__)

class _DropdownOverlay(QWidget):
    RADIUS = 8
    SHADOW = 10
    GAP = 6

    def __init__(self, owner: "ComboBox", parent: QWidget):
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

    def _visible_item_indices(self) -> list[int]:
        return self._owner._visible_indices()

    def _list_height(self) -> int:
        return self._visible_items() * self._item_height()

    def _content_rect(self) -> QRect:
        return self.rect().adjusted(self.SHADOW, self.SHADOW, -self.SHADOW, -self.SHADOW)

    def _has_scrollbar(self) -> bool:
        return len(self._visible_item_indices()) > self._owner.maxVisibleItems()

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
            visible_index=max(0, owner._visible_position_for_index(owner.currentIndex()) - owner._scroll_offset),
            row_height=self._item_height(),
            scrollable=len(self._visible_item_indices()) > owner.maxVisibleItems(),
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
        max_offset = max(0, len(self._visible_item_indices()) - self._visible_items())
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
        new_offset = max(0, min(int(value), max(0, len(self._visible_item_indices()) - self._visible_items())))
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
        draw_rounded_shadow(painter, content, steps=self.SHADOW, radius=self.RADIUS)

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
        visible_indices = self._visible_item_indices()
        for visible_idx in range(visible_count):
            source_pos = self._owner._scroll_offset + visible_idx
            if source_pos >= len(visible_indices):
                break
            item_index = visible_indices[source_pos]
            item = self._owner._items[item_index]
            item_rect = QRectF(
                self._item_rect(visible_idx).translated(self._content_rect().topLeft()).adjusted(0, 1, -1, -1)
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
            scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
            QApplication.sendEvent(
                self.custom_v_scrollbar,
                QMouseEvent(
                    event.type(),
                    QPointF(scrollbar_pos),
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
        visible_indices = self._visible_item_indices()
        for visible_idx in range(self._visible_items()):
            source_pos = self._owner._scroll_offset + visible_idx
            if source_pos >= len(visible_indices):
                break
            item_index = visible_indices[source_pos]
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
            scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
            QApplication.sendEvent(
                self.custom_v_scrollbar,
                QMouseEvent(
                    event.type(),
                    QPointF(scrollbar_pos),
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
        visible_indices = self._visible_item_indices()
        for visible_idx in range(self._visible_items()):
            source_pos = self._owner._scroll_offset + visible_idx
            if source_pos >= len(visible_indices):
                break
            item_index = visible_indices[source_pos]
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
        visible_count = len(self._visible_item_indices())
        if visible_count <= self._owner._max_visible_items:
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta > 0:
            self._owner._scroll_offset = max(0, self._owner._scroll_offset - 1)
        elif delta < 0:
            self._owner._scroll_offset = min(
                visible_count - self._owner._max_visible_items,
                self._owner._scroll_offset + 1,
            )
        self._sync_scrollbar()
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.custom_v_scrollbar.isVisible():
            if self.custom_v_scrollbar.geometry().contains(event.position().toPoint()):
                scrollbar_pos = self.custom_v_scrollbar.mapFromGlobal(event.globalPosition().toPoint())
                QApplication.sendEvent(
                    self.custom_v_scrollbar,
                    QMouseEvent(
                        event.type(),
                        QPointF(scrollbar_pos),
                        event.globalPosition(),
                        event.button(),
                        event.buttons(),
                        event.modifiers(),
                    ),
                )
                event.accept()
                return
        super().mousePressEvent(event)
