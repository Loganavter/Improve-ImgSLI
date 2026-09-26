"""Card delete ✕ button: round hover-only badge overhanging the corner.

Reject (capsule ✕) only toggles the rejected flag (dim + strike-through,
no corner mode switch); the top-right ✕ deletes the card via
``remove_from_grid`` (file on disk stays) + HUD notice.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QPoint, QEvent
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card


def _owner(items: list[GalleryItem]) -> SimpleNamespace:
    notes: list = []
    hud = SimpleNamespace(notify=lambda text, timeout_ms=2500: notes.append(text))
    owner = SimpleNamespace(
        state=SimpleNamespace(items=list(items), selected_paths=set(), selected_order=[]),
        _selection_hud=hud,
    )
    owner.notes = notes
    return owner


def _card(qtbot, item: GalleryItem, owner: SimpleNamespace):
    parent = QWidget()
    qtbot.addWidget(parent)
    card = build_gallery_card(item, parent=parent, owner=owner)
    card._test_parent = parent  # strong ref: qtbot tracks via weakref only
    parent.resize(400, 300)
    parent.show()
    card.move(0, 0)
    card.show()
    # Park the cursor outside the card: Qt synthesizes real Enter/Leave for
    # whatever sits under it, which would fight the fake hover events below.
    # Showing the card under the static cursor synthesizes an Enter, so drain
    # one event round for a deterministic idle state.
    try:
        QCursor.setPos(parent.mapToGlobal(QPoint(390, 290)))
        QApplication.processEvents()
    except Exception:
        pass
    return card


def _park_over(btn, card) -> None:
    """Move the virtual cursor onto the badge WITHOUT delivering events."""
    try:
        host = btn.parent()
        center = btn.pos() + QPoint(btn.width() // 2, btn.height() // 2)
        QCursor.setPos(host.mapToGlobal(center))
    except Exception:
        pass


def _delete_button(card):
    # Host-level button (card clips children to its rect — no overhang there).
    btn = getattr(card, "_gallery_delete_btn", None)
    assert btn is not None
    return btn


def _hover(card, enter: bool = True) -> None:
    filt = getattr(card, "_gallery_hover_filter", None)
    assert filt is not None
    kind = QEvent.Type.Enter if enter else QEvent.Type.Leave
    filt.eventFilter(card, SimpleNamespace(type=lambda kind=kind: kind))


def _click(btn) -> None:
    try:
        btn.click()
    except Exception:
        btn.clicked.emit()


def test_delete_button_hover_only(qtbot) -> None:
    """Hidden idle; real card-hover shows it (round badge, overhang corner)."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    assert not btn.isVisible()
    _hover(card, enter=True)
    assert btn.isVisible()
    pos = btn.pos()
    assert pos.x() + btn.width() // 2 == card.pos().x() + card.width()
    assert pos.y() + btn.height() // 2 == card.pos().y()


def test_delete_button_hides_after_leave(qtbot) -> None:
    """Leave hides on the same tick as the capsule (no linger)."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    _hover(card, enter=True)
    assert btn.isVisible()
    _hover(card, enter=False)
    assert not btn.isVisible()


def test_delete_button_hover_shows(qtbot) -> None:
    """Hovering the badge itself shows it (card-or-badge hover)."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    assert not btn.isVisible()
    filt = getattr(card, "_gallery_delete_hover_filter", None)
    assert filt is not None
    filt.eventFilter(btn, SimpleNamespace(type=lambda: QEvent.Type.Enter))
    assert btn.isVisible()


def test_card_leave_toward_badge_keeps_visible(qtbot) -> None:
    """Leaving the card onto the overhang half keeps the badge (no flicker)."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    _hover(card, enter=True)
    assert btn.isVisible()
    _park_over(btn, card)
    _hover(card, enter=False)
    assert btn.isVisible()


def test_badge_leave_outside_hides(qtbot) -> None:
    """Leaving the badge anywhere but the card hides immediately."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    _hover(card, enter=True)
    assert btn.isVisible()
    filt = getattr(card, "_gallery_delete_hover_filter", None)
    assert filt is not None
    filt.eventFilter(btn, SimpleNamespace(type=lambda: QEvent.Type.Enter))
    assert btn.isVisible()
    filt.eventFilter(btn, SimpleNamespace(type=lambda: QEvent.Type.Leave))
    assert not btn.isVisible()


def test_hover_x_then_card_keeps_visible(qtbot) -> None:
    """Card Enter cancels the hide scheduled by the badge Leave.

    Regression: hover ✕ → move onto card → ✕ vanished after ~200 ms (the
    X-Leave hide was never cancelled by the card Enter).
    """
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    _hover(card, enter=True)
    assert btn.isVisible()
    filt = getattr(card, "_gallery_delete_hover_filter", None)
    assert filt is not None
    filt.eventFilter(btn, SimpleNamespace(type=lambda: QEvent.Type.Leave))
    _hover(card, enter=True)
    qtbot.wait(300)
    assert btn.isVisible()


def test_capsule_and_badge_hide_show_together(qtbot) -> None:
    """Card↔badge travel keeps both; leaving both hides both on one tick."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    btn = _delete_button(card)
    _hover(card, enter=True)
    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is not None and flyout.isVisible()
    assert btn.isVisible()
    # Travel onto the badge: both stay.
    _park_over(btn, card)
    _hover(card, enter=False)
    assert btn.isVisible()
    assert flyout.isVisible()
    # Leave outward from the badge: both drop together.
    try:
        from PySide6.QtGui import QCursor

        QCursor.setPos(card._test_parent.mapToGlobal(QPoint(390, 290)))
    except Exception:
        pass
    filt = getattr(card, "_gallery_delete_hover_filter", None)
    assert filt is not None
    filt.eventFilter(btn, SimpleNamespace(type=lambda: QEvent.Type.Leave))
    assert not btn.isVisible()
    assert not flyout.isVisible()


def test_delete_button_visible_while_rejected(qtbot) -> None:
    """No corner mode switch: rejected cards keep the same delete ✕.

    Rejected is signalled by dim + strike-through only; the hover-only
    delete button shows for rejected cards exactly like for normal ones.
    """
    from tabs.image_gallery.ui.card import update_gallery_card

    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1, rejected=True)
    card = _card(qtbot, item, _owner([item]))
    _hover(card, enter=True)
    assert _delete_button(card).isVisible()
    item.rejected = False
    update_gallery_card(card, item)
    _hover(card, enter=True)
    assert _delete_button(card).isVisible()


def test_delete_button_removes_card_and_notifies(qtbot) -> None:
    """Clicking ✕ removes the card from state and names it in the HUD."""
    a = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    b = GalleryItem(path=Path("/gallery/b.png"), mtime_ns=2)
    owner = _owner([a, b])
    card = _card(qtbot, a, owner)
    _hover(card, enter=True)
    _click(_delete_button(card))
    assert [str(it.path) for it in owner.state.items] == [str(b.path)]
    assert owner.notes == ["Removed a.png"]


def test_delete_button_paints_outside_card(qtbot) -> None:
    """Pixel witness: red glyph pixels exist beyond the card rect."""
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _card(qtbot, item, _owner([item]))
    _hover(card, enter=True)
    btn = _delete_button(card)
    assert btn.isVisible()
    QApplication.processEvents()
    QApplication.processEvents()
    px = card._test_parent.grab().toImage()
    n = 0
    for x in range(card.width() + 1, card.width() + 12):
        for y in range(0, 12):
            c = px.pixelColor(x, y)
            if c.red() > 120 and c.red() > c.green() + 40 and c.red() > c.blue() + 40:
                n += 1
    assert n > 0
