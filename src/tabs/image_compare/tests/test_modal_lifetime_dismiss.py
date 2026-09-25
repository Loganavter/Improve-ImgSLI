"""Modal lifetime (W1): PasteDirection overlays must not outlive the tab.

Covers all three open sites (clipboard service, duplicate, pending insert —
refs are discarded at open, so the tab sweeps its window): overlays visible
-> ``ImageCompareTab.on_deactivated()`` / ``on_session_closed()`` -> hidden.
Plus missing-window fail-open, foreign owner_tab guard, and page-Hide path.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from services.system.paste_direction_overlay import PasteDirectionOverlay
from tabs.contract import TabContext
from tabs.image_compare.tab import ImageCompareTab


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _make_tab_with_page(qtbot):
    win = QWidget()
    qtbot.addWidget(win)
    win.show()
    page = QWidget(win)
    page.show()
    tab = ImageCompareTab()
    tab._widget = page
    return tab, win, page


def _shown_overlay(qtbot, win, owner_tab=None):
    anchor = QLabel("canvas", parent=win)
    overlay = PasteDirectionOverlay(win, anchor, is_horizontal=False)
    if owner_tab is not None:
        overlay.setProperty("owner_tab", owner_tab)
    # NOTE: not qtbot-managed — child of win, dies with it at teardown.
    overlay.show_overlay()
    assert overlay.isVisible()
    return overlay


def test_all_three_sites_dismissed_on_deactivated(qapp, qtbot):
    """Clipboard + duplicate + pending-insert overlays all die on switch."""
    tab, win, page = _make_tab_with_page(qtbot)
    overlays = [_shown_overlay(qtbot, win) for _ in range(3)]
    tab.on_deactivated(TabContext())
    for overlay in overlays:
        assert not overlay.isVisible()


def test_all_three_sites_dismissed_on_session_closed(qapp, qtbot):
    tab, win, page = _make_tab_with_page(qtbot)
    overlays = [_shown_overlay(qtbot, win) for _ in range(3)]
    tab.on_session_closed("other-session", TabContext())
    for overlay in overlays:
        assert not overlay.isVisible()


def test_foreign_owner_tag_never_touched(qapp, qtbot):
    """An overlay tagged for another tab survives our deactivation."""
    tab, win, page = _make_tab_with_page(qtbot)
    foreign = _shown_overlay(qtbot, win, owner_tab="image_gallery")
    ours = _shown_overlay(qtbot, win, owner_tab="image_compare")
    tab.on_deactivated(TabContext())
    assert foreign.isVisible()
    assert not ours.isVisible()
    foreign.dismiss()


def test_missing_window_fail_open(qapp, qtbot):
    """No widget / detached widget: lifecycle never raises."""
    tab = ImageCompareTab()
    tab._widget = None
    tab.on_deactivated(TabContext())
    tab.on_session_closed("sess", TabContext())
    lonely = QWidget()
    qtbot.addWidget(lonely)
    tab._widget = lonely  # never shown: window() is None-friendly
    tab.on_deactivated(TabContext())
    tab.on_session_closed("sess", TabContext())


def test_page_hide_dismisses_paste_overlays(qapp, qtbot):
    """Stack-switch path: explicit page hide dismisses without lifecycle."""
    from PySide6.QtWidgets import QStackedWidget

    from tabs.image_compare.tab import _ModalLifetimeHideFilter

    win = QWidget()
    qtbot.addWidget(win)
    win.show()
    stack = QStackedWidget(win)
    page = QWidget()
    other = QWidget()
    stack.addWidget(page)
    stack.addWidget(other)
    stack.setCurrentWidget(page)
    win.show()
    tab = ImageCompareTab()
    tab._widget = page
    filt = _ModalLifetimeHideFilter(tab._dismiss_paste_overlays, page)
    page.installEventFilter(filt)
    overlay = _shown_overlay(qtbot, win)
    stack.setCurrentWidget(other)  # hides page -> watcher fires
    assert not overlay.isVisible()
