"""Flat/series grid rebuild + append paths (grid_view package, plan C1)."""

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

from tabs.image_gallery.ui.grid_view import VIEW_GRID, logger

def _resolve_mode(view, explicit: object = None) -> object:
    """Resolve current gallery mode (fidelity/camera/batch_synthetic) for per-dot colors."""
    self = view
    if explicit is not None:
        return explicit
    if getattr(self, "_mode", None) is not None:
        return self._mode  # type: ignore[attr-defined]
    # Fallback: walk parent / window for _mode or state.mode (widget/controller).
    for obj in (self.parent(), self.window()):
        if obj is None:
            continue
        m = getattr(obj, "_mode", None)
        if m is not None:
            return m
        st = getattr(obj, "state", None)
        if st is not None:
            m2 = getattr(st, "mode", None)
            if m2 is not None:
                return m2
        # Direct parent widget (ImageGalleryWidget) may hold _mode
        try:
            pw = obj
            if hasattr(pw, "_mode") and getattr(pw, "_mode") is not None:
                return getattr(pw, "_mode")
        except Exception:
            pass
    # Also try parent chain for cards host
    try:
        p = self.parent()
        while p is not None:
            m = getattr(p, "_mode", None)
            if m is not None:
                return m
            p = p.parent()  # type: ignore[attr-defined]
    except Exception:
        pass
    return None

def _resolve_profile(view, explicit: object = None) -> object:
    """Resolve the ACTIVE metric profile from the LIVE state (never cached).

    Mirrors ``_resolve_mode``'s parent/window walk but reads ONLY
    ``state.metric_profile`` (the same objects ``_resolve_mode`` inspects for
    ``state.mode``). The profile is refreshed when the folder's metrics
    settle, while ``_mode`` is only rewritten on triage/source change — so a
    profile cached on the widget would show stale (base-only) dots. Returns
    the stored profile, or ``None`` so callers fall back to the mode mapping
    (fail-open).
    """
    self = view
    if explicit is not None:
        return explicit
    for obj in (self.parent(), self.window()):
        if obj is None:
            continue
        st = getattr(obj, "state", None)
        if st is not None:
            prof = getattr(st, "metric_profile", None)
            if prof is not None:
                return prof
    # Also walk the parent chain (cards host / nested containers).
    try:
        p = self.parent()
        while p is not None:
            st = getattr(p, "state", None)
            if st is not None:
                prof = getattr(st, "metric_profile", None)
                if prof is not None:
                    return prof
            p = p.parent()  # type: ignore[attr-defined]
    except Exception:
        pass
    return None

def rebuild_grid(view, items: list[GalleryItem], mode: object = None, *, paint_selection: bool = True, flat_ungrouped: bool = False) -> None:
    """Clear and rebuild the 4-column grid from *items* (pool-reusing Buttons).

    ``mode`` controls per-dot artifact palette; proxied to ``build_gallery_card``.
    ``paint_selection=False`` skips the closing selection sweep — the
    widget passes it when a series restore follows in the same tick and
    sweeps once itself (else every rebuild pays two full sweeps).
    ``flat_ungrouped=True`` wraps a header-less flat pool in a single
    ``UNGROUPED`` section on the SAME pass, so a fresh pool never paints
    nameless while the triage worker is pending. Opt-in: the widget asks
    for it on a first load (no series to restore); callers that restore a
    live series in the same tick keep the flat primitive.
    """
    self = view
    # Keyboard focus continuity: cards are recycled and re-acquired, so
    # capture the focused path now and re-focus its card once the pool is
    # rebuilt (mirrors _rebuild_series' focus preserve).
    _focus_snapshot = self._focus_snapshot()
    if mode is not None:
        self._mode = mode
    else:
        # Try to keep last mode or resolve from parent if not yet set.
        resolved = self._resolve_mode()
        if resolved is not None and getattr(self, "_mode", None) is None:
            self._mode = resolved
    # Cancel pending chunk if rebuild called again (e.g. folder switch)
    try:
        self._rebuild_pending = None
        self._rebuild_index = 0
    except Exception:
        pass
    # Return live cards to pool.
    for path in list(self._cards_by_path):
        self._recycle_card(path)
    # Remove any leftover widgets from layout (headers + empty label etc. not managed here).
    self._clear_series_headers()
    try:
        self._hide_band_separator()
    except Exception:
        pass
    while self.items_layout.count():
        item = self.items_layout.takeAt(0)
        w = item.widget()
        if w is not None and w not in list(self._cards_by_path.values()) and w not in self._pool and w not in self._series_headers:
            try:
                # Stillborn-toplevel guard (see _clear_series_headers):
                # never orphan a visible widget.
                w.hide()
            except Exception:
                pass
            w.setParent(None)

    self._items = list(items)
    self._series = None
    self._ungrouped = []
    self._hub_names = []
    self._collapsed = {}
    self._series_cards = {}
    self._cards_by_path.clear()

    # Eager responsive columns for THIS build. Otherwise the first frame
    # lays out at the stale count (GRID_COLUMNS=4) and only the debounced
    # ``_adapt_timer`` (150 ms) grows it — the "first frames in 2 rows, then
    # one row" jump (log: cols=4 at rebuild -> cols=9 +135 ms).
    if self._view_mode == VIEW_GRID:
        try:
            self._applied_columns = int(self._compute_columns())
        except Exception:
            pass

    if not items:
        self._sync_series_column_widths(series_mode=False)
        self._update_host_height(0)
        return

    # Large folders: chunk to keep event loop alive (systemic vs 1037 sync)
    if len(items) > self._REBUILD_CHUNK * 2:
        self._rebuild_pending = list(items)
        self._rebuild_index = 0
        self._rebuild_flat_ungrouped = bool(flat_ungrouped)
        self._rebuild_focus_path = _focus_snapshot
        self._update_host_height(len(items))  # reserve height early so scrollbar correct
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._rebuild_next_chunk)
        return

    for idx, item in enumerate(items):
        card = self._acquire_card(item)
        self._cards_by_path[str(item.path)] = card
        r, c = divmod(idx, self.grid_columns)
        self.items_layout.addWidget(card, r, c)
        card.show()

    if paint_selection:
        self.apply_selection(self._selection)
    self._sync_series_column_widths(series_mode=False)
    self._update_host_height(len(items))
    # Commit the rows' geometry synchronously. Without this the added
    # cards only lay out on the following event-loop turn, so a view
    # switch on a flat (no live series yet) grid paints one frame of
    # uncommitted rows — list columns collapse to the thumb width and
    # the title elides/overlaps until the layout catches up.
    try:
        self.items_layout.activate()
    except Exception:
        logger.debug("rebuild_grid: layout activate failed", exc_info=True)
    self._schedule_visible_range_emit()
    if flat_ungrouped:
        self._promote_flat_ungrouped()
    # Re-focus the card that held focus before the rebuild (a rebuilt
    # header/group move must not drop the keyboard ring; a removed focused
    # card falls through to the nearest still-live card).
    self._restore_focus(_focus_snapshot)

