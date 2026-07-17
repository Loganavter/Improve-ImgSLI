"""App-side wrapper around toolkit `decorate_dialog`.

Resolves AppIcon-named window-control icons before delegating to
``sli_ui_toolkit.decorate_dialog``.

Also installs an application-wide event filter that auto-decorates any
``QDialog`` / ``QMessageBox`` that's about to be shown for the first time —
otherwise error/warning popups would slip through with the OS native frame.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from sli_ui_toolkit import CustomTitleBar, decorate_dialog as _toolkit_decorate_dialog
from sli_ui_toolkit.theme import ThemeManager
from ui.theming import polish_themed_dialog, resolve_theme_color

CUSTOM_DECORATION_RESIZE_MARGIN = 8


_MSGBOX_TITLE_BY_ICON = {
    QMessageBox.Icon.Critical: "Error",
    QMessageBox.Icon.Warning: "Warning",
    QMessageBox.Icon.Information: "Information",
    QMessageBox.Icon.Question: "Confirm",
}


def _resolve_dialog_title(dialog: QDialog) -> str:
    title = dialog.windowTitle() or ""
    if title:
        return title
    if isinstance(dialog, QMessageBox):
        return _MSGBOX_TITLE_BY_ICON.get(dialog.icon(), "Message")
    return ""


def decorate_dialog(
    dialog: QDialog,
    *,
    title: str = "",
    show_minimize: bool = False,
    show_maximize: bool = False,
    show_close: bool = True,
    resizable: bool = True,
) -> CustomTitleBar | None:
    existing = getattr(dialog, "_csd_title_bar", None)
    if existing is not None:
        return existing if isinstance(existing, CustomTitleBar) else None
    # polish_themed_dialog can re-enter via the app Polish interceptor and
    # stack a second CustomTitleBar.HEIGHT onto the layout top margin.
    if bool(getattr(dialog, "_csd_decorating", False)):
        return None

    from ui.icon_manager import AppIcon

    dialog._csd_decorating = True
    try:
        theme_manager = ThemeManager.get_instance()
        polish_themed_dialog(theme_manager, dialog)

        title_bar = _toolkit_decorate_dialog(
            dialog,
            title=title,
            minimize_icon=AppIcon.MINIMIZE,
            maximize_icon=AppIcon.MAXIMIZE,
            restore_icon=AppIcon.RESTORE,
            close_icon=AppIcon.WINDOW_CLOSE,
            show_minimize=show_minimize,
            show_maximize=show_maximize,
            show_close=show_close,
            resizable=resizable,
            resize_margin=CUSTOM_DECORATION_RESIZE_MARGIN,
        )
        return title_bar
    finally:
        dialog._csd_decorating = False


def install_dialog_help_menu(
    dialog: QDialog,
    *,
    page: str | None = None,
    anchor: str | None = None,
    title_bar: CustomTitleBar | None = None,
) -> object | None:
    """Install the main-window Help menu (label + dropdown) on a dialog title bar.

    Same entries as the host Help menu: Show Help and Find Action. Leading
    zone, left of the title — mirrors ``MainWindowMenuController`` Help.
    Idempotent; no-op when decorations are off / title bar missing.
    """
    existing = getattr(dialog, "_csd_help_menu_strip", None)
    if existing is not None:
        return existing

    bar = title_bar if title_bar is not None else getattr(dialog, "_csd_title_bar", None)
    if bar is None:
        return None
    set_strip = getattr(bar, "set_menu_strip", None)
    set_leading = getattr(bar, "set_leading", None)
    if not callable(set_strip) and not callable(set_leading):
        return None

    from resources.translations import get_current_language, tr
    from sli_ui_toolkit import TitleBarMenu, TitleBarMenuStrip
    from sli_ui_toolkit.widgets import ContextMenuAction, ContextMenuSeparator
    from ui.actions.palette.dialog import open_help_page

    lang = get_current_language() or "en"

    def _tr(key: str, fallback: str) -> str:
        text = tr(key, lang)
        return fallback if text == key else text

    def _on_triggered(action_id: str, _data: object) -> None:
        if action_id == "help.show":
            open_help_page(page or "export", anchor)
            return
        if action_id == "help.find_action":
            from ui.actions.palette import show_command_palette

            owner = getattr(dialog, "_find_action_owner_tab", None)
            show_command_palette(parent=dialog, active_tab=owner)

    strip = TitleBarMenuStrip(
        [
            TitleBarMenu(
                label=_tr("menu.help", "Help"),
                entries=[
                    ContextMenuAction(
                        "help.show",
                        _tr("menu.show_help", "Show Help"),
                    ),
                    ContextMenuSeparator(),
                    ContextMenuAction(
                        "help.find_action",
                        _tr("menu.find_action", "Find Action"),
                        shortcut="Ctrl+Shift+P",
                    ),
                ],
                on_triggered=_on_triggered,
            )
        ],
        parent=bar,
    )
    if callable(set_strip):
        set_strip(strip)
    else:
        set_leading(strip)
    dialog._csd_help_menu_strip = strip
    return strip


# Back-compat alias used by early call sites / tests.
install_dialog_help_button = install_dialog_help_menu


def configure_custom_decoration_resize_margin() -> None:
    """Widen toolkit frameless resize hit target for custom-decorated dialogs."""
    from sli_ui_toolkit.ui.windows import frameless

    frameless.RESIZE_MARGIN = CUSTOM_DECORATION_RESIZE_MARGIN


class _DialogDecorationInterceptor(QObject):
    """Catch every top-level QDialog at Polish-time and decorate it.

    Polish fires once during widget setup, before the window is mapped onto
    the screen — calling :func:`decorate_dialog` here means the frameless flag
    is applied while the QWindow is still hidden, so there is no visible
    flicker. Dialogs that already carry ``_csd_title_bar`` (i.e. explicitly
    decorated by their authors) are skipped. Set ``_csd_opt_out = True`` on a
    dialog instance to bypass this filter entirely.
    """

    def eventFilter(self, watched, event):
        if event.type() != QEvent.Type.Polish:
            return False
        if not isinstance(watched, QDialog):
            return False
        if not watched.isWindow():
            return False
        if getattr(watched, "_csd_title_bar", None) is not None:
            return False
        if bool(getattr(watched, "_csd_decorating", False)):
            return False
        if bool(getattr(watched, "_csd_opt_out", False)):
            return False
        try:
            decorate_dialog(watched, title=_resolve_dialog_title(watched))
        except Exception:
            pass
        return False


def install_application_dialog_decorations(app: QApplication | None) -> None:
    """Install the app-wide auto-decoration filter (idempotent)."""
    if app is None or getattr(app, "_csd_filter_installed", False):
        return
    interceptor = _DialogDecorationInterceptor(app)
    app.installEventFilter(interceptor)
    app._csd_filter_installed = True
    app._csd_filter = interceptor
