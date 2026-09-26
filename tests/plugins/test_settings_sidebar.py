"""Settings sidebar splitter + row elision.

Regression: nav row buttons refused to shrink below their text width
(horizontal ``Expanding`` honors ``minimumSizeHint``), so the sidebar host
wedged at the widest entry ("Сравнение изображений"), the splitter could
not narrow past it, and long labels clipped at the viewport instead of
eliding (toolkit ``IconListWidget`` rows now use horizontal ``Ignored``).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from plugins.settings.dialog import SettingsDialog
from sli_ui_toolkit.managers import UiScale


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _scale_one():
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def test_settings_sidebar_rows_shrink_when_splitter_narrows(qapp):
    dialog = SettingsDialog("ru", "dark", 60, 10, 200, False, True)
    dialog.show()
    qapp.processEvents()
    try:
        splitter = dialog.shell.splitter
        assert splitter is not None
        splitter.setSizes([120, 900])
        qapp.processEvents()
        # Design floor: the sidebar minimum width, not the content width.
        assert splitter.sizes()[0] == 200
        sidebar = dialog.sidebar
        assert sidebar.count() > 0
        widths = set()
        shrunk_below_hint = False
        for i in range(sidebar.count()):
            button = sidebar.row_button(i)
            assert button is not None
            # Shrunk into the narrowed host (8px host margins each side),
            # below the full-text hint — the elide precondition.
            assert button.width() <= 200 - 16, button.width()
            if button.width() < button.sizeHint().width():
                shrunk_below_hint = True
            widths.add(button.width())
        assert shrunk_below_hint, "no row shrank below its text width"
        assert len(widths) == 1, sorted(widths)
    finally:
        dialog.close()
