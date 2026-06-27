"""Runtime check: tooltips on QTabBar items are routed through PathTooltip.

The static contract in tests/contracts/test_no_system_tooltips.py cannot
catch item-based tooltip APIs like ``QTabBar.setTabToolTip`` — they are
AST-indistinguishable from any other ``.setToolTip`` call. This test pumps
a synthetic ``QHelpEvent(ToolTip)`` through a QTabBar that has a per-tab
tooltip set, and asserts that the toolkit's application interceptor caught
it and forwarded the text to the custom PathTooltip bubble, instead of
letting Qt render a native tooltip.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QHelpEvent
from PySide6.QtWidgets import QApplication, QTabBar
from sli_ui_toolkit.ui.widgets.atomic.tooltips import (
    PathTooltip,
    install_application_tooltips,
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_tab_bar_tooltip_routes_through_path_tooltip(qapp):
    install_application_tooltips(qapp)

    bar = QTabBar()
    bar.addTab("First")
    bar.addTab("Second")
    bar.setTabToolTip(0, "First tab hint")
    bar.setTabToolTip(1, "Second tab hint")
    bar.resize(200, 32)
    bar.show()
    QApplication.processEvents()

    PathTooltip.get_instance().hide_tooltip()
    PathTooltip.get_instance()._pending_text = ""

    rect_second = bar.tabRect(1)
    local_pos = rect_second.center()
    global_pos = bar.mapToGlobal(local_pos)
    event = QHelpEvent(QEvent.Type.ToolTip, local_pos, global_pos)

    handled = QApplication.sendEvent(bar, event)

    assert handled, "Application interceptor must consume the ToolTip event"
    pending = PathTooltip.get_instance()._pending_text
    assert pending == "Second tab hint", (
        "QTabBar item tooltip must be resolved via tabAt() and forwarded to "
        f"PathTooltip; got pending text={pending!r}"
    )

    bar.deleteLater()
