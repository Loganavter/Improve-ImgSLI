"""Gallery hover capsule must not steal keyboard focus (Del/Space/arrows stay grid's).

Regression: the card mini-capsule (``IconActionFlyout``) was shown with one
bare ``show()`` per card Enter, and stock ``BaseFlyout.show()`` grabs
keyboard focus into the pill + weakens StrongFocus ancestors (grid
included) until hide. Consequences while hovering:
- Space activated the focused pill button (e.g. make-best) instead of
  removing the selection from the grid;
- arrows navigated within the pill instead of moving gallery selection;
- Del lived or died by focus-propagation luck (stale/None focus after
  rebuild churn swallowed it).

Pinned here (headless):
- ``ensure_gallery_card_flyout`` marks the pill ``_skip_focus_grab``
  (which also skips nav-section registration, so arrows stay grid's);
- showing the capsule while a card has focus keeps focus + StrongFocus
  policies intact;
- Space with the capsule visible still removes the selection via the grid.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card.hover import (
    ensure_gallery_card_flyout,
    show_gallery_card_flyout,
)
from tabs.image_gallery.widget import ImageGalleryWidget


def _card(parent):
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    return build_gallery_card(item, parent=parent, owner=None)


def test_capsule_marks_skip_focus_grab(qtbot) -> None:
    win = QWidget()
    qtbot.addWidget(win)
    win.resize(800, 600)
    win.show()
    card = _card(win)
    flyout = ensure_gallery_card_flyout(card)
    assert flyout is not None
    assert getattr(flyout, "_skip_focus_grab", False) is True


def test_capsule_show_keeps_focus_and_policies(qtbot) -> None:
    items = [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i)
        for i, n in enumerate(("a.png", "b.png"))
    ]
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    w.rebuild_grid(items)
    card = w._grid_view.card_for(items[0].path)
    assert card is not None
    card.setFocus(Qt.FocusReason.MouseFocusReason)
    qtbot.wait(10)
    assert QApplication.focusWidget() is card
    grid_policy = w.focusPolicy()
    card_policy = card.focusPolicy()
    assert int(grid_policy) == int(Qt.FocusPolicy.StrongFocus)

    show_gallery_card_flyout(card, None)
    qtbot.wait(10)

    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is not None and flyout.isVisible()
    assert QApplication.focusWidget() is card
    assert w.focusPolicy() == grid_policy
    assert card.focusPolicy() == card_policy


def test_space_removes_selection_with_capsule_visible(qtbot) -> None:
    items = [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i)
        for i, n in enumerate(("a.png", "b.png", "c.png"))
    ]
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    w.rebuild_grid(items)
    ctrl = SimpleNamespace(
        state=SimpleNamespace(
            items=list(items),
            selected_paths={items[0].path, items[1].path},
            selected_order=[items[0].path, items[1].path],
        ),
        widget=w,
    )
    w._controller = ctrl  # type: ignore[attr-defined]
    card = w._grid_view.card_for(items[0].path)
    assert card is not None
    show_gallery_card_flyout(card, None)
    qtbot.wait(10)

    QTest.keyClick(w, Qt.Key.Key_Space)
    qtbot.wait(10)

    assert [str(it.path) for it in ctrl.state.items] == [str(items[2].path)]
