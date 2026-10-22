"""The activity pulse repaints the PILL, not the whole card.

Owner report 2026-10-22, item 6 (grid scrolling lags in the AI gallery). The
pulse repaints every active card at ~12 fps (spinner) and every frame of a done
fade; a full ``card.update()`` re-runs the cover-pixmap rescale, the dots and
the badge for a ~40x18 px change. In the AI gallery every queued card is active
at once, so this is a constant full-card repaint storm on the same GUI thread
that scrolls the grid.

Measured baseline on a private lease (36-image series, 40 wheel notches): a
notch during analysis took ~3x the idle time. This test pins the mechanism: the
painter stashes the pill rect on the card and the pulse repaints exactly that
rect; a card without the stash (first paint) still gets a full update, and an
invisible card is not repainted at all.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF

from tabs.image_gallery.models import ActivityPhase, GalleryItem
from tabs.image_gallery.ui.card import build_gallery_card
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.card.activity_pill import paint_item_activity
from tabs.image_gallery.services.activity import set_activity


def _card(qapp, *, show: bool = True):
    item = GalleryItem(path=Path("/gallery/a.png"), mtime_ns=1)
    card = build_gallery_card(item, parent=None, mode="camera")
    card.resize(250, 170)
    if show:
        card.show()
        qapp.processEvents()
    return item, card


def _spy_update(card) -> list:
    calls: list = []
    card.update = lambda *a: calls.append(a)  # type: ignore[method-assign]
    return calls


def test_the_painter_stashes_the_pill_rect(qapp) -> None:
    from PySide6.QtGui import QPainter, QPixmap

    item, card = _card(qapp)
    set_activity(item, ActivityPhase.QUEUED, "ai")
    pix = QPixmap(card.size())
    painter = QPainter(pix)
    try:
        paint_item_activity(painter, card, QRectF(8, 8, 234, 140), corner="top_right")
    finally:
        painter.end()
    rect = getattr(card, "_gallery_activity_rect", None)
    assert rect is not None and rect.width() > 0 and rect.height() > 0
    assert rect.width() < card.width(), "the pill is a small corner region"
    assert rect.height() < card.height()


def test_the_pulse_repaints_only_the_stashed_rect(qapp) -> None:
    item, card = _card(qapp)
    card._gallery_activity_rect = QRectF(150, 10, 60, 18)
    calls = _spy_update(card)
    pulse = ActivityPulse()
    pulse.sync(card)
    assert calls, "the pulse must repaint the live pill"
    arg = calls[-1][0] if calls[-1] else None
    assert arg is not None, "a stashed pill rect must become a partial update"
    assert arg.width() < card.width() and arg.height() < card.height()


def test_a_card_without_a_stash_falls_back_to_a_full_update(qapp) -> None:
    item, card = _card(qapp)
    calls = _spy_update(card)
    pulse = ActivityPulse()
    pulse.sync(card)
    assert calls and calls[-1] == ()


def test_an_invisible_card_is_not_repainted(qapp) -> None:
    item, card = _card(qapp, show=False)
    card._gallery_activity_rect = QRectF(150, 10, 60, 18)
    calls = _spy_update(card)
    pulse = ActivityPulse()
    pulse.sync(card)  # the card was never shown
    assert calls == [], "a hidden card must not burn a repaint"
