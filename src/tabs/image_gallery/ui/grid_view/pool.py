"""Card pool / recycle / rebind helpers (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label, Layer, OverlayScrollArea

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

logger = logging.getLogger("ImproveImgSLI")

from tabs.image_gallery.ui.grid_view import VIEW_GRID, VIEW_LIST
from .drag_source import _gallery_domain


def _acquire_card(view, item: GalleryItem):
    self = view
    _mode = self._resolve_mode()
    _domain = _gallery_domain(self)
    want_list = self._view_mode == VIEW_LIST
    updater = update_gallery_list_card if want_list else update_gallery_card
    while self._pool:
        card = self._pool.pop()
        # Pool must never mix grid/list builders (different regions).
        if getattr(card, "_gallery_view_mode", VIEW_GRID) != self._view_mode:
            try:
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
            continue
        try:
            card.setParent(self.items_host)
        except Exception:
            pass
        try:
            updater(  # type: ignore[arg-type]
                card,
                item,
                mode=_mode,
                translate=self._activity_translate,
                domain=_domain,
            )
        except Exception:
            pass
        # Rebind click to current toggle handler (pool may carry old closure).
        self._rebind_card(card)
        try:
            card._gallery_view_mode = self._view_mode  # type: ignore[attr-defined]
        except Exception:
            pass
        self._ensure_card_drag(card)
        self._ensure_card_keys(card)
        self._sync_activity(card)
        return card
    if want_list:
        card = build_gallery_list_card(
            item,
            parent=self.items_host,
            on_activate=self._handle_toggle,
            on_context_menu=self._handle_context_menu,
            mode=_mode,
            translate=self._activity_translate,
            domain=_domain,
        )
    else:
        card = build_gallery_card(
            item,
            parent=self.items_host,
            on_activate=self._handle_toggle,
            on_context_menu=self._handle_context_menu,
            mode=_mode,
            translate=self._activity_translate,
            domain=_domain,
        )
    try:
        card._gallery_view_mode = self._view_mode  # type: ignore[attr-defined]
    except Exception:
        pass
    self._ensure_card_drag(card)
    self._ensure_card_keys(card)
    self._sync_activity(card)
    return card

def _sync_activity(view, card) -> None:
    self = view
    try:
        self._activity.sync(card)
    except RuntimeError:
        pass

def _activity_translate(view, key: str, default: str) -> str:
    """Tab translator via the owner (controller ``_tr``; widget fallback)."""
    self = view
    try:
        owner = self._gallery_widget._owner_for_triage()
        tr = getattr(owner, "_tr", None)
        return str(tr(key, default)) if callable(tr) else default
    except Exception:
        return default

def _ungrouped_header_text(view, count: int) -> str:
    """Localized UNGROUPED tail header (``image_gallery.series.ungrouped``)."""
    self = view
    try:
        return str(self._activity_translate(
            "image_gallery.series.ungrouped", "UNGROUPED · {count}"
        )).format(count=count)
    except Exception:
        return f"UNGROUPED · {count}"

def _recycle_card(view, str_path: str) -> None:
    self = view
    card = self._cards_by_path.pop(str_path, None)  # type: ignore[arg-type]
    if card is None:
        # Also handle case where path key is Path str but layout still holds widget not in map.
        return
    try:
        self.items_layout.removeWidget(card)
    except Exception:
        pass
    try:
        apply_gallery_selection(card, False)  # type: ignore[arg-type]
    except Exception:
        pass
    try:
        # Hover/menu state is per-widget; drop it before the pooled card
        # is rebound to another item (or the bar rides it to a new card).
        from tabs.image_gallery.ui.card.hover import reset_card_hover_state

        reset_card_hover_state(card)
    except Exception:
        pass
    try:
        card.hide()
    except Exception:
        pass
    if len(self._pool) < 32:
        try:
            card.setParent(self)
        except Exception:
            pass
        self._pool.append(card)
    else:
        try:
            card.setParent(None)
            card.deleteLater()
        except Exception:
            pass

def _rebind_card(view, card) -> None:
    # Disconnect previous regionClicked/rightClicked if possible, then reconnect via helper.
    # Easiest: disconnect all and rebind via build helper's internal.
    self = view
    try:
        card.regionClicked.disconnect()
    except Exception:
        pass
    try:
        card.rightClicked.disconnect()
    except Exception:
        pass
    try:
        card.clicked.disconnect()
    except Exception:
        pass
    # Re-install handlers with current callbacks. List rows route chrome
    # region clicks to actions — grid binder would activate on every id.
    if self._view_mode == VIEW_LIST:
        _bind_list_row(card, on_activate=self._handle_toggle, on_context_menu=self._handle_context_menu)
        return
    from tabs.image_gallery.ui.card import _bind_gallery_card  # local import to avoid cycle

    _bind_gallery_card(card, on_activate=self._handle_toggle, on_context_menu=self._handle_context_menu)

def _handle_toggle(view, path: Path, additive: bool = False) -> None:
    self = view
    if callable(self._on_toggle):
        try:
            self._on_toggle(path, additive)
        except TypeError:
            self._on_toggle(path)
