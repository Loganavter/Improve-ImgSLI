"""Synchronous settle for DOUBLE-mode panel limit relaxation.

``relax_panel_limits_for_double`` raises a panel's (and its scroll area's)
min/max so the shared DOUBLE height actually applies instead of being
silently clamped to the stale single-mode limits. The limits derive from
the computed panel geometry while the panel hosts a QLayout, so the
panel's own layout must re-run in the same call — otherwise the scroll
viewport lags one turn mid-drag.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.composite.list_panel import ListPanel
from ui.widgets.unified_list_picker.double_geometry import (
    relax_panel_limits_for_double,
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _make_panel():
    noop = lambda *args, **kwargs: None  # noqa: E731
    return ListPanel(
        1, 36, QFont(), lambda n: -1,
        noop, noop, noop, noop, noop, noop, None,
    )


def test_relax_panel_limits_settles_layout_synchronously(qapp):
    panel = _make_panel()
    panel.show()
    try:
        qapp.processEvents()
        assert panel.layout().activate() is False
        # Simulate the stale single-mode clamp on both the panel and its
        # scroll area, then grow to DOUBLE height.
        panel.setMaximumHeight(82)
        panel.scroll_area.setMaximumHeight(50)
        qapp.processEvents()
        relax_panel_limits_for_double(panel, 400)
        assert panel.maximumHeight() >= 400
        assert panel.layout().activate() is False
        qapp.processEvents()
        # Shrink direction: stale large minimums relaxed down.
        panel.setMinimumHeight(300)
        panel.scroll_area.setMinimumHeight(200)
        qapp.processEvents()
        relax_panel_limits_for_double(panel, 100)
        assert panel.minimumHeight() <= 100
        assert panel.layout().activate() is False
    finally:
        panel.deleteLater()
