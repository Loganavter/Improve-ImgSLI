"""Closing Quick Look hands the keyboard cursor back to the card that opened it.

Bug (reproduced live): open Quick Look from a gallery card, close it (Esc /
veil / ✕ / direct hide) — focus is *not* returned to the opener; it is left at
the top of the window (the panel's own focus is simply dropped), so the user
has to walk back from the beginning.

Expected: closing returns the keyboard cursor to the card that opened the
panel; if that card is gone (rejected / hidden / rebuilt), the grid's own
current-or-nearest card; never the window's first focusable widget.

Falsifiable core (``test_close_returns_focus_to_opener_card``): on the unfixed
tree ``QApplication.focusWidget()`` after the close is ``None`` — the overlay's
focus was dropped and nothing replaced it (assert None is <opener card>).

Offscreen focus needs a live, pumped window (same idiom as
``test_gallery_keyboard._shown_widget``): ``QTest.qWait`` after each step so Qt
finishes its deferred focus delivery.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.widget import ImageGalleryWidget


def _items(*names: str) -> list[GalleryItem]:
    return [
        GalleryItem(path=Path(f"/gallery/{n}"), mtime_ns=i + 1)
        for i, n in enumerate(names)
    ]


def _open(qtbot, n: int = 3):
    w = ImageGalleryWidget()
    qtbot.addWidget(w)
    w.resize(1280, 800)
    w.show()
    qtbot.waitExposed(w)
    items = _items(*(f"i{i}.png" for i in range(n)))
    w.rebuild_grid(items)
    QTest.qWait(20)
    return w, items


def _card(w, item):
    return w._grid_view.card_for(item.path)


def _focus_card(w, item) -> None:
    card = _card(w, item)
    assert card is not None, "test setup: card missing"
    assert w._grid_view.focus_card(card) is True
    QTest.qWait(20)


def test_close_returns_focus_to_opener_card(qtbot) -> None:
    w, items = _open(qtbot)
    _focus_card(w, items[1])
    assert QApplication.focusWidget() is _card(w, items[1])

    w.show_quick_look(items[1])
    overlay = w._quick_look_overlay
    assert overlay.isVisible()
    QTest.qWait(20)  # let the panel's own focus bootstrap settle, as live

    overlay.dismiss()
    QTest.qWait(20)
    assert not overlay.isVisible()

    # The keyboard cursor is back on the card that opened the panel — not on
    # the window's first focusable widget (the reported symptom).
    assert QApplication.focusWidget() is _card(w, items[1])


def test_escape_close_returns_focus_to_opener_card(qtbot) -> None:
    w, items = _open(qtbot)
    _focus_card(w, items[2])

    w.show_quick_look(items[2])
    overlay = w._quick_look_overlay
    assert overlay.isVisible()
    QTest.qWait(20)  # let the panel's own focus bootstrap settle, as live

    QTest.keyClick(overlay, Qt.Key.Key_Escape)
    QTest.qWait(20)
    assert not overlay.isVisible()

    assert QApplication.focusWidget() is _card(w, items[2])


def test_close_falls_back_to_grid_when_opener_is_gone(qtbot) -> None:
    """Opener card rejected/rebuilt away → grid's own card, never window top."""
    w, items = _open(qtbot)
    _focus_card(w, items[1])

    w.show_quick_look(items[1])
    overlay = w._quick_look_overlay
    assert overlay.isVisible()
    QTest.qWait(20)  # let the panel's own focus bootstrap settle, as live

    # Rebuild without the opener: its card is recycled and gone.
    w.rebuild_grid(items[:1] + items[2:])
    QTest.qWait(20)
    assert _card(w, items[1]) is None

    overlay.dismiss()
    QTest.qWait(20)
    assert not overlay.isVisible()

    focused = QApplication.focusWidget()
    assert focused is not None
    # Landed inside the gallery grid, on a live card.
    assert w._grid_view.isAncestorOf(focused)
    assert focused in set(w._grid_view._cards_by_path.values())


def test_second_close_does_not_steal_focus(qtbot) -> None:
    """Idempotent: a second close must not yank focus back."""
    w, items = _open(qtbot)
    _focus_card(w, items[0])

    w.show_quick_look(items[0])
    overlay = w._quick_look_overlay
    QTest.qWait(20)  # let the panel's own focus bootstrap settle, as live
    overlay.dismiss()
    QTest.qWait(20)
    assert QApplication.focusWidget() is _card(w, items[0])

    # The user walked to another card; a stray re-close must not steal it.
    _focus_card(w, items[2])
    overlay.hide()
    QTest.qWait(20)
    assert QApplication.focusWidget() is _card(w, items[2])
