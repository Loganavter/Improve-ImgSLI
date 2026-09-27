"""Gallery hover capsule must not kick window activation (no busy cursor).

Regression for the Wayland busy-cursor storm: the card mini-capsule
(``IconActionFlyout``, group ``gallery_card``) is shown with one bare
``show()`` per card Enter — and cards also sweep under a stationary
cursor during grid scroll. ``BaseFlyout.show()`` used to call
``window.activateWindow()`` on every such show whenever Qt reported the
window inactive (the common Wayland mid-scroll state); each call mints
an xdg-activation request with a stale token and the compositor answers
the storm with busy/loading cursor feedback (MC-zoom precedent, see
``test_mc_zoom_no_busy_cursor.py``).

Pinned here (headless; live cursor check stays manual):
- ``ensure_gallery_card_flyout`` marks the pill ``_no_window_activate``;
- a hover-frequency show/hide series with the window forced inactive
  (Wayland scroll state) issues zero ``activateWindow`` calls and leaves
  ``QApplication.overrideCursor()`` empty;
- the capsule still toggles visible (no behavior loss).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card.hover import ensure_gallery_card_flyout


def _card(parent):
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    return build_gallery_card(item, parent=parent, owner=None)


def test_capsule_marks_no_window_activate(qtbot) -> None:
    win = QWidget()
    qtbot.addWidget(win)
    win.resize(800, 600)
    win.show()
    card = _card(win)
    flyout = ensure_gallery_card_flyout(card)
    assert flyout is not None
    assert getattr(flyout, "_no_window_activate", False) is True


def test_capsule_hover_series_issues_no_activation(qtbot, monkeypatch) -> None:
    win = QWidget()
    qtbot.addWidget(win)
    win.resize(800, 600)
    win.show()
    card = _card(win)
    card.resize(200, 200)
    card.show()
    flyout = ensure_gallery_card_flyout(card)
    assert flyout is not None

    calls: list[str] = []
    # Wayland mid-scroll report: visible window, Qt says inactive.
    monkeypatch.setattr(win, "isActiveWindow", lambda: False)
    monkeypatch.setattr(
        win, "activateWindow", lambda *a, **k: calls.append("activate")
    )

    for _ in range(12):
        # What show_gallery_card_flyout does per card Enter (hover.py).
        flyout.setParent(card)
        try:
            flyout.update_state()
        except Exception:
            pass
        flyout.move(10, 10)
        flyout.show()
        assert flyout.isVisible()
        flyout.hide()

    assert calls == []
    assert QApplication.overrideCursor() is None
