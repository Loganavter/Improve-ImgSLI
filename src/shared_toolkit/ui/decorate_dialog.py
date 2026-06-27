"""App-side wrapper around toolkit `decorate_dialog`.

Reads the `use_custom_decorations` QSettings flag and resolves AppIcon-named
window-control icons before delegating to ``sli_ui_toolkit.decorate_dialog``.

Also installs an application-wide event filter that auto-decorates any
``QDialog`` / ``QMessageBox`` that's about to be shown for the first time —
otherwise error/warning popups would slip through with the OS native frame
even when the user opted into custom decorations.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from sli_ui_toolkit import CustomTitleBar, decorate_dialog as _toolkit_decorate_dialog

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


def _read_use_custom_decorations_setting() -> bool:
    try:
        from PySide6.QtCore import QSettings
        qs = QSettings("improve-imgsli", "improve-imgsli")
        if not qs.contains("use_custom_decorations"):
            return True
        return str(qs.value("use_custom_decorations")).lower() == "true"
    except Exception:
        return True


def decorate_dialog(
    dialog: QDialog,
    *,
    title: str = "",
    show_minimize: bool = False,
    show_maximize: bool = False,
    show_close: bool = True,
) -> CustomTitleBar | None:
    if not _read_use_custom_decorations_setting():
        return None

    from ui.icon_manager import AppIcon, get_app_icon

    return _toolkit_decorate_dialog(
        dialog,
        title=title,
        minimize_icon=get_app_icon(AppIcon.MINIMIZE),
        maximize_icon=get_app_icon(AppIcon.MAXIMIZE),
        restore_icon=get_app_icon(AppIcon.RESTORE),
        close_icon=get_app_icon(AppIcon.WINDOW_CLOSE),
        show_minimize=show_minimize,
        show_maximize=show_maximize,
        show_close=show_close,
    )


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
