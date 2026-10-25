"""Selection sweep, visibility, host-height + external helpers (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Layer, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import (
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    apply_gallery_selection,
    build_gallery_card,
    gallery_selection_accent,
    update_gallery_card,
)
from tabs.image_gallery.ui.card.activity_pulse import ActivityPulse
from tabs.image_gallery.ui.list.card import (
    LIST_CARD_H,
    _bind_list_row,
    build_gallery_list_card,
    update_gallery_list_card,
)
from ui.widgets.shelf import OpaqueFillHost, apply_opaque_widget_fill
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

from tabs.image_gallery.ui.grid_view import GRID_COLUMNS, GRID_MARGIN_BOTTOM, GRID_MARGIN_TOP, GRID_SPACING, VIEW_LIST


def _card_tint_fn():
    """Resolve the card tint helper through the owning package.

    ``tests/test_repaint_overhead.py`` monkeypatches
    ``tabs.image_gallery.ui.grid_view.apply_gallery_selection`` to count
    selection sweeps; resolving through the package keeps that seam live
    after the package split (plan-gallery-split-2026-10-17 Part C1).
    """
    try:
        from tabs.image_gallery.ui import grid_view as _gv

        return _gv.apply_gallery_selection
    except Exception:
        return apply_gallery_selection


def refresh_card(view, item: GalleryItem) -> None:
    self = view
    card = self._cards_by_path.get(str(item.path))
    if card is None:
        return
    try:
        from .drag_source import _gallery_domain

        domain = _gallery_domain(self)
    except Exception:
        domain = ""
    try:
        if self._view_mode == VIEW_LIST:
            update_gallery_list_card(  # type: ignore[arg-type]
                card,
                item,
                mode=self._resolve_mode(),
                translate=self._activity_translate,
                domain=domain,
                profile=self._resolve_profile(),
            )
        else:
            # translate rides the card (attached at build) — no per-update threading.
            update_gallery_card(  # type: ignore[arg-type]
                card, item, mode=self._resolve_mode(), domain=domain,
                profile=self._resolve_profile(),
            )
    except Exception:
        pass
    self._sync_activity(card)
    # Re-apply selection tint in case accent changed.
    self.apply_selection(self._selection)

def refresh_cards(view, items) -> None:
    """Batch card refresh: one content update per card, ONE selection sweep.

    Delivery handlers (artifact/fidelity analysis) used to call
    ``refresh_card`` per item, each re-running ``apply_selection`` over
    the whole grid — O(N^2) region updates + repaints on the UI thread
    in a single delivery, stalling the event loop (compositor busy
    cursor, dropped overlay frames) exactly when quick look shows new
    severities. Single-call behavior of ``refresh_card`` is unchanged.
    """
    self = view
    try:
        items = list(items or [])
    except Exception:
        return
    if not items:
        return
    try:
        mode = self._resolve_mode()
    except Exception:
        mode = None
    try:
        profile = self._resolve_profile()
    except Exception:
        profile = None
    try:
        from .drag_source import _gallery_domain

        domain = _gallery_domain(self)
    except Exception:
        domain = ""
    for item in items:
        try:
            card = self._cards_by_path.get(str(item.path))
        except Exception:
            continue
        if card is None:
            continue
        try:
            if self._view_mode == VIEW_LIST:
                update_gallery_list_card(  # type: ignore[arg-type]
                    card,
                    item,
                    mode=mode,
                    translate=self._activity_translate,
                    domain=domain,
                    profile=profile,
                )
            else:
                update_gallery_card(card, item, mode=mode, domain=domain, profile=profile)  # type: ignore[arg-type]
        except Exception:
            pass
        self._sync_activity(card)
    try:
        self.apply_selection(self._selection)
    except Exception:
        pass

def set_card_visible(view, path: Path, visible: bool) -> None:
    self = view
    card = self._cards_by_path.get(str(path))
    if card is not None:
        try:
            card.setVisible(bool(visible))
        except Exception:
            pass

def apply_selection(view, selected: set[Path] | set[str] | None = None) -> None:
    self = view
    if selected is None:
        selected = self._selection
    norm: set[str] = set()
    for p in selected or set():
        norm.add(str(p))
    self._selection = set(norm)
    accent = self._selection_accent
    try:
        accent_key = None if accent is None else (
            int(accent.red()), int(accent.green()),
            int(accent.blue()), int(accent.alpha()),
        )
    except Exception:
        accent_key = None
    for str_path, card in self._cards_by_path.items():
        want = str_path in norm
        # Idempotence stamp: repeat sweeps (thumbnail ticks, rebuild
        # tails) skip cards whose tint is already correct — otherwise
        # every sweep repaints every card (O(N²) per load cycle).
        try:
            stamp = getattr(card, "_gallery_sel_applied", None)
        except Exception:
            stamp = None
        if stamp == (want, accent_key):
            continue
        if stamp is None and not want:
            # Cold card is already visually unselected (no override ever
            # applied): stamp without painting. Otherwise the first
            # preview sweep repaints EVERY card (~26ms stall measured on
            # drag start) just to confirm the status quo.
            try:
                card._gallery_sel_applied = (want, accent_key)  # type: ignore[attr-defined]
            except Exception:
                pass
            continue
        try:
            _card_tint_fn()(card, want, accent=accent)  # type: ignore[arg-type]
        except Exception:
            pass
        try:
            card._gallery_sel_applied = (want, accent_key)  # type: ignore[attr-defined]
        except Exception:
            pass

def refresh_selection_accent(view) -> None:
    self = view
    from ui.widgets.shelf.marquee_plumbing import refresh_accent

    refresh_accent(self, gallery_selection_accent())
    self.apply_selection(self._selection)

def _update_host_height(view, item_count: int) -> None:
    # Let host grow with content; scroll area will show scrollbar as needed.
    # Host height is derived from row count * stride + margins.
    self = view
    if item_count <= 0:
        try:
            self.items_host.setMinimumHeight(1)
        except Exception:
            pass
        return
    rows = (item_count + self.grid_columns - 1) // self.grid_columns
    stride = self._card_height_px() + scaled_px(GRID_SPACING)
    margins = scaled_px(GRID_MARGIN_TOP) + scaled_px(GRID_MARGIN_BOTTOM)
    needed = margins + rows * self._card_height_px() + max(0, rows - 1) * scaled_px(GRID_SPACING)
    # Also ensure stride accounts for content padding already in card height.
    _ = stride  # keep for future virtualization parity
    try:
        self.items_host.setMinimumHeight(needed)
    except Exception:
        pass

def grid_columns(view) -> int:
    self = view
    if self._view_mode == VIEW_LIST:
        return 1
    try:
        return max(1, int(getattr(self, "_applied_columns", GRID_COLUMNS)))
    except Exception:
        return GRID_COLUMNS

def items(view) -> list[GalleryItem]:
    self = view
    return list(self._items)

def card_for(view, path: Path | str):  # type: ignore[no-untyped-def]
    self = view
    return self._cards_by_path.get(str(path))

def set_fill_color(view, color) -> None:
    self = view
    try:
        apply_opaque_widget_fill(self.items_host, color)
        apply_opaque_widget_fill(self.scroll_area.viewport(), color)
        apply_opaque_widget_fill(self.scroll_area, color)
    except Exception:
        pass

def event_filter(view, watched, event) -> bool:  # noqa: N802
    self = view
    # Delegate to marquee module if available.
    try:
        from tabs.image_gallery.ui import marquee as _marquee

        if _marquee.event_filter(self, watched, event):
            return True
    except Exception:
        pass
    # FM background menu: right-click on empty host opens Sort by / View.
    try:
        from PySide6.QtCore import QEvent as _QEvent
        from PySide6.QtGui import QMouseEvent as _QMouseEvent

        host = getattr(self, "items_host", None)
        if (
            host is not None
            and watched is host
            and event.type() == _QEvent.Type.MouseButtonPress
            and isinstance(event, _QMouseEvent)
            and event.button() == Qt.MouseButton.RightButton
        ):
            try:
                pos = event.position().toPoint()
            except Exception:
                pos = None
            try:
                child = host.childAt(pos) if pos is not None else None
            except Exception:
                child = None
            if child is None and callable(getattr(self, "_on_empty_context_menu", None)):
                try:
                    global_pos = host.mapToGlobal(pos) if pos is not None else None
                except Exception:
                    global_pos = None
                self._on_empty_context_menu(global_pos)
                return True
    except Exception:
        pass
    # KeyPress on the host/viewport (no card holds focus yet): the scroll
    # area would otherwise swallow arrows before the owner widget sees
    # them. Delegate to the card-grid navigation (session_picker parity,
    # ``recent/items_view.eventFilter`` → ``_handle_key_press``).
    try:
        if event.type() == QEvent.Type.KeyPress and self.handle_navigation_key(event):
            return True
    except Exception:
        pass
    return False
