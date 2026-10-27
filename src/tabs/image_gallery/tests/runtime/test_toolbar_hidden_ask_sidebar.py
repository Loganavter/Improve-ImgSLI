"""The Ask-sidebar toolbar button is HIDDEN (unfinished feature, owner 2026-10-27).

The button still exists (the wiring, tooltip setters, toggle signal and the
tab-level panel are untouched so re-exposing it is one line), but it must not be
offered to the user: the Ask surface is not finished.

Red-before on this commit's base: the button was visible in the toolbar row.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_the_ask_sidebar_button_is_not_offered(qapp):
    from tabs.image_gallery.ui.toolbar import GalleryToolbar

    bar = GalleryToolbar()
    btn = bar.ask_sidebar_button
    assert btn is not None, "the widget must stay (re-exposing is one line)"
    assert btn.objectName() == "gallery_toolbar_ask_sidebar"
    assert btn.isVisibleTo(bar) is False, (
        "the Ask sidebar is unfinished — its button must not be visible"
    )
    # Hidden, not destroyed: the toggle wiring still works for a future wave.
    assert hasattr(bar, "askSidebarToggled")
