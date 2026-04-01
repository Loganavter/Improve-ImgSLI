from __future__ import annotations

from typing import Iterable

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QFrame, QListWidget, QListWidgetItem

from ...services import get_icon_service
from ..atomic.minimalist_scrollbar import MinimalistScrollBar
from ui.icon_manager import get_app_icon

class SidebarNavList(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setIconSize(QSize(24, 24))
        self._items_data: list[tuple[str, object | None]] = []

    def enable_minimal_scrollbar(self) -> None:
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBar(MinimalistScrollBar())

    def set_nav_items(self, items: Iterable[tuple[str, object | None]]) -> None:
        self.clear()
        self._items_data = list(items)
        for text, icon_enum in self._items_data:
            item = QListWidgetItem(self._build_icon(icon_enum, selected=False), text)
            item.setSizeHint(QSize(0, 44))
            self.addItem(item)

    def refresh_icons(self) -> None:
        current_row = self.currentRow()
        for i, (_text, icon_enum) in enumerate(self._items_data):
            if i >= self.count():
                continue
            self.item(i).setIcon(self._build_icon(icon_enum, selected=(i == current_row)))

    def _build_icon(self, icon_enum, *, selected: bool) -> QIcon:
        if icon_enum is None:
            return QIcon()

        icon_service = get_icon_service("Improve-ImgSLI")
        base_icon = (
            icon_service.get_icon(icon_enum.value, is_dark=True)
            if selected
            else get_app_icon(icon_enum)
        )
        pixmap = base_icon.pixmap(self.iconSize())
        if pixmap.isNull():
            return base_icon

        icon = QIcon()
        for mode in (
            QIcon.Mode.Normal,
            QIcon.Mode.Active,
            QIcon.Mode.Selected,
            QIcon.Mode.Disabled,
        ):
            icon.addPixmap(pixmap, mode, QIcon.State.Off)
            icon.addPixmap(pixmap, mode, QIcon.State.On)
        return icon
