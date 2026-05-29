"""FluentComboBox public API: standard item methods, type-to-search best-match,
and keyboard navigation over the filtered result set.

Dogma source: docs/dev/UI_TOOLKIT_LIBRARY.md.
"""

from __future__ import annotations

import os
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from sli_ui_toolkit.widgets import ComboBox

APP = QApplication.instance() or QApplication([])

def test_combobox_supports_common_item_api():
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

    APP.processEvents()

def test_combobox_type_to_search_prefers_best_match():
    combo = ComboBox()
    combo.addItems(["Arial", "Open Sans", "New Roman", "Roboto"])
    combo.show()
    combo.setFocus()
    APP.processEvents()

    QTest.keyClicks(combo, "ne")
    APP.processEvents()

    assert combo.searchText() == "ne"
    assert combo.currentText() == "New Roman"
    assert combo._expanded is True
    assert combo._visible_indices() == [2]

def test_combobox_keyboard_navigation_uses_filtered_results():
    combo = ComboBox()
    combo.addItems(["Arial", "New Roman", "Nerd Font", "Neo Sans", "Roboto"])
    combo.show()
    combo.setFocus()
    APP.processEvents()

    QTest.keyClicks(combo, "ne")
    APP.processEvents()

    assert combo.currentText() == "New Roman"
    assert combo._visible_indices() == [1, 2, 3]

    QTest.keyClick(combo, Qt.Key.Key_Down)
    APP.processEvents()
    assert combo.currentText() == "Nerd Font"

    QTest.keyClick(combo, Qt.Key.Key_Down)
    APP.processEvents()
    assert combo.currentText() == "Neo Sans"

    QTest.keyClick(combo, Qt.Key.Key_Enter)
    APP.processEvents()
    assert combo.currentText() == "Neo Sans"
    assert combo._expanded is False
    assert combo.searchText() == ""
