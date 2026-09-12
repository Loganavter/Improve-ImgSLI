"""Auto-decoration of top-level QDialog/QMessageBox.

Every ad-hoc dialog (including ``QMessageBox.warning`` and friends) must end
up with a CustomTitleBar via the shared ``decorate_dialog`` wrapper —
otherwise error popups slip through with the OS native frame. The
auto-installer hooks ``QEvent.Type.Polish`` which fires before the window is
mapped onto the screen. Client-side decorations are always enabled.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from shared_toolkit.ui.decorate_dialog import (
    CUSTOM_DECORATION_RESIZE_MARGIN,
    configure_custom_decoration_resize_margin,
    install_application_dialog_decorations,
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_qmessagebox_gets_auto_decorated(qapp):
    install_application_dialog_decorations(qapp)

    box = QMessageBox()
    box.setText("error")
    box.setWindowTitle("oops")

    box.ensurePolished()
    QApplication.processEvents()

    title_bar = getattr(box, "_csd_title_bar", None)
    assert title_bar is not None, "QMessageBox must be auto-decorated"
    box.deleteLater()


def test_already_decorated_dialog_skipped(qapp):
    install_application_dialog_decorations(qapp)

    dlg = QDialog()
    dlg._csd_title_bar = "sentinel"
    dlg.ensurePolished()
    QApplication.processEvents()

    assert (
        dlg._csd_title_bar == "sentinel"
    ), "filter must not clobber existing decoration"
    dlg.deleteLater()


def test_opt_out_dialog_skipped(qapp):
    install_application_dialog_decorations(qapp)

    dlg = QDialog()
    dlg._csd_opt_out = True
    dlg.ensurePolished()
    QApplication.processEvents()

    assert getattr(dlg, "_csd_title_bar", None) is None
    dlg.deleteLater()


def test_custom_decoration_resize_margin_is_widened():
    from sli_ui_toolkit.ui.windows import frameless

    previous = frameless.RESIZE_MARGIN
    try:
        frameless.RESIZE_MARGIN = 4
        configure_custom_decoration_resize_margin()
        assert frameless.RESIZE_MARGIN == CUSTOM_DECORATION_RESIZE_MARGIN == 8
    finally:
        frameless.RESIZE_MARGIN = previous
