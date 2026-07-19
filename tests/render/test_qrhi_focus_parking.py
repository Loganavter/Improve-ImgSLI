"""Keyboard focus must not stick on QRhiWidget hosts (Wayland/Vulkan nudge)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

from ui.widgets.canvas.rhi_focus import park_keyboard_focus_off_qrhi


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_park_moves_focus_from_qrhi_to_focusable_ancestor(qapp):
    shell = QWidget()
    shell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    container = QWidget(shell)  # NoFocus by default
    canvas = QRhiWidget(container)
    canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    shell.show()
    canvas.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()
    assert isinstance(QApplication.focusWidget(), QRhiWidget)

    assert park_keyboard_focus_off_qrhi(canvas) is True
    QApplication.processEvents()
    assert QApplication.focusWidget() is shell

    shell.close()


def test_park_noop_when_focus_already_off_qrhi(qapp):
    shell = QWidget()
    shell.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    shell.show()
    shell.setFocus(Qt.FocusReason.OtherFocusReason)
    QApplication.processEvents()

    assert park_keyboard_focus_off_qrhi() is False
    assert QApplication.focusWidget() is shell

    shell.close()
