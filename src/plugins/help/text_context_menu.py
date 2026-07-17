"""Help page text selection context menu (app-owned ContextMenu)."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from resources.translations import tr
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuSeparator,
    HelpDocumentView,
)
from ui.context_menu.manager import open_context_menu_entries
from ui.icon_manager import AppIcon, get_app_icon


def _tr_help(key: str, fallback: str, language: str) -> str:
    text = tr(key, language=language)
    return fallback if text == key else text


def open_help_text_context_menu(
    *,
    dialog: QWidget,
    document: HelpDocumentView,
    global_pos: QPoint,
    language: str,
) -> None:
    """Open the standard in-app context menu for help body text."""
    has_selection = bool(document.selected_plain_text().strip())
    entries: list[ContextMenuAction | ContextMenuSeparator] = [
        ContextMenuAction(
            "help.text.copy",
            _tr_help("help.context.copy", "Copy", language),
            icon=get_app_icon("copy.svg"),
            shortcut="Ctrl+C",
            enabled=has_selection,
        ),
    ]

    entries.append(
        ContextMenuAction(
            "help.text.copy_markdown",
            _tr_help("help.context.copy_markdown", "Copy as Markdown", language),
            icon=get_app_icon("text_filename.svg"),
            shortcut="Ctrl+Shift+C",
            enabled=has_selection,
        )
    )
    entries.append(ContextMenuSeparator())
    entries.append(
        ContextMenuAction(
            "help.text.select_all",
            _tr_help("help.context.select_all", "Select all", language),
            icon=AppIcon.TEXT_MANIPULATOR,
            shortcut="Ctrl+A",
        )
    )

    def on_triggered(action_id: str, _data: object) -> None:
        if action_id == "help.text.copy":
            text = document.selected_plain_text()
            if text:
                QGuiApplication.clipboard().setText(text)
        elif action_id == "help.text.select_all":
            document.select_all_text()
        elif action_id == "help.text.copy_markdown":
            text = document.selected_markdown()
            if text:
                QGuiApplication.clipboard().setText(text)

    open_context_menu_entries(
        source_widget=dialog,
        global_pos=global_pos,
        entries=tuple(entries),
        key=("help_text", id(document)),
        on_triggered=on_triggered,
    )
