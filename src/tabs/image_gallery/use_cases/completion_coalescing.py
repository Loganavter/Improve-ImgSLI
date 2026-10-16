"""Coalesced gallery completions — ONE dispatch per event-loop turn.

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
Thumbnail-ready and card-refresh completions are batched and flushed once per
turn via ``QTimer.singleShot(0, …)`` — or synchronously when there is no event
loop (headless unit contexts). The pending buffers
(``_pending_thumb_ready`` / ``_pending_card_items``) and the scheduled flags
stay on the owner; these functions only read/write them through ``owner``.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer

from core.state_management.gallery_actions import (
    GalleryThumbnailsReady,
    GalleryTriageFinished,
)
from tabs.image_gallery.state import selectors as _gallery_selectors

logger = logging.getLogger("ImproveImgSLI")


def _queue_thumb_ready(owner, path: Path, status: str) -> None:
    try:
        owner._pending_thumb_ready.append((str(path), status))
    except Exception:
        return
    if owner._thumb_flush_scheduled:
        return
    owner._thumb_flush_scheduled = True
    try:
        if QCoreApplication.instance() is None:
            # No event loop (headless unit context) — flush synchronously.
            owner._flush_pending_thumbnails()
        else:
            QTimer.singleShot(0, owner._flush_pending_thumbnails)
    except Exception:
        try:
            owner._flush_pending_thumbnails()
        except Exception:
            pass


def _flush_pending_thumbnails(owner) -> None:
    owner._thumb_flush_scheduled = False
    if not owner._pending_thumb_ready:
        return
    batch, owner._pending_thumb_ready = owner._pending_thumb_ready, []
    # Coalesce same path → last status wins, first-seen order kept.
    last: dict[str, str] = {}
    for path, status in batch:
        last[path] = status
    ready = [(p, last[p]) for p in dict.fromkeys(p for p, _ in batch)]
    # Drop entries the slot already has (reducer identity would no-op
    # without an emit, leaking own-emit accounting).
    try:
        slot = owner._gallery_slot()
        if slot is not None:
            current = {
                m.path: m.status for m in _gallery_selectors.get_items(slot)
            }
            ready = [(p, s) for p, s in ready if current.get(p) != s]
    except Exception:
        pass
    if not ready:
        return
    owner._emit_gallery(GalleryThumbnailsReady(ready=ready))


def flush_pending_thumbnails(owner) -> None:
    """Flush a coalesced turn synchronously (tests / teardown)."""
    owner._flush_pending_thumbnails()
    owner._flush_pending_card_refresh()


def _queue_card_refresh(owner, item) -> None:
    """Defer one card repaint into the per-tick batch (see __init__)."""
    try:
        owner._pending_card_items[str(getattr(item, "path", item))] = item
    except Exception:
        return
    if owner._card_flush_scheduled:
        return
    owner._card_flush_scheduled = True
    try:
        if QCoreApplication.instance() is None:
            # No event loop (headless unit context) — flush synchronously.
            owner._flush_pending_card_refresh()
        else:
            QTimer.singleShot(0, owner._flush_pending_card_refresh)
    except Exception:
        try:
            owner._flush_pending_card_refresh()
        except Exception:
            pass


def _flush_pending_card_refresh(owner) -> None:
    owner._card_flush_scheduled = False
    if not owner._pending_card_items:
        return
    batch, owner._pending_card_items = list(owner._pending_card_items.values()), {}
    try:
        refresh_cards = getattr(owner.widget, "refresh_cards", None)
        if callable(refresh_cards):
            refresh_cards(batch)
            return
    except Exception:
        pass
    for item in batch:
        try:
            owner.widget.refresh_card(item)
        except Exception:
            pass


def _emit_triage_finished(owner, triage_state: str, source_path=None) -> bool:
    """Dispatch GalleryTriageFinished from the local summary + ranks.

    ``source_path`` overrides the mirrored state value when given
    (set_source path); otherwise the current state mirror is carried.
    """
    try:
        ranks: dict[str, int] = {}
        for it in owner.state.items:
            try:
                if it.rank is not None:
                    ranks[str(it.path)] = int(it.rank)
            except Exception:
                continue
        mode = getattr(owner.state, "mode", None)
        mode_s = getattr(mode, "value", mode)
        source = source_path if source_path is not None else getattr(owner.state, "source_path", None)
        if source is not None and not isinstance(source, (str, Path)):
            source = None
        return owner._emit_gallery(
            GalleryTriageFinished(
                triage_state=triage_state,
                mode=str(mode_s) if mode_s is not None else None,
                source_path=str(source) if source is not None else None,
                ranks=ranks,
            )
        )
    except Exception:
        logger.debug("triage-finished dispatch failed", exc_info=True)
        return False
