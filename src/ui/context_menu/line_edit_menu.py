"""App-wide right-click context menu for QLineEdit (and CustomLineEdit).

Same styled ContextMenu the help viewer uses for its text body
(``plugins/help/text_context_menu.py``), installed once for every line edit
instead of Qt's native undo/cut/copy/paste menu.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from resources.translations import tr
from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
from ui.context_menu.manager import open_context_menu_entries
from ui.icon_manager import AppIcon, get_app_icon


class _LineEditContextMenuFilter(QObject):
    """Right-click -> app-styled ContextMenu instead of Qt's native one.

    The selection is captured on the right-button *press*, before the
    ContextMenu event: focus-parking and other app-level event filters that
    react to the same press (``apply_editable_text_behavior``'s
    ``clearFocus`` scheduling, popup creation, ...) can clear the live
    selection by the time the ContextMenu event itself arrives, which made
    Copy always show disabled. Captured selection is restored right before
    the menu is built so both the entry state and the on-screen highlight
    stay correct.
    """

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._pending_selection: tuple[QLineEdit, int, str] | None = None

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if (
            event.type() == QEvent.Type.MouseButtonPress
            and isinstance(watched, QLineEdit)
            and isinstance(event, QMouseEvent)
            and event.button() == Qt.MouseButton.RightButton
        ):
            if watched.hasSelectedText():
                self._pending_selection = (
                    watched,
                    watched.selectionStart(),
                    watched.selectedText(),
                )
            else:
                self._pending_selection = None
            return super().eventFilter(watched, event)
        if event.type() == QEvent.Type.ContextMenu and isinstance(watched, QLineEdit):
            self._open_menu(watched, event.globalPos())  # type: ignore[attr-defined]  # QContextMenuEvent globalPos
            return True
        return super().eventFilter(watched, event)

    def _restore_pending_selection(self, line_edit: QLineEdit) -> None:
        pending = self._pending_selection
        self._pending_selection = None
        if pending is None:
            return
        widget, start, text = pending
        if widget is not line_edit or line_edit.hasSelectedText():
            return
        if line_edit.text()[start : start + len(text)] != text:
            return
        line_edit.setSelection(start, len(text))

    def _open_menu(self, line_edit: QLineEdit, global_pos) -> None:
        self._restore_pending_selection(line_edit)
        has_selection = line_edit.hasSelectedText()
        read_only = line_edit.isReadOnly()
        clipboard_has_text = bool(QGuiApplication.clipboard().text())

        entries: list[ContextMenuAction | ContextMenuSeparator] = [
            ContextMenuAction(
                "line_edit.cut",
                tr("action.context_cut", default="Cut"),
                shortcut="Ctrl+X",
                enabled=has_selection and not read_only,
            ),
            ContextMenuAction(
                "line_edit.copy",
                tr("action.context_copy", default="Copy"),
                icon=get_app_icon("copy.svg"),
                shortcut="Ctrl+C",
                enabled=has_selection,
            ),
            ContextMenuAction(
                "line_edit.paste",
                tr("action.context_paste", default="Paste"),
                shortcut="Ctrl+V",
                enabled=clipboard_has_text and not read_only,
            ),
            ContextMenuSeparator(),
            ContextMenuAction(
                "line_edit.select_all",
                tr("action.context_select_all", default="Select all"),
                icon=AppIcon.TEXT_MANIPULATOR,
                shortcut="Ctrl+A",
                enabled=bool(line_edit.text()),
            ),
        ]

        def on_triggered(action_id: str, _data: object) -> None:
            if action_id == "line_edit.cut":
                line_edit.cut()
            elif action_id == "line_edit.copy":
                line_edit.copy()
            elif action_id == "line_edit.paste":
                line_edit.paste()
            elif action_id == "line_edit.select_all":
                line_edit.selectAll()

        open_context_menu_entries(
            source_widget=line_edit,
            global_pos=global_pos,
            entries=tuple(entries),
            key=("line_edit", id(line_edit)),
            on_triggered=on_triggered,
        )


_installed = False


def install_line_edit_context_menu_policy(app: QApplication) -> None:
    """Install the styled ПКМ menu for every ``QLineEdit`` in the process."""
    global _installed
    if _installed:
        return
    event_filter = _LineEditContextMenuFilter(app)
    app.installEventFilter(event_filter)
    app._line_edit_context_menu_filter = event_filter  # type: ignore[attr-defined]  # dynamic attribute
    _installed = True
