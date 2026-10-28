"""The still-image export dialog must be a plain non-modal top-level window.

Owner bug (2026-10-28): "make the export dialog behave like the video editor —
non-modal, the window moves itself and does not grab the main one". The cause is
not Qt layout code: **mutter** treats a *modal* transient as an attached dialog
and redirects a move grab to its toplevel transient-for window
(``meta_window_is_attached_dialog(window) && meta_grab_op_is_moving`` →
``grab_window = get_toplevel_transient_for(window)``, mutter 2014-05-02), so
dragging the export dialog dragged the main window. The video editor escapes it
because it declares itself non-modal (``setModal(False)`` +
``setWindowModality(NonModal)``) and is shown with ``show()``; the export dialog
was ``exec()``-ed — application-modal by construction.

Red-before, all three tests:

* the non-modal test fails with ``ApplicationModal`` recorded while the dialog
  is open (and ``show_export_dialog`` returns a ``(code, options)`` tuple
  instead of the dialog);
* the accept/reject tests cannot even call the API — ``show_export_dialog``
  had no ``on_finished`` parameter, so the export result was only obtainable by
  blocking.

The probes run from a ``QTimer`` so even a modal implementation terminates
instead of hanging the suite.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import shiboken6 as sip
from PySide6.QtCore import QEvent, QCoreApplication, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from resources.translations import add_i18n_root


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _state():
    from domain.types import Color
    from plugins.export.models import ExportDialogState

    add_i18n_root(Path("src/plugins/export/resources/i18n"))
    return ExportDialogState(
        current_language="en",
        output_dir="/tmp",
        favorite_dir=None,
        last_format="PNG",
        quality=95,
        png_compress_level=9,
        fill_background=True,
        background_color=Color(255, 255, 255, 255),
        comment_text="",
        comment_keep_default=False,
        resolution_scale=1.0,
        virtual_canvas_active=True,
    )


def _manager(qapp):
    from ui.managers.dialog_manager import DialogManager

    shell = QWidget()
    shell.resize(320, 200)
    shell.show()
    qapp.processEvents()
    return DialogManager(SimpleNamespace(parent_widget=shell)), shell


def _visible_export_dialogs() -> list:
    return [
        w
        for w in QApplication.topLevelWidgets()
        if w.objectName() == "ExportDialog" and w.isVisible()
    ]


def test_export_dialog_opens_non_modal_and_shell_stays_interactive(qapp):
    manager, shell = _manager(qapp)
    probes: list[tuple] = []

    def probe() -> None:
        dialogs = _visible_export_dialogs()
        assert dialogs, "the export dialog never became visible"
        dialog = dialogs[0]
        probes.append(
            (
                dialog.isModal(),
                dialog.windowModality(),
                # The real "is the main window blocked" signal: a modal dialog
                # is registered as the application's modal widget. A widget's
                # own isEnabled() is NOT affected by modality, so asserting it
                # would prove nothing.
                QApplication.activeModalWidget(),
                QApplication.modalWindow(),
            )
        )
        dialog.reject()

    QTimer.singleShot(0, probe)
    dialog = manager.show_export_dialog(
        _state(), preview_image=None, suggested_filename="out"
    )

    returned_live = dialog is not None and hasattr(dialog, "isModal")
    qapp.processEvents()

    assert probes, "the export dialog never appeared"
    is_modal, modality, modal_widget, modal_window = probes[0]
    assert is_modal is False, "a modal transient is an attached dialog for mutter"
    assert modality == Qt.WindowModality.NonModal
    assert modal_widget is None, "no modal dialog may be active while exporting"
    assert modal_window is None, "the export dialog must not be the modal window"

    assert returned_live, (
        "show_export_dialog must return the live dialog; it used to return "
        "(code, options) from a blocking exec()"
    )

    if sip.isValid(dialog):
        assert dialog.isModal() is False
        assert dialog.windowModality() == Qt.WindowModality.NonModal
        assert dialog.windowType() & Qt.WindowType.Window
    shell.close()
    shell.deleteLater()
    qapp.processEvents()


def test_accepted_reports_export_options_exactly_once(qapp):
    manager, shell = _manager(qapp)
    calls: list[tuple] = []

    dialog = manager.show_export_dialog(
        _state(),
        preview_image=None,
        suggested_filename="out",
        on_finished=lambda code, options: calls.append((code, options)),
    )
    dialog.edit_dir.setText("/tmp/out")
    dialog.edit_name.setText("shot")
    dialog.accept()
    qapp.processEvents()

    assert len(calls) == 1, f"continued {len(calls)} times, expected once"
    code, options = calls[0]
    assert code == QDialog.DialogCode.Accepted
    assert options, "an accepted dialog must hand over a non-empty options dict"
    assert options["file_name"] == "shot"
    assert options["output_dir"] == "/tmp/out"

    shell.close()
    shell.deleteLater()
    qapp.processEvents()


def test_cancel_reports_rejected_without_options_and_leaves_no_dialog(qapp):
    manager, shell = _manager(qapp)
    calls: list[tuple] = []

    dialog = manager.show_export_dialog(
        _state(),
        preview_image=None,
        suggested_filename="out",
        on_finished=lambda code, options: calls.append((code, options)),
    )
    dialog.reject()
    qapp.processEvents()
    # Deferred deletes only run on an explicit flush off the main loop's return.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert len(calls) == 1
    code, options = calls[0]
    assert code == QDialog.DialogCode.Rejected
    assert options == {}, "cancel carries no export options — nothing to write"

    assert not sip.isValid(dialog), (
        "the dialog must not linger after the user cancelled: the manager "
        "deleteLater()s it once on_finished has run"
    )
    assert manager._open_export_dialogs == []

    shell.close()
    shell.deleteLater()
    qapp.processEvents()
