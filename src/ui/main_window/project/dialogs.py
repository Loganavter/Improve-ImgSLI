"""Project open/save file dialogs — attached Qt dialogs, never native.

**Native, through the XDG desktop portal** (owner decision 2026-10-28: "вернуть
нативный через портал" — the modern GNOME chooser). The portal chooser is a
separate application whose window the portal itself parents, so we keep the
native look *and* the stacking fix.

The failure this replaced (owner report 2026-10-28: after opening the image
export dialog, every later project file dialog appeared *under* the main window;
"в остальных случаях порядок появления верный") came from Qt's *in-process* GTK
dialog: a foreign window whose ``transient-for`` rides an exported parent surface
plus an xdg-activation grant we do not control. The documented family lives in
the internal notes on the help dialog opening below the main window and on the
flyout restore / xdg-activation notification: mutter's
``meta_window_show()`` places a window that maps with
``takes_focus_on_map == FALSE`` **just below the focused window** — i.e. behind
the app — unless the focused window is an ancestor of its transient chain (an
attached dialog is exempt). On GNOME Wayland the GTK/portal chooser is a
separate window whose ``transient-for`` is set through an *exported* parent
surface, and its ``GtkFileChooserDialog`` focuses itself; whether it ends up
above us then depends on an xdg-activation grant we do not control (Telegram
Desktop fights the same class by never depending on activation: it parents the
dialog to the visible active top-level and suppresses its own delayed
activation).

What stays from the fix: the dialog is parented to the **visible active**
top-level (not a stale/hidden one) and is **window-modal**, so whatever backend
answers, the compositor has an attached-dialog shape to place. The instance API
(not the static ``getSaveFileName``) keeps the parent/modality assertable — the
static helpers hide the widget entirely.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QWidget

if TYPE_CHECKING:
    from ui.main_window.project_io import MainWindowProjectIo


def _dialog_parent(owner: "MainWindowProjectIo") -> QWidget:
    """Visible active window, else the shell — never a hidden/dead one.

    An attached dialog is only safe when its parent is the live focused
    top-level; a parent whose window is hidden (or already destroyed) gives the
    compositor nothing to attach to and the dialog can map behind.
    """
    app = QApplication.instance()
    active = app.activeWindow() if app is not None else None
    if isinstance(active, QWidget):
        try:
            if active.isVisible():
                return active
        except RuntimeError:
            pass
    return owner._window


def make_file_dialog(owner: "MainWindowProjectIo", *, for_save: bool) -> QFileDialog:
    """Build the project file dialog (attached, Qt-drawn, window-modal)."""
    from services.io.project_io import PROJECT_FILE_EXTENSION

    dialog = QFileDialog(_dialog_parent(owner))
    # Native on purpose: with QT_QPA_PLATFORMTHEME=xdgdesktopportal (seeded in
    # __main__._configure_linux_desktop_integrations) this resolves to the
    # portal chooser. Never force DontUseNativeDialog here.
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, False)
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setNameFilter(
        owner._tr("menu.project_filter", "BlinkTable Project (*.blinktable *.imgsli)")
    )
    if for_save:
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setDefaultSuffix(PROJECT_FILE_EXTENSION.lstrip("."))
        dialog.selectFile(owner.project_start_path(for_save=True))
    else:
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setDirectory(owner.project_start_path(for_save=False))
    return dialog


def _choose(owner: "MainWindowProjectIo", *, for_save: bool) -> str | None:
    dialog = make_file_dialog(owner, for_save=for_save)
    try:
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        selected = dialog.selectedFiles()
    finally:
        dialog.deleteLater()
    return selected[0] if selected else None


def _choose_project_open_path(owner: "MainWindowProjectIo") -> str | None:
    return _choose(owner, for_save=False) or None


def _choose_project_save_path(owner: "MainWindowProjectIo") -> str | None:
    from services.io.project_io import PROJECT_FILE_EXTENSION, has_project_extension

    path = _choose(owner, for_save=True)
    if not path:
        return None
    if not has_project_extension(path):
        path = f"{path}{PROJECT_FILE_EXTENSION}"
    return path
