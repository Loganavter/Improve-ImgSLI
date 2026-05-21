from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QFrame, QListWidget, QListWidgetItem

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

@dataclass(slots=True)
class IconListItem:
    text: str
    icon: object | None = None
    data: object | None = None
    row_height: int = 44

class IconListWidget(QListWidget):
    def __init__(self, parent=None, *, icon_size: QSize | None = None, row_height: int = 44):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setIconSize(icon_size or QSize(24, 24))
        self._row_height = int(row_height)
        self._items_data: list[IconListItem] = []

    def enable_minimal_scrollbar(self) -> None:
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBar(MinimalistScrollBar())

    def set_items(self, items: Iterable[IconListItem | tuple[str, object | None]]) -> None:
        self.clear()
        self._items_data = []
        for item in items:
            spec = item if isinstance(item, IconListItem) else IconListItem(*item)
            self._items_data.append(spec)
            list_item = QListWidgetItem(self._build_icon(spec.icon), spec.text)
            list_item.setSizeHint(QSize(0, spec.row_height or self._row_height))
            list_item.setData(Qt.ItemDataRole.UserRole, spec.data)
            self.addItem(list_item)

    def refresh_icons(self) -> None:
        for index, spec in enumerate(self._items_data):
            if index >= self.count():
                continue
            self.item(index).setIcon(self._build_icon(spec.icon))

    def _build_icon(self, icon_value) -> QIcon:
        if icon_value is None:
            return QIcon()
        base_icon = resolve_icon(icon_value)
        if base_icon.isNull():
            return QIcon()

        icon = QIcon(base_icon)
        selected_color = self._selected_icon_color()
        selected_pixmap = self._tinted_pixmap(base_icon, selected_color)
        if not selected_pixmap.isNull():
            icon.addPixmap(selected_pixmap, QIcon.Mode.Selected)
            icon.addPixmap(selected_pixmap, QIcon.Mode.Active)
        return icon

    def _selected_icon_color(self) -> QColor:
        theme = ThemeManager.get_instance()
        color = theme.try_get_color("HighlightedText")
        if color is None or not color.isValid():
            color = QColor("white")
        return color

    def _tinted_pixmap(self, icon: QIcon, color: QColor) -> QPixmap:
        size = self.iconSize()
        if not size.isValid():
            size = QSize(24, 24)
        base_pixmap = icon.pixmap(size, QIcon.Mode.Normal, QIcon.State.Off)
        if base_pixmap.isNull():
            base_pixmap = icon.pixmap(size)
        if base_pixmap.isNull():
            return QPixmap()

        tinted = QPixmap(base_pixmap.size())
        tinted.fill(Qt.GlobalColor.transparent)

        painter = QPainter(tinted)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        painter.drawPixmap(0, 0, base_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        return tinted

class SidebarNavList(IconListWidget):
    def set_nav_items(self, items: Iterable[tuple[str, object | None]]) -> None:
        self.set_items(items)
