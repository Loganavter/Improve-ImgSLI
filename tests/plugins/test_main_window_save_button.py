"""Image-compare tab's save action stays visibly labeled before translation refresh.

``btn_save``/``btn_image1``/``btn_image2`` are built by
``ImageComparePrimitivesFactory`` onto the tab-owned ``ImageCompareWidget``
(see ``tabs/image_compare/ui/primitives.py``), not by the host
``Ui_ImageComparisonApp`` — the host only owns the workspace chrome around
the active tab's page. So this test assembles the real tab page the same
way ``ImageCompareTab.assemble_host_page`` does, instead of reading these
buttons off the host UI directly.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from tabs.image_compare.tab import ImageCompareTab
from ui.main_window.ui import Ui_ImageComparisonApp


def test_wide_main_window_buttons_have_initial_labels_and_expand():
    """Wide action buttons must not start as icon-only 36px controls."""
    app = QApplication.instance() or QApplication([])
    window = QWidget()
    ui = Ui_ImageComparisonApp()
    ui.setupUi(window)

    tab = ImageCompareTab()
    tab.create_page(window, None)
    tab.assemble_host_page(ui)
    page = tab.widget

    assert getattr(page.btn_save, "_text", "") == "Save Result"
    assert getattr(page.btn_image1, "_text", "") == "Add Img(s) 1"
    assert getattr(page.btn_image2, "_text", "") == "Add Img(s) 2"
    assert page.btn_save.sizeHint().width() > page.btn_quick_save.sizeHint().width()
    assert page.btn_save.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert page.btn_image1.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert page.btn_image2.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding

    window.deleteLater()
    app.processEvents()
