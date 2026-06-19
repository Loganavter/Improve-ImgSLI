"""Main-window save action stays visibly labeled before translation refresh."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from ui.main_window.ui import Ui_ImageComparisonApp


def test_wide_main_window_buttons_have_initial_labels_and_expand():
    """Wide action buttons must not start as icon-only 36px controls."""
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    ui = Ui_ImageComparisonApp()

    ui.setupUi(window)

    assert getattr(ui.btn_save, "_text", "") == "Save Result"
    assert getattr(ui.btn_image1, "_text", "") == "Add Img(s) 1"
    assert getattr(ui.btn_image2, "_text", "") == "Add Img(s) 2"
    assert ui.btn_save.sizeHint().width() > ui.btn_quick_save.sizeHint().width()
    assert ui.btn_save.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert ui.btn_image1.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert ui.btn_image2.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

    window.deleteLater()
    app.processEvents()