def _promote_flat_ungrouped(view) -> None:
    """Wrap a header-less flat pool in a single ``UNGROUPED`` section.

    A flat rebuild must not paint nameless cards while the triage worker
    is pending: every item belongs under ``UNGROUPED`` from the first
    frame. No-op when a series view is already live (``_series`` is not
    ``None``) or the pool is empty. Reuses the already-built cards —
    ``set_series`` routes through ``_rebuild_series``, which recycles and
    reflows them in place.
    """
    self = view
    if getattr(self, "_series", None) is not None:
        return
    try:
        if not list(getattr(self, "_items", None) or []):
            return
    except Exception:
        return
    try:
        self.set_series([], hub_names=[], collapsed={})
    except Exception:
        logger.debug("rebuild_grid: flat→UNGROUPED promotion failed", exc_info=True)

def _rebuild_next_chunk(view) -> None:
    self = view
    pending = getattr(self, "_rebuild_pending", None)
    if pending is None:
        return
    start = getattr(self, "_rebuild_index", 0)
    end = min(start + self._REBUILD_CHUNK, len(pending))
    for idx in range(start, end):
        item = pending[idx]
        card = self._acquire_card(item)
        self._cards_by_path[str(item.path)] = card
        r, c = divmod(idx, self.grid_columns)
        self.items_layout.addWidget(card, r, c)
        card.show()
    self._rebuild_index = end
    if end < len(pending):
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._rebuild_next_chunk)
    else:
        # Done — finalize selection after all chunks
        self._rebuild_pending = None
        self._rebuild_index = 0
        self.apply_selection(self._selection)
        # Chunked fill finished — now wrap the flat pool in UNGROUPED
        # (deferred so the chunks stay responsive; the header lands the
        # moment the pool is complete).
        if getattr(self, "_rebuild_flat_ungrouped", False):
            self._promote_flat_ungrouped()
        # Same synchronous commit as the non-chunked path: the last
        # chunk must not leave the tail rows unlaid-out for a frame.
        try:
            self.items_layout.activate()
        except Exception:
            logger.debug("_rebuild_next_chunk: layout activate failed", exc_info=True)
        self._schedule_visible_range_emit()
        self._restore_focus(getattr(self, "_rebuild_focus_path", None))
        self._rebuild_focus_path = None

