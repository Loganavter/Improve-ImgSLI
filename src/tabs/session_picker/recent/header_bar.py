"""Header bar for the Session Picker Recent shelf (title + sort/view)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenuAction,
    Label,
    popup_context_menu_for_anchor,
)

from services.io.recent_projects import (
    SORT_ASC,
    SORT_CREATED,
    SORT_DESC,
    SORT_MODIFIED,
    SORT_NAME,
    VIEW_GRID,
    VIEW_LIST,
    normalize_recent_sort_mode,
    set_recent_sort_mode,
    set_recent_sort_order,
    set_recent_view_mode,
)
from tabs.session_picker.icons import Icon as SessionPickerIcon
from tabs.session_picker.icons import get_icon as get_session_picker_icon


class RecentHeaderBar(QWidget):
    """Title plus sort/view chips. Emits prefs changes; does not own MRU data."""

    prefs_changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, tr: Callable[..., str]):
        super().__init__(parent)
        self._tr = tr
        self._sort_mode = SORT_MODIFIED
        self._sort_order = SORT_DESC
        self._view_mode = "grid"
        self.setObjectName("RecentHeaderBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.title_label = Label(
            self._tr("recent.title", "Recent"),
            pixel_size=16,
            bold=True,
        )
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.sort_button = Button(
            text=self._sort_label(),
            variant="default",
            size=(168, 28),
            corner_radius=8,
        )
        self.sort_button.clicked.connect(self._on_sort_clicked)
        layout.addWidget(self.sort_button)

        self.sort_order_button = Button(
            icon=get_session_picker_icon(SessionPickerIcon.SORT_DESC),
            variant="default",
            size=(28, 28),
            corner_radius=8,
        )
        self.sort_order_button.clicked.connect(self._toggle_sort_order)
        layout.addWidget(self.sort_order_button)

        self.view_button = Button(
            icon=get_session_picker_icon(SessionPickerIcon.VIEW_GRID),
            variant="default",
            size=(28, 28),
            corner_radius=8,
        )
        self.view_button.clicked.connect(self._toggle_view)
        layout.addWidget(self.view_button)

    def sync(
        self,
        *,
        sort_mode: str,
        sort_order: str,
        view_mode: str,
        has_items: bool,
        chip_bg: QColor,
    ) -> None:
        self._sort_mode = sort_mode
        self._sort_order = sort_order
        self._view_mode = view_mode
        self.title_label.setText(self._tr("recent.title", "Recent"))
        self.sort_button.setText(self._sort_label())
        # Exact opaque fill — custom_bg is an 18% tint and cannot lighten
        # a shelf (only darken), so override_bg is required here.
        self.sort_button.set_override_bg_color(chip_bg)
        self.sort_button.setVisible(has_items)

        order_icon = (
            SessionPickerIcon.SORT_ASC
            if self._sort_order == SORT_ASC
            else SessionPickerIcon.SORT_DESC
        )
        self.sort_order_button.setIcon(get_session_picker_icon(order_icon))
        self.sort_order_button.setToolTip(self._sort_order_label())
        self.sort_order_button.set_override_bg_color(chip_bg)
        self.sort_order_button.setVisible(has_items)

        view_icon = (
            SessionPickerIcon.VIEW_LIST
            if self._view_mode == VIEW_LIST
            else SessionPickerIcon.VIEW_GRID
        )
        self.view_button.setIcon(get_session_picker_icon(view_icon))
        self.view_button.setToolTip(self._view_label())
        self.view_button.set_override_bg_color(chip_bg)
        self.view_button.setVisible(has_items)

    def set_controls_visible(self, visible: bool) -> None:
        self.sort_button.setVisible(visible)
        self.sort_order_button.setVisible(visible)
        self.view_button.setVisible(visible)

    def _sort_label(self) -> str:
        if self._sort_mode == SORT_NAME:
            return self._tr("recent.sort_name", "Name")
        if self._sort_mode == SORT_CREATED:
            return self._tr("recent.sort_created", "Date created")
        return self._tr("recent.sort_modified", "Date modified")

    def _sort_order_label(self) -> str:
        if self._sort_order == SORT_ASC:
            return self._tr("recent.sort_asc", "Ascending")
        return self._tr("recent.sort_desc", "Descending")

    def _view_label(self) -> str:
        if self._view_mode == VIEW_LIST:
            return self._tr("recent.view_list", "List")
        return self._tr("recent.view_grid", "Grid")

    def _on_sort_clicked(self) -> None:
        parent = self.window()
        if parent is None:
            return
        options = (
            (
                "recent.sort.modified",
                self._tr("recent.sort_modified", "Date modified"),
                SORT_MODIFIED,
                SessionPickerIcon.SORT_BY_MODIFIED,
            ),
            (
                "recent.sort.created",
                self._tr("recent.sort_created", "Date created"),
                SORT_CREATED,
                SessionPickerIcon.SORT_BY_CREATED,
            ),
            (
                "recent.sort.name",
                self._tr("recent.sort_name", "Name"),
                SORT_NAME,
                SessionPickerIcon.SORT_BY_NAME,
            ),
        )
        entries = tuple(
            ContextMenuAction(
                action_id,
                label,
                icon=get_session_picker_icon(icon),
                data=mode,
                checkable=True,
                checked=self._sort_mode == mode,
            )
            for action_id, label, mode, icon in options
        )

        def on_triggered(_action_id: str, data: object) -> None:
            self._sort_mode = normalize_recent_sort_mode(str(data))
            set_recent_sort_mode(self._sort_mode)
            self.prefs_changed.emit()

        popup_context_menu_for_anchor(
            parent,
            self.sort_button,
            entries,
            on_triggered=on_triggered,
        )

    def _toggle_sort_order(self) -> None:
        self._sort_order = SORT_ASC if self._sort_order == SORT_DESC else SORT_DESC
        set_recent_sort_order(self._sort_order)
        self.prefs_changed.emit()

    def _toggle_view(self) -> None:
        self._view_mode = VIEW_LIST if self._view_mode == VIEW_GRID else VIEW_GRID
        set_recent_view_mode(self._view_mode)
        self.prefs_changed.emit()
