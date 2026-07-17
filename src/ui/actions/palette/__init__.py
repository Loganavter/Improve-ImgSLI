"""Find Action host entrypoints — open palette, install shortcuts, topic resolve."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

from ui.actions.palette.dialog import FindActionDialog

logger = logging.getLogger("ImproveImgSLI")


def refresh_open_dialog_find_actions() -> int:
    """Re-contribute Find Action chrome from any open dialog that supports it.

    Video Editor / Export register temporarily; if contribution was skipped on
    reuse/raise, opening the palette from the main window still picks them up.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return 0
    refreshed = 0
    for widget in app.topLevelWidgets():
        contribute = getattr(widget, "_contribute_find_actions", None)
        if not callable(contribute):
            continue
        try:
            if not widget.isVisible():
                continue
        except RuntimeError:
            continue
        try:
            contribute()
            refreshed += 1
        except Exception:
            logger.debug(
                "[find-action] refresh contribute failed on %s",
                type(widget).__name__,
                exc_info=True,
            )
    return refreshed


def show_command_palette(
    *,
    query: str = "",
    topic: str | None = None,
    parent: QWidget | None = None,
    preselect_action_id: str | None = None,
    auto_pulse: bool = False,
    active_tab: str | None = None,
) -> None:
    # ``parent`` is only a geometry hint (center on its screen); ownership stays
    # with a root-level window so the palette is not a child/transient popup.
    # Prefer the parent dialog's tab override when opening from Video/Export.
    if active_tab is None and parent is not None:
        active_tab = getattr(parent, "_find_action_owner_tab", None)
    refresh_open_dialog_find_actions()
    if parent is not None:
        contribute = getattr(parent, "_contribute_find_actions", None)
        if callable(contribute):
            try:
                contribute()
            except Exception:
                logger.debug(
                    "[find-action] parent contribute failed on %s",
                    type(parent).__name__,
                    exc_info=True,
                )
    dialog = FindActionDialog(
        None,
        query=query,
        topic=topic,
        preselect_action_id=preselect_action_id,
        auto_pulse=auto_pulse,
        active_tab=active_tab,
    )
    center_on_reference(dialog, parent)
    dialog.exec()


def center_on_reference(dialog: QWidget, reference: QWidget | None) -> None:
    screen = None
    if reference is not None:
        window = reference.window()
        handle = window.windowHandle() if window is not None else None
        if handle is not None:
            screen = handle.screen()
        elif window is not None:
            screen = window.screen()
    if screen is None:
        from PySide6.QtGui import QGuiApplication

        screen = QGuiApplication.primaryScreen()
    if screen is None:
        return
    geo = screen.availableGeometry()
    frame = dialog.frameGeometry()
    frame.moveCenter(geo.center())
    dialog.move(frame.topLeft())


def install_dialog_find_action_shortcut(
    dialog: QWidget,
    *,
    active_tab: str | None = None,
) -> QShortcut:
    """Ctrl+Shift+P on a dialog window (main-window binder does not reach it)."""
    existing = getattr(dialog, "_find_action_shortcut", None)
    if existing is not None:
        return existing

    owner = active_tab or getattr(dialog, "_find_action_owner_tab", None)

    def _open() -> None:
        show_command_palette(parent=dialog, active_tab=owner)

    shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), dialog)
    shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
    shortcut.setAutoRepeat(False)
    shortcut.activated.connect(_open)
    dialog._find_action_shortcut = shortcut
    return shortcut


def install_find_action_shortcut(window: QWidget, callback) -> None:
    """Deprecated: shortcuts come from ActionShortcutBinder. Kept as no-op sync."""
    del callback
    from ui.actions.binder import resync_action_shortcuts

    resync_action_shortcuts(window)


def install_contextual_palette_shortcut(window: QWidget, callback) -> None:
    """Deprecated: shortcuts come from ActionShortcutBinder. Kept as no-op sync."""
    del callback
    from ui.actions.binder import resync_action_shortcuts

    resync_action_shortcuts(window)


def resolve_palette_topic_from_focus(*, active_tab: str | None = None) -> str | None:
    from PySide6.QtWidgets import QApplication
    from ui.actions.registry import get_action_registry

    focused = QApplication.focusWidget()
    return get_action_registry().topic_for_widget(focused, active_tab=active_tab)
