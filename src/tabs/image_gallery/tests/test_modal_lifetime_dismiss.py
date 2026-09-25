"""Modal lifetime (W1): gallery modals must not outlive the tab.

Asserts for each modal class (QuickLook, CleanReview): overlay visible ->
``ImageGalleryTab.on_deactivated()`` / ``on_session_closed()`` -> overlay
hidden. Plus missing-attr fail-open and the page-Hide watcher path.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from tabs.contract import TabContext
from tabs.image_gallery.tab import ImageGalleryTab
from tabs.image_gallery.ui.clean_review import CleanReviewOverlay
from tabs.image_gallery.ui.quick_look import QuickLookOverlay


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
    tab = ImageGalleryTab()
    tab._widget = page
    return tab, win, page


def _shown_overlay(qtbot, cls, win):
    overlay = cls(win)
    # NOTE: not qtbot-managed — child of win, dies with it at teardown.
    overlay.show_overlay()
    assert overlay.isVisible()
    return overlay


def test_quicklook_dismissed_on_deactivated(qapp, qtbot):
    tab, win, page = _make_tab_with_page(qtbot)
    overlay = _shown_overlay(qtbot, QuickLookOverlay, win)
    page._quick_look_overlay = overlay
    tab.on_deactivated(TabContext())
    assert not overlay.isVisible()


def test_clean_review_dismissed_on_deactivated(qapp, qtbot):
    tab, win, page = _make_tab_with_page(qtbot)
    overlay = _shown_overlay(qtbot, CleanReviewOverlay, win)
    page._clean_overlay = overlay
    tab.on_deactivated(TabContext())
    assert not overlay.isVisible()


def test_quicklook_dismissed_on_session_closed(qapp, qtbot):
    tab, win, page = _make_tab_with_page(qtbot)
    overlay = _shown_overlay(qtbot, QuickLookOverlay, win)
    page._quick_look_overlay = overlay
    tab.on_session_closed("other-session", TabContext())
    assert not overlay.isVisible()


def test_clean_review_dismissed_on_session_closed(qapp, qtbot):
    tab, win, page = _make_tab_with_page(qtbot)
    overlay = _shown_overlay(qtbot, CleanReviewOverlay, win)
    page._clean_overlay = overlay
    tab.on_session_closed("other-session", TabContext())
    assert not overlay.isVisible()


def test_missing_attrs_fail_open(qapp, qtbot):
    """No overlay attrs at all (and no window): lifecycle never raises."""
    tab = ImageGalleryTab()
    tab._widget = None
    tab.on_deactivated(TabContext())
    tab.on_session_closed("sess", TabContext())
    lonely = QWidget()
    qtbot.addWidget(lonely)
    tab._widget = lonely  # never shown: window() may be None, attrs missing
    tab.on_deactivated(TabContext())
    tab.on_session_closed("sess", TabContext())


def test_page_hide_dismisses_modals(qapp, qtbot):
    """Stack-switch path: explicit page hide dismisses without lifecycle."""
    from PySide6.QtWidgets import QStackedWidget

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
    tab = ImageGalleryTab()
    tab._widget = page
    tab._install_modal_lifetime_watch()
    quick = _shown_overlay(qtbot, QuickLookOverlay, win)
    clean = _shown_overlay(qtbot, CleanReviewOverlay, win)
    page._quick_look_overlay = quick
    page._clean_overlay = clean
    stack.setCurrentWidget(other)  # hides page -> watcher fires
    assert not quick.isVisible()
    assert not clean.isVisible()


def test_minimize_hide_does_not_dismiss(qapp, qtbot):
    """Ancestor-driven hides (window minimize) are not tab deactivation."""
    tab, win, page = _make_tab_with_page(qtbot)
    tab._install_modal_lifetime_watch()
    overlay = _shown_overlay(qtbot, QuickLookOverlay, win)
    page._quick_look_overlay = overlay
    win.hide()  # ancestor hide: page.isHidden() stays False
    assert not page.isHidden()
    # Not dismissed: explicit flag preserved (isVisible is ancestor-sensitive).
    assert not overlay.isHidden()
    win.show()
    assert overlay.isVisible()
