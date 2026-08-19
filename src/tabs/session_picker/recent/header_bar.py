"""Control buttons for the Session Picker Recent shelf header (sort/view).

The shelf title lives in the shared ``ShelfWidget`` (``ui.widgets.shelf``);
this widget is the "control buttons on top" cluster the shelf host adds via
``add_header_widget``. Emits prefs changes; does not own MRU data.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenuAction,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu

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

logger = logging.getLogger("ImproveImgSLI")


class RecentHeaderBar(QWidget):
    """Sort/view chips for the shelf header. Emits prefs changes; no MRU data."""

    prefs_changed = Signal()

    def __init__(self, parent: QWidget | None = None, *, tr: Callable[..., str]):
        super().__init__(parent)
        self._tr = tr
        self._sort_mode = SORT_MODIFIED
        self._sort_order = SORT_DESC
        self._view_mode = "grid"
        self.setObjectName("RecentHeaderBar")
        self._sort_menu: ContextMenu | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

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

    def keyPressEvent(self, event) -> None:  # noqa: N802
        from PySide6.QtWidgets import QApplication

        key = event.key()
        buttons = [
            b for b in (self.sort_button, self.sort_order_button, self.view_button)
            if b.isVisible()
        ]
        if not buttons:
            super().keyPressEvent(event)
            return
        focused = QApplication.focusWidget()
        idx = next((i for i, b in enumerate(buttons) if b is focused), None)
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            if idx is not None and idx > 0:
                buttons[idx - 1].setFocus(Qt.FocusReason.OtherFocusReason)
                event.accept()
                logger.debug(
                    "[shelf-nav] header left/up idx=%d -> button %d/%d",
                    idx, idx - 1, len(buttons),
                )
                return
            # Past first → hand off to last create-card in the session picker.
            logger.debug(
                "[shelf-nav] header left/up idx=%s -> create-cards (past first)", idx
            )
            picker = self.parentWidget()
            while picker is not None and not hasattr(picker, "focus_last_create_card"):
                picker = picker.parentWidget()
            if picker is not None and picker.focus_last_create_card():
                event.accept()
                return
            event.ignore()
            super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Right:
            if idx is not None and idx < len(buttons) - 1:
                buttons[idx + 1].setFocus(Qt.FocusReason.OtherFocusReason)
                event.accept()
                logger.debug(
                    "[shelf-nav] header right idx=%d -> button %d/%d",
                    idx, idx + 1, len(buttons),
                )
                return
            event.ignore()
            super().keyPressEvent(event)
            return
        if key == Qt.Key.Key_Down:
            # Down from any header button → first shelf card.
            logger.debug(
                "[shelf-nav] header down idx=%s -> shelf cards", idx
            )
            panel = self.parentWidget()
            while panel is not None and not hasattr(panel, "focus_recent_item"):
                panel = panel.parentWidget()
            if panel is not None and panel.focus_recent_item(True):
                event.accept()
                return
            event.ignore()
            super().keyPressEvent(event)
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if idx is not None:
                buttons[idx].clicked.emit()
                event.accept()
                return
        super().keyPressEvent(event)

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

        # Toggle: hide the old menu if still visible.
        existing = getattr(self.sort_button, "_anchor_context_menu", None)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.hide()
                    return
            except RuntimeError:
                pass
            self.sort_button._anchor_context_menu = None  # type: ignore[attr-defined]

        menu = ContextMenu(
            parent,
            entries=entries,
            on_triggered=on_triggered,
            surface="in_window",
        )
        self._sort_menu = menu
        self.sort_button._anchor_context_menu = menu  # type: ignore[attr-defined]
        menu.show_aligned(
            self.sort_button,
            anchor_point="bottom-center",
            flyout_point="top-center",
            offset=2,
            animation_axis="vertical",
        )

    def _toggle_sort_order(self) -> None:
        self._sort_order = SORT_ASC if self._sort_order == SORT_DESC else SORT_DESC
        set_recent_sort_order(self._sort_order)
        self.prefs_changed.emit()

    def _toggle_view(self) -> None:
        self._view_mode = VIEW_LIST if self._view_mode == VIEW_GRID else VIEW_GRID
        set_recent_view_mode(self._view_mode)
        self.prefs_changed.emit()