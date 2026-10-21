"""Help page text selection context menu (app-owned ContextMenu)."""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget

from resources.translations import tr
from sli_ui_toolkit.widgets import (
    ContextMenuAction,
    ContextMenuSeparator,
    Text,
)
from ui.context_menu.manager import open_context_menu_entries
from ui.icon_manager import AppIcon, themed_icon


def _tr_help(key: str, fallback: str, language: str) -> str:
    text = tr(key, language=language)
    return fallback if text == key else text


def open_help_text_context_menu(
    *,
    dialog: QWidget,
    document: Text,
    global_pos: QPoint,
    language: str,
    source_markdown: str = "",
) -> None:
    """Open the standard in-app context menu for help body text.

    ``document`` is the host's ``Text(mode="document")``. The page source is
    host state: ``Text.set_blocks`` clears ``source_markdown`` by design, so
    copy-as-Markdown receives the markdown the dialog rendered from.
    """
    has_selection = bool(document.selected_plain_text().strip())
    entries: list[ContextMenuAction | ContextMenuSeparator] = [
        ContextMenuAction(
            "help.text.copy",
            _tr_help("help.context.copy", "Copy", language),
            icon=themed_icon("copy.svg"),
            shortcut="Ctrl+C",
            enabled=has_selection,
        ),
    ]

    entries.append(
        ContextMenuAction(
            "help.text.copy_markdown",
            _tr_help("help.context.copy_markdown", "Copy as Markdown", language),
            icon=themed_icon("text_filename.svg"),
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
            # Toolkit copy contract: clipboard + the selection is dropped
            # afterwards (a copy ends the selection gesture). Do not set the
            # clipboard here — that is what left the highlight behind.
            document.copy_selection()
        elif action_id == "help.text.select_all":
            document.select_all_text()
        elif action_id == "help.text.copy_markdown":
            document.copy_selection_markdown(source_markdown)

    # The menu stays on the app-wide RMB surface (``in_window``): it is a
    # child overlay of the dialog, drawn into the dialog's own surface.
    #
    # Do NOT opt this menu out to a native ``Qt.Popup`` top-level (2026-10-21,
    # live on Wayland/Mutter): in this app's widget tree a popup-surface
    # ContextMenu gets a wl_surface with NO compositor role — it is not an
    # xdg_popup, not a subsurface, just an orphan surface. The compositor
    # therefore never composites it: the menu is painted (its buffer reaches
    # the server) but nothing appears, and the host window's drawing is
    # disturbed. Proof: a WAYLAND_DEBUG trace of the live app shows the
    # menu's surface created with only a viewport and never given an
    # xdg_surface, while the dialog and the main window get theirs.
    # The same path is used by the gallery's popup menus — see the
    # investigation in internal-docs.
    open_context_menu_entries(
        source_widget=dialog,
        global_pos=global_pos,
        entries=tuple(entries),
        key=("help_text", id(document)),
        on_triggered=on_triggered,
    )