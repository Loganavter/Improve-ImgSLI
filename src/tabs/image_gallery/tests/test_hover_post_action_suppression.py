"""Post-action capsule suppression must cover owner-less (pool-recycled) cards.

Regression: grid ``_acquire_card`` builds cards without an owner, so
``_CardHoverFilter._owner`` is None for them — but ``_after_card_action``
stamps the 600 ms suppression on the real owner (controller). The Enter
path consulted only ``self._owner``, so after a reject rebuild shuffled a
new card under the stationary cursor its capsule popped up instantly,
defeating the post-action window (and the action closure captured None
instead of the controller).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card


def _ownerless_card(qtbot, item: GalleryItem):
    """Card built exactly like grid pool reuse: no owner passed."""
    parent = QWidget()
    qtbot.addWidget(parent)
    card = build_gallery_card(item, parent=parent)
    card._test_parent = parent  # strong ref: qtbot tracks via weakref only
    parent.resize(400, 300)
    parent.show()
    card.move(0, 0)
    card.show()
    # Park the cursor away: showing under a static cursor synthesizes a real
    # Enter that would fight the fake hover events below.
    try:
        QCursor.setPos(parent.mapToGlobal(QPoint(390, 290)))
        QApplication.processEvents()
    except Exception:
        pass
    return card


def _enter(card) -> None:
    filt = getattr(card, "_gallery_hover_filter", None)
    assert filt is not None
    filt.eventFilter(card, SimpleNamespace(type=lambda: QEvent.Type.Enter))


def test_suppression_holds_for_ownerless_card(qtbot) -> None:
    """Suppression stamped on the window controller blocks an owner-less card."""
    from tabs.image_gallery.ui.card.hover import _suppress_capsule

    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _ownerless_card(qtbot, item)
    filt = getattr(card, "_gallery_hover_filter", None)
    assert filt is not None and filt._owner is None

    controller = SimpleNamespace()
    card.window()._gallery_controller = controller  # type: ignore[attr-defined]
    _suppress_capsule(controller, ms=600)

    _enter(card)
    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is None or not flyout.isVisible()


def test_suppression_expiry_shows_for_ownerless_card(qtbot) -> None:
    """After the window expires the same owner-less card shows the capsule."""
    from tabs.image_gallery.ui.card.hover import _suppress_capsule

    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _ownerless_card(qtbot, item)

    controller = SimpleNamespace()
    card.window()._gallery_controller = controller  # type: ignore[attr-defined]
    _suppress_capsule(controller, ms=1)
    qtbot.wait(30)

    _enter(card)
    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is not None and flyout.isVisible()
    assert set(flyout._buttons.keys()) == {"make_best", "reject", "compare"}


def test_resolve_card_owner_prefers_hint_then_window(qtbot) -> None:
    """Owner resolution order: explicit hint > card attr > window controller."""
    from tabs.image_gallery.ui.card.hover import _resolve_card_owner

    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = _ownerless_card(qtbot, item)
    hint, stored, via_window = SimpleNamespace(), SimpleNamespace(), SimpleNamespace()
    card.window()._gallery_controller = via_window  # type: ignore[attr-defined]

    assert _resolve_card_owner(card, hint) is hint
    card._gallery_owner = stored  # type: ignore[attr-defined]
    assert _resolve_card_owner(card, None) is stored
    del card._gallery_owner
    assert _resolve_card_owner(card, None) is via_window


def test_suppression_stamped_before_triage_rebuild(qtbot, monkeypatch) -> None:
    """The post-action window must open before triage rebuilds the grid.

    Regression (live 2026-09-26): the rebuild recycles cards under the
    stationary cursor and Qt synthesizes Enter mid-rebuild — the stamp at
    the end of ``_after_card_action`` came ~50 ms too late, so the capsule
    re-showed instantly on the shuffled card. The handler stamps first.
    """
    from PySide6.QtWidgets import QWidget

    from tabs.image_gallery.ui.card import build_gallery_card
    from tabs.image_gallery.ui.card.hover import (
        _capsule_suppressed,
        show_gallery_card_flyout,
    )
    from tabs.image_gallery.use_cases import triage as _triage

    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    owner = SimpleNamespace(
        state=SimpleNamespace(items=[item], selected_paths=set(), selected_order=[]),
    )
    parent = QWidget()
    qtbot.addWidget(parent)
    card = build_gallery_card(item, parent=parent, owner=owner)
    card._test_parent = parent

    seen: dict = {}
    real_toggle = _triage.toggle_reject

    def _spy_toggle(o, p):  # type: ignore[no-untyped-def]
        seen["stamped"] = bool(_capsule_suppressed(o, card))
        return real_toggle(o, p)

    monkeypatch.setattr(_triage, "toggle_reject", _spy_toggle)
    show_gallery_card_flyout(card, owner)
    flyout = getattr(card, "_gallery_card_flyout", None)
    assert flyout is not None
    flyout.actionTriggered.emit("reject")
    assert seen.get("stamped") is True
