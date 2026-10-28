"""The project file dialog must be an ATTACHED Qt dialog, never native.

Owner report 2026-10-28: after opening the image export dialog, every later
project file dialog (File → Save/Save As **and** Open) appeared *under* the main
window; "в остальных случаях порядок появления верный". The documented family is
`docs/dev/platform/investigations/help-dialog-opens-below-main-window.md`:
mutter's ``meta_window_show()`` puts a window that maps without focus **just
below the focused window** unless the focused window is an ancestor of its
transient chain. A native GTK/portal chooser is a separate window whose
transient-for depends on an exported parent surface and on an xdg-activation
grant we do not control.

So the dialogs are built as ``DontUseNativeDialog`` ``QFileDialog`` children of
the visible active top-level, window-modal — the Settings shape ("attached
dialogs stay above their parent"). The static ``QFileDialog.getSaveFileName``
helpers could not even be asserted: they hide the widget.

Red-before: on the previous code this module built no dialog object at all (the
static helpers), so ``make_file_dialog`` did not exist and the GTK chooser had
no parent/modal properties to hold on to.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from ui.main_window.project.dialogs import make_file_dialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class _Owner:
    """Only the surface ``make_file_dialog`` reads."""

    def __init__(self, window: QWidget, start: str) -> None:
        self._window = window
        self._start = start

    def _tr(self, _key: str, default: str = "") -> str:
        return default

    def project_start_path(self, *, for_save: bool) -> str:
        return self._start


def _owner(qapp, tmp_path: Path) -> tuple[_Owner, QWidget]:
    shell = QWidget()
    shell.setObjectName("Shell")
    shell.resize(800, 600)
    shell.show()
    qapp.processEvents()
    return _Owner(shell, str(tmp_path / "Untitled.blinktable")), shell


def test_save_dialog_is_an_attached_qt_dialog(qapp, tmp_path):
    owner, shell = _owner(qapp, tmp_path)
    dialog = make_file_dialog(owner, for_save=True)
    try:
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog) is True, (
            "a native chooser maps without a transient we control (mutter then "
            "stacks it under the main window)"
        )
        assert dialog.windowModality() == Qt.WindowModality.WindowModal, (
            "an attached (window-modal) dialog is the shape mutter keeps above "
            "its parent"
        )
        assert dialog.parent() is shell, "the dialog must be transient for the live shell"
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptSave
        assert dialog.fileMode() == QFileDialog.FileMode.AnyFile
        assert dialog.defaultSuffix() == "blinktable"
        selected = dialog.selectedFiles()
        assert selected and selected[0].endswith("Untitled.blinktable"), selected
    finally:
        dialog.close()
        dialog.deleteLater()
        shell.close()
        shell.deleteLater()


def test_open_dialog_targets_an_existing_project_file(qapp, tmp_path):
    owner, shell = _owner(qapp, tmp_path)
    owner._start = str(tmp_path)
    dialog = make_file_dialog(owner, for_save=False)
    try:
        assert dialog.testOption(QFileDialog.Option.DontUseNativeDialog) is True
        assert dialog.windowModality() == Qt.WindowModality.WindowModal
        assert dialog.parent() is shell
        assert dialog.acceptMode() == QFileDialog.AcceptMode.AcceptOpen
        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
    finally:
        dialog.close()
        dialog.deleteLater()
        shell.close()
        shell.deleteLater()