def append_new_cards(view, items: list[GalleryItem]) -> None:
    """Append-only fast path for pool growth (drop-append).

    Keeps every painted card/header in place — no flat teardown, no
    restore pass. New cards land in the UNGROUPED tail when a series
    view is live (creating the tail header on first use). A flat
    pre-triage pool (no headers yet) is promoted to a single UNGROUPED
    section in the SAME pass, so the freshly appended card(s) are
    grouped immediately instead of waiting for the triage worker
    (bug 2: first-drop grouping delay). Falls back to a full
    ``rebuild_grid`` when there is no safe incremental plan (e.g. a
    chunked rebuild still in flight).
    """
    self = view
    fresh = [it for it in (items or [])]
    if not fresh:
        return
    if getattr(self, "_rebuild_pending", None) is not None:
        self.rebuild_grid(list(getattr(self, "_items", []) or []) + list(fresh))
        return
    try:
        self._items = list(getattr(self, "_items", []) or []) + list(fresh)
    except Exception:
        logger.debug("append_new_cards: item-list update failed", exc_info=True)
    if getattr(self, "_series", None) is None:
        # Flat, pre-triage pool (no headers yet): promote the whole pool
        # to one UNGROUPED section now. `_rebuild_series` reuses the
        # already-parented cards and lays them under the new tail header
        # in one pass — the appended card is grouped the moment it
        # arrives, with no reliance on a later triage delivery.
        try:
            self._series = []
            self._ungrouped = list(getattr(self, "_items", []) or [])
            self._hub_names = []
            # _rebuild_series sweeps selection itself — no second sweep.
            self._rebuild_series()
        except Exception:
            logger.debug(
                "append_new_cards: flat→UNGROUPED promotion failed", exc_info=True
            )
        return
    try:
        ungrouped = list(getattr(self, "_ungrouped", []) or [])
        # Side-by-side bands anchor the tail in the right band with its
        # own column math — the incremental rowCount plan below only fits
        # the stacked band, so banded appends go through the surgical
        # _rebuild_series instead (reuses every live card/header).
        try:
            _n_series = len(list(getattr(self, "_series", []) or []))
            _tail_after = len(ungrouped) + len(fresh)
            _secs_after = int(_n_series) + (1 if int(_tail_after) > 0 else 0)
        except Exception:
            _secs_after = 0
        if self._bands_active() or self._would_band_with(_secs_after):
            try:
                self._ungrouped = ungrouped + list(fresh)
            except Exception:
                logger.debug("append_new_cards: ungrouped sync failed", exc_info=True)
            for item in fresh:
                try:
                    _card = self._acquire_card(item)
                    self._cards_by_path[str(item.path)] = _card
                except Exception:
                    continue
            try:
                self._rebuild_series()
            except Exception:
                logger.debug("append_new_cards: banded rebuild failed", exc_info=True)
            return
        # Ensure exactly one UNGROUPED tail header widget exists. State
        # (_ungrouped) and the actual header widget can disagree after a
        # fail-open earlier pass; anchoring cards to a header that isn't
        # there is what threw the appended card to a default position.
        headers = list(getattr(self, "_series_headers", []) or [])
        has_tail = any(
            getattr(h, "objectName", lambda: "")() == "GallerySeriesHeader_ungrouped"
            for h in headers
        )
        total = len(ungrouped) + len(fresh)
        if has_tail:
            self._refresh_ungrouped_header_count(total)
        else:
            row = int(self.items_layout.rowCount())
            header = self._make_series_header(
                self._ungrouped_header_text(total), total,
                hub_name=None,
                collapsed=bool(getattr(self, "_tail_collapsed", False)), index=None,
            )
            self._series_headers.append(header)
            self.items_layout.addWidget(header, row, 0, 1, self._tail_header_span())
            header.show()
        base = int(self.items_layout.rowCount())
        pos0 = len(ungrouped)
        # Anchor new cards to the live ungrouped block, not to
        # rowCount: rowCount counts header rows too, so continuing
        # from it overshoots one row per header above (live: the
        # 2nd card lands a row low on its own — reads as a nameless
        # group until triage rebuilds). The tail block is last and
        # compact, so its start row = rowCount - its row span.
        try:
            _cols = max(1, int(self.grid_columns))
        except Exception:
            _cols = 1
        try:
            _span = -(-int(pos0) // _cols) if pos0 else 0
            _start = int(base) - int(_span) if _span else int(base)
        except Exception:
            _start = int(base)
        for pos, item in enumerate(fresh):
            card = self._acquire_card(item)
            self._cards_by_path[str(item.path)] = card
            r, c = divmod(pos0 + pos, _cols)
            self.items_layout.addWidget(card, _start + r, c)
            card.show()
        try:
            self._ungrouped = ungrouped + list(fresh)
        except Exception:
            logger.debug("append_new_cards: ungrouped sync failed", exc_info=True)
    except Exception:
        logger.debug("append_new_cards: grouped tail append failed", exc_info=True)
    try:
        self._update_host_height_for_series(int(self.items_layout.rowCount()))
    except Exception:
        logger.debug("append_new_cards: host height sync failed", exc_info=True)
    try:
        self.apply_selection(self._selection)
    except Exception:
        logger.debug("append_new_cards: selection sweep failed", exc_info=True)
