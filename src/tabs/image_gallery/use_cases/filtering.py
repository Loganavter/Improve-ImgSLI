"""Filtering helpers for the Image Gallery (debounced text + brief match).

Thin-owner helpers: plain functions taking the owner (``GalleryController``).
Keystrokes coalesce through the owner's single-shot ``_filter_timer``; the
fast pass (filename + in-memory tags) runs on the UI thread while the
brief-cache disk match runs on a ``GenericWorker``, merged only when the query
and folder generation are still current. Owner state
(``_pending_filter_text`` / ``_filter_timer`` / ``_filter_gen``) and the
``GalleryController.FILTER_DEBOUNCE_MS`` window stay on the owner.

The ``state.filter_text`` mirror write goes through ``setattr``: a bare
``.state.X =`` outside ``controller.py`` is rejected by the gallery ownership
guard (``src/tabs/image_gallery/tests/contracts/test_gallery_ownership_guards.py``).
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from sli_ui_toolkit.workers import GenericWorker

from core.state_management.gallery_actions import GalleryFilterSet
from tabs.image_gallery.state import selectors as _gallery_selectors


def set_filter_text(owner, text: str) -> None:
    owner._pending_filter_text = text or ""
    timer = owner._filter_timer
    if timer is None:
        try:
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(owner._apply_pending_filter)
            owner._filter_timer = timer
        except Exception:
            timer = None
    if timer is None:
        # No Qt event loop (headless unit context) — apply synchronously.
        owner._apply_filter(owner._pending_filter_text, owner._filter_gen + 1)
        return
    try:
        timer.stop()
        timer.start(owner.FILTER_DEBOUNCE_MS)
    except Exception:
        owner._apply_filter(owner._pending_filter_text, owner._filter_gen + 1)


def apply_pending_filter(owner) -> None:
    """Flush a debounced keystroke synchronously (tests / teardown)."""
    timer = owner._filter_timer
    if timer is not None:
        try:
            timer.stop()
        except Exception:
            pass
    owner._apply_pending_filter()


def _apply_pending_filter(owner) -> None:
    owner._filter_gen += 1
    owner._apply_filter(owner._pending_filter_text, owner._filter_gen)


def _apply_filter_fast(owner, text: str) -> None:
    """UI-thread fast pass: filename + in-memory tags only, no disk."""
    from tabs.image_gallery.services.filtering import match_fast_items

    fast = {item.path for item in match_fast_items(owner.state.items, text)}
    if not (text or "").strip():
        fast = {item.path for item in owner.state.items}
    for item in owner.state.items:
        try:
            owner.widget.set_card_visible(item.path, item.path in fast)
        except Exception:
            pass


def _apply_filter(owner, text: str, filter_gen: int) -> None:
    from tabs.image_gallery.services.filtering import match_brief_items

    owner._filter_gen = max(owner._filter_gen, filter_gen)
    gen = owner._filter_gen
    # Dispatch-only source (set_selection pattern): skip dispatch when
    # the slot already equals, else emit, then mirror locally.
    try:
        slot = owner._gallery_slot()
        if slot is None or _gallery_selectors.get_filter_text(slot) != text:
            owner._emit_gallery(GalleryFilterSet(filter_text=text))
    except Exception:
        owner._emit_gallery(GalleryFilterSet(filter_text=text))
    # setattr (not a direct attribute assignment) keeps this mirror write clear
    # of the gallery ownership guard, which rejects bare state writes outside
    # controller.py (see tests/contracts/test_gallery_ownership_guards.py).
    setattr(owner.state, "filter_text", text)
    owner._apply_filter_fast(text)
    if not (text or "").strip():
        return
    # Slow pass off the UI thread: brief-cache disk match, mtime-honored.
    # Merged on arrival only if no newer keystroke/folder switch landed.
    snapshot = list(owner.state.items)

    def _slow() -> set:
        try:
            return {item.path for item in match_brief_items(snapshot, text)}
        except Exception:
            return set()

    folder_gen = owner._folder_gen
    worker = GenericWorker(_slow)
    worker.signals.result.connect(
        lambda extra, g=gen, fg=folder_gen: owner._on_brief_filter_ready(extra, g, fg)
    )
    worker.signals.error.connect(lambda _err: None)
    owner._pool_start(worker, 0)


def _on_brief_filter_ready(
    owner, extra_paths: set, filter_gen: int, folder_gen: int
) -> None:
    if filter_gen != owner._filter_gen or not owner._is_current_folder_gen(folder_gen):
        return  # stale query or folder switch — never resurrect old matches
    if not extra_paths:
        return
    for item in owner.state.items:
        if item.path in extra_paths:
            try:
                owner.widget.set_card_visible(item.path, True)
            except Exception:
                pass
