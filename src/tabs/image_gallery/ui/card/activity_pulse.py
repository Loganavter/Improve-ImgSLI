"""Shared repaint driver for activity pills — one QTimer per grid.

Only cards whose item is in an active phase (or fading out after ``done``)
are tracked and repainted. Idle cards are never registered, so they never
repaint from this driver. ``done`` runs one bounded ``QVariantAnimation``
per card: hold ``DONE_LINGER_MS``, fade over ``DONE_FADE_MS``, then clear
the explicit phase.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QVariantAnimation

from tabs.image_gallery.models import ActivityPhase
from tabs.image_gallery.services.activity import (
    ACTIVE_PHASES,
    activity_of,
    clear_activity,
    explicit_activity,
)

ACTIVITY_TICK_MS = 83  # ~12 fps
DONE_LINGER_MS = 1000
DONE_FADE_MS = 250
ACTIVITY_MAX_FADES = 24

_DONE = ActivityPhase.DONE.value


class ActivityPulse(QObject):
    """Owned by ``GalleryGridView``; receives cards, never builds them."""

    def __init__(self, parent: QObject | None = None, translate=None) -> None:
        super().__init__(parent)
        self._translate = translate
        self._cards: dict[int, object] = {}
        self._fades: dict[int, tuple[QVariantAnimation, object]] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(ACTIVITY_TICK_MS)
        self._timer.timeout.connect(self._tick)

    def tracked_count(self) -> int:
        return len(self._cards)

    def sync(self, card) -> None:
        """Re-evaluate one card after its item changed (or on each tick)."""
        key = id(card)
        item = getattr(card, "_gallery_item", None)
        card._gallery_activity_tr = self._translate
        fade = self._fades.get(key)
        if fade is not None:
            if fade[1] is item and self._explicit_phase(item) == _DONE:
                card.update()
                return
            self._stop_fade(key, card)
        phase = self._phase(item)
        if phase in ACTIVE_PHASES:
            self._track(key, card)
        elif phase == _DONE and self._explicit_phase(item) == _DONE:
            self._untrack(key)
            self._start_fade(key, card, item)
        else:
            self._untrack(key)
        card.update()

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _phase(item) -> str | None:
        if item is None:
            return None
        got = activity_of(item)
        return got[0] if got else None

    @staticmethod
    def _explicit_phase(item) -> str | None:
        if item is None:
            return None
        got = explicit_activity(item)
        return got[0] if got else None

    def _track(self, key: int, card) -> None:
        self._cards[key] = card
        if not self._timer.isActive():
            self._timer.start()

    def _untrack(self, key: int) -> None:
        self._cards.pop(key, None)
        if not self._cards:
            self._timer.stop()

    def _start_fade(self, key: int, card, item) -> None:
        if len(self._fades) >= ACTIVITY_MAX_FADES or not card.isVisible():
            clear_activity(item)
            return
        total = DONE_LINGER_MS + DONE_FADE_MS
        anim = QVariantAnimation(self)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setDuration(total)
        anim.setKeyValueAt(DONE_LINGER_MS / total, 1.0)
        anim.valueChanged.connect(lambda v, c=card: self._on_fade_value(c, v))
        anim.finished.connect(lambda k=key, c=card, it=item: self._on_fade_finished(k, c, it))
        self._fades[key] = (anim, item)
        card._gallery_activity_alpha = 1.0
        self._track(key, card)
        anim.start()

    def _stop_fade(self, key: int, card) -> None:
        entry = self._fades.pop(key, None)
        if entry is not None:
            entry[0].stop()
            entry[0].deleteLater()
        card._gallery_activity_alpha = None

    @staticmethod
    def _on_fade_value(card, value) -> None:
        card._gallery_activity_alpha = float(value)
        card.update()

    def _on_fade_finished(self, key: int, card, item) -> None:
        entry = self._fades.pop(key, None)
        if entry is not None:
            entry[0].deleteLater()
        card._gallery_activity_alpha = None
        if getattr(item, "activity_phase", None) == _DONE:
            clear_activity(item)
        self.sync(card)

    def _tick(self) -> None:
        for key, card in list(self._cards.items()):
            try:
                self.sync(card)
            except RuntimeError:
                # Underlying C++ widget was deleted.
                self._untrack(key)
        if not self._cards:
            self._timer.stop()
