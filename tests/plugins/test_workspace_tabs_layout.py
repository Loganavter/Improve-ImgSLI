"""Main-window workspace tabs use the public toolkit component."""

from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QTabBar, QWidget

from sli_ui_toolkit.widgets import AdaptiveTabStrip
from ui.icon_manager import AppIcon
from ui.main_window.layouts import LayoutComposer
from ui.main_window.ui import Ui_ImageComparisonApp

APP = QApplication.instance() or QApplication([])


def _strip(parent=None) -> AdaptiveTabStrip:
    return AdaptiveTabStrip(
        add_icon=AppIcon.ADD,
        close_icon=AppIcon.CLOSE,
        parent=parent,
    )


def test_workspace_bar_is_toolkit_adaptive_tab_strip():
    window = QWidget()
    strip = _strip(window)
    ui = SimpleNamespace(
        main_window=SimpleNamespace(store=SimpleNamespace()),
        workspace_tabs=strip,
        btn_new_session=strip.add_button,
    )
    composer = LayoutComposer(ui)

    bar = composer._workspace_bar_widget(window)
    composer._configure_workspace_tabs()

    assert bar is strip
    assert ui.workspace_tabs_bar is strip
    assert strip.objectName() == "WorkspaceTabsBar"
    assert strip.tab_bar.objectName() == "WorkspaceTabs"
    assert ui.btn_new_session is strip.add_button


def test_sync_workspace_tabs_populates_toolkit_strip():
    ui = Ui_ImageComparisonApp()
    ui.workspace_tabs = _strip()
    sessions = [
        SimpleNamespace(id="one", title="First", session_type="image_compare"),
        SimpleNamespace(id="two", title="Second", session_type="multi_compare"),
    ]

    ui.sync_workspace_tabs(sessions, "two")

    assert ui.workspace_tabs.count() == 2
    assert ui.workspace_tabs.currentIndex() == 1
    assert ui.workspace_tabs.tabData(0) == "one"
    assert ui.workspace_tabs.tabData(1) == "two"
    assert all(
        ui.workspace_tabs.tabButton(index, QTabBar.ButtonPosition.RightSide)
        is not None
        for index in range(2)
    )


def test_single_workspace_tab_keeps_close_button():
    ui = Ui_ImageComparisonApp()
    ui.workspace_tabs = _strip()
    session = SimpleNamespace(
        id="only",
        title="Only",
        session_type="image_compare",
    )

    ui.sync_workspace_tabs([session], "only")

    assert ui.workspace_tabs.tabButton(
        0, QTabBar.ButtonPosition.RightSide
    ) is not None
