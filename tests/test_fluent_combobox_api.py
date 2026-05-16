from __future__ import annotations

import os
import sys

from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), os.pardir, "src"))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        "packages",
        "sli-ui-toolkit",
        "src",
    ),
)

from sli_ui_toolkit.widgets import ComboBox

def test_combobox_supports_common_item_api():
    app = QApplication.instance() or QApplication([])

    combo = ComboBox()
    combo.addItem("One", 1)
    combo.addItems(["Two", "Three"])
    combo.setItemData(1, 2)
    combo.insertItem(1, "One and half", 15)

    assert combo.count() == 4
    assert combo.items() == [
        ("One", 1),
        ("One and half", 15),
        ("Two", 2),
        ("Three", None),
    ]

    combo.setItemText(3, "Three updated")
    combo.setCurrentData(15)
    assert combo.currentIndex() == 1
    assert combo.currentText() == "One and half"

    combo.removeItem(1)
    assert combo.count() == 3
    assert combo.findText("One and half") == -1
    assert combo.itemText(2) == "Three updated"

    app.processEvents()
