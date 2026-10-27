"""Series grouping, headers, collapse + retitle (grid_view package, plan C1).
Audit-Meta: pattern=thin-owner-target size=exempt reason="series grouping/header lifecycle is one concern moved out of the thin GalleryGridView owner (plan-gallery-split-2026-10-17 Part C1)"
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Layer, OverlayScrollArea, Text

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

from tabs.image_gallery.ui.grid_view import GRID_BAND_MIN_TOTAL, GRID_COLUMNS, GRID_MARGIN_BOTTOM, GRID_MARGIN_TOP, GRID_SEPARATOR_COL_W, GRID_SPACING, SERIES_ARROW_RESERVE, VIEW_GRID, VIEW_LIST, logger

from .layers import (
    _gallery_header_text_color,
    _SeriesCollapseArrowLayer,
    _SeriesDropTargetLayer,
    _SeriesHeaderAccentLayer,
    _strip_header_arrow,
    _disconnect_btn_theme,
)
from .context import _cluster_series_id, _section_members

def set_series(
    view,
    series: list[list[GalleryItem]] | None,
    hub_names: list[str | None] | None = None,
    collapsed: dict[int, bool] | set[int] | list[bool] | None = None,
    mode: object = None,
) -> None:
    """Rebuild grid with series sections.

    *series* — list of clusters as member lists (``Series`` dataclasses
    accepted too). Clusters with ≥1 members render as own SERIES
    sections — 1-member manual sections (S2 sync-move leftovers) stay
    visible instead of dissolving. Items in no cluster are collected
    under an ``UNGROUPED`` tail. ``None`` or empty clears series mode
    and falls back to the flat UNGROUPED view for all items.
    *hub_names* — per-series hub display name (e.g. source file name).
    *collapsed* — mapping of series index → collapsed bool (or set of collapsed indices).
    *mode* — gallery mode for per-dot colors (fidelity/camera/batch_synthetic), proxied to cards.
    """
    self = view
    # Full rebuild like rebuild_grid — cancel a pending chunked rebuild
    # first, or its QTimer tick would re-add cards on top of the series.
    try:
        self._rebuild_pending = None
        self._rebuild_index = 0
    except Exception:
        pass
    if mode is not None:
        self._mode = mode
    else:
        resolved = self._resolve_mode()
        if resolved is not None and getattr(self, "_mode", None) is None:
            self._mode = resolved
    if not series:
        # No clusters — show UNGROUPED section for all items (real_design.md:59)
        filtered: list[list[GalleryItem]] = []
        # Fall through to UNGROUPED handling below
    else:
        # S2: keep every non-empty cluster as its own section
        # (1-member manual sections stay visible); Series dataclasses
        # and plain member lists both accepted.
        filtered = [_section_members(s) for s in series if len(_section_members(s)) >= 1]
    if not filtered:
        # No valid clusters — all items are ungrouped, show UNGROUPED header
        try:
            all_items = list(self._items) if getattr(self, "_items", None) else []
        except Exception:
            all_items = []
        self._series = []
        self._ungrouped = list(all_items)
        self._hub_names = []
        # Preserve collapsed
        try:
            self._collapsed = dict(getattr(self, "_collapsed", {}) or {})
        except Exception:
            self._collapsed = {}
        # Ensure host shows UNGROUPED even for 1 item
        self._rebuild_series()
        return
    # Determine ungrouped as items not in any cluster.
    try:
        member_paths = {str(it.path) for cl in filtered for it in cl}
    except Exception:
        member_paths = set()
    try:
        all_items = list(self._items)
    except Exception:
        all_items = []
    # If _items was not yet populated (caller passed series before flat list),
    # derive flat list from series + maybe explicit ungrouped tail inside series.
    if not all_items:
        all_items = [it for cl in filtered for it in cl]
        member_paths = {str(it.path) for cl in filtered for it in cl}
    ungrouped = [it for it in all_items if str(it.path) not in member_paths]
    self._series = filtered
    self._ungrouped = ungrouped
    if hub_names is not None:
        try:
            self._hub_names = list(hub_names)[: len(filtered)]
            while len(self._hub_names) < len(filtered):
                self._hub_names.append(None)
        except Exception:
            self._hub_names = [None] * len(filtered)
    else:
        self._hub_names = [None] * len(filtered)
    norm_collapsed: dict[int, bool] = {}
    try:
        if isinstance(collapsed, dict):
            for k, v in collapsed.items():
                try:
                    norm_collapsed[int(k)] = bool(v)
                except Exception:
                    continue
        elif isinstance(collapsed, set):
            for k in collapsed:
                try:
                    norm_collapsed[int(k)] = True
                except Exception:
                    continue
        elif isinstance(collapsed, list):
            for idx, val in enumerate(collapsed):
                if bool(val):
                    norm_collapsed[idx] = True
        elif collapsed is None:
            norm_collapsed = dict(getattr(self, "_collapsed", {}) or {})
            # keep only indices within range
            norm_collapsed = {k: v for k, v in norm_collapsed.items() if 0 <= k < len(filtered)}
        else:
            norm_collapsed = {}
    except Exception:
        norm_collapsed = {}
    self._collapsed = norm_collapsed
    self._rebuild_series()

def _retitle_header(view, header, text: str, index, collapsed: bool = False) -> None:
    """Refresh a reused series header in place (no destroy/create).

    Updates the label text, object names and the collapse-button closure
    (which captures the section index — a reused widget at a new
    position must toggle the new section). UNGROUPED headers (index
    None) get their toggle disconnected. The collapse arrow stays a
    painter layer (never text): flags + title reserve flip here so a
    series ↔ UNGROUPED slot reuse never clips the arrow.
    """
    self = view
    is_series = index is not None
    display = _strip_header_arrow(text)
    try:
        header.setObjectName(
            f"GallerySeriesHeader_{index}" if is_series else "GallerySeriesHeader_ungrouped"
        )
    except Exception:
        pass
    try:
        btn = header.findChild(Button)
    except Exception:
        btn = None
    if btn is None:
        return
    # Keep the click affordance in sync with the slot's new role: a
    # header reused from an UNGROUPED slot (created disabled) must become
    # clickable when it now fronts a real, collapsible series — and vice
    # versa. Without this the collapse toggle is dead on a retitled slot.
    try:
        # Every header (series OR the UNGROUPED tail) is a normal,
        # clickable collapsible group.
        btn.setEnabled(True)
    except Exception:
        pass
    try:
        btn.setObjectName(
            f"GallerySeriesHeaderBtn_{index}" if is_series else "GallerySeriesHeader_ungrouped_btn"
        )
    except Exception:
        pass
    try:
        btn.update_region(
            "_main",
            rows=[ButtonRow(
                text=display.upper(), size=16, color=_gallery_header_text_color(),
                h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True,
            )],
        )
    except Exception:
        pass
    try:
        # A reused header slot may flip series ↔ UNGROUPED: repoint the
        # accent layer's palette (accent vs dialog.border) with it, flip
        # the arrow layer's visibility/state, and reserve/clear the
        # title's right padding so the arrow never overlaps text.
        _painter = getattr(btn, "_painter", None)
        for _layer in list(getattr(_painter, "layers", None) or []):
            if isinstance(_layer, _SeriesHeaderAccentLayer):
                _layer._collapsible = bool(is_series)
            elif isinstance(_layer, _SeriesCollapseArrowLayer):
                _layer._collapsible = True
                _layer._collapsed = bool(collapsed)
        try:
            btn.setContentPadding(
                (scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0)
            )
        except Exception:
            pass
        btn.update()
    except Exception:
        pass
    try:
        btn.clicked.disconnect()
    except Exception:
        pass
    # Only disconnect what was actually wired: an UNGROUPED header slot is
    # built WITHOUT a customContextMenuRequested connection, and a bare
    # disconnect() on an unconnected signal emits a RuntimeWarning (not an
    # exception, so the except below would not catch it).
    if getattr(btn, "_gallery_ctx_menu_wired", False):
        try:
            btn.customContextMenuRequested.disconnect()
        except Exception:
            pass
        try:
            btn._gallery_ctx_menu_wired = False  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
    except Exception:
        pass
    if is_series:
        try:
            self._series_header_labels[index] = display
        except Exception:
            pass
        # A reused header slot may have been built for the UNGROUPED tail
        # (no menu wiring); (re)attach the series context menu here too.
        try:
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, i=index, b=btn: self._handle_series_context(b, i, _pos)
            )
            btn._gallery_ctx_menu_wired = True  # type: ignore[attr-defined]
        except Exception:
            pass

def set_series_attention(view, series_ids) -> None:
    """Mark series that need a human first (additive routing hint).

    Stores the id set rendered as a series-header marker and re-titles in
    place (never a teardown). Empty/None clears the marker. Never touches
    cards, rank or selection.
    """
    self = view
    try:
        self._series_attention = {str(s) for s in (series_ids or ()) if s}
    except Exception:
        self._series_attention = set()
    try:
        self._rebuild_series()
    except Exception:
        pass

def _rebuild_series(view, *, refresh_content: bool = True) -> None:
    """Internal: rebuild with series headers + UNGROUPED tail.

    ``refresh_content=False`` (resize path, via ``_rebuild_series_geometry``)
    keeps the surgical reconcile — same headers, same cards, same plan math —
    but skips the per-card content refresh (badge/dots/cover re-stamp). A
    window-edge drag only changes the PLAN; re-stamping every card there cost
    one ``update_gallery_card`` per card on each resize tick of a running
    analysis (owner report 2026-10-27).
    """
    self = view
    # Preserve scroll + keyboard focus across the teardown: heights land
    # identical, but the intermediate collapse clamps the scrollbar to 0
    # and reparenting drops focus to None (keyboard dead until a click).
    try:
        _bar = self.scroll_area.verticalScrollBar()
        _saved_scroll = int(_bar.value())
    except Exception:
        _bar = None
        _saved_scroll = 0
    _focus_snapshot = self._focus_snapshot()
    # --- surgical reconcile (no teardown) ---
    # Reuses header widgets (text refreshed in place) and surviving
    # cards (content updated, never hidden/reparented). Previously every
    # regroup destroyed all headers (deleteLater) and round-tripped all
    # cards through hide+reparent+show — per-card ParentChange storms,
    # badge resyncs, focus loss and header-button blink, log-proven on
    # every drop.
    if self._series is None:
        for path in list(self._cards_by_path):
            self._recycle_card(path)
        self._clear_series_headers()
        try:
            self._hide_band_separator()
        except Exception:
            pass
        while self.items_layout.count():
            try:
                self.items_layout.takeAt(0)
            except Exception:
                break
        self._cards_by_path.clear()
        self._series_cards = {}
        self._sync_series_column_widths(series_mode=False)
        return
    try:
        _mode = self._resolve_mode()
    except Exception:
        _mode = None
    try:
        _profile = self._resolve_profile()
    except Exception:
        _profile = None
    try:
        from .drag_source import _gallery_domain

        _domain = _gallery_domain(self)
    except Exception:
        _domain = ""
    # 1. plan sections (same order/texts as the old full rebuild).
    def _hdr(key: str, default: str, **kw) -> str:
        try:
            return str(self._activity_translate(key, default)).format(**kw)
        except Exception:
            return default.format(**kw)

    _sections: list[dict] = []
    for idx, cluster in enumerate(list(self._series or [])):
        hub = self._hub_names[idx] if idx < len(self._hub_names) else None
        is_collapsed = bool(self._collapsed.get(idx, False))
        if hub:
            header_text = _hdr(
                "image_gallery.series.header_hub",
                "SERIES {n} · {hub} · {count} VARIANTS",
                n=idx + 1, hub=hub, count=len(cluster),
            )
        else:
            header_text = _hdr(
                "image_gallery.series.header",
                "SERIES {n} · {count} images",
                n=idx + 1, count=len(cluster),
            )
        if _cluster_series_id(cluster) in self._series_attention:
            header_text = (
                f"{header_text} · "
                f"{_hdr('image_gallery.series.needs_attention', 'NEEDS ATTENTION')}"
            )
        _sections.append({
            "kind": "series", "index": idx, "hub": hub,
            "collapsed": is_collapsed, "text": header_text,
            "items": list(cluster) if not is_collapsed else [],
        })
    if list(getattr(self, "_ungrouped", []) or []):
        _ung = list(getattr(self, "_ungrouped", []) or [])
        _sections.append({
            "kind": "tail", "index": None, "hub": None,
            "collapsed": bool(getattr(self, "_tail_collapsed", False)),
            "text": _hdr(
                "image_gallery.series.ungrouped",
                "UNGROUPED · {count}",
                count=len(_ung),
            ),
            "items": _ung,
        })
    # 2. cards: recycle gone paths only.
    try:
        _wanted = {str(getattr(it, "path", None)) for s in _sections for it in s["items"]}
    except Exception:
        _wanted = set()
    for path in list(self._cards_by_path):
        try:
            if str(path) not in _wanted:
                self._recycle_card(path)
        except Exception:
            continue
    # 3. cards: update kept in place (no hide/reparent — filters, pins
    # and focus survive), acquire genuinely new ones.
    self._series_cards = {}
    for sec in _sections:
        if sec["kind"] == "series" and sec["collapsed"]:
            continue
        cards: list[object] = []
        for item in sec["items"]:
            try:
                sp = str(item.path)
            except Exception:
                continue
            card = self._cards_by_path.get(sp)
            if card is None:
                try:
                    card = self._acquire_card(item)
                except Exception:
                    continue
                self._cards_by_path[sp] = card
            else:
                try:
                    # MODE-AWARE, exactly like ``marquee.refresh_card``: a list
                    # row carries the inline badge inside its TEXT rows and has
                    # no ``cover`` region, so the grid updater raised
                    # ``ValueError: unknown button region id: 'cover'`` here and
                    # the swallowed exception left the row's badge stale
                    # (measured 2026-10-22: a rebuilt series kept ``#2`` after
                    # the badge was cleared). One implementation of the choice:
                    # the two sibling refreshers do the same branch.
                    if refresh_content:
                        if getattr(self, "_view_mode", VIEW_GRID) == VIEW_LIST:
                            update_gallery_list_card(  # type: ignore[arg-type]
                                card,
                                item,
                                mode=_mode,
                                translate=self._activity_translate,
                                domain=_domain,
                                profile=_profile,
                            )
                        else:
                            update_gallery_card(  # type: ignore[arg-type]
                                card, item, mode=_mode, domain=_domain, profile=_profile
                            )
                except Exception:
                    logger.debug("series card refresh failed", exc_info=True)
                try:
                    if refresh_content:
                        self._sync_activity(card)
                except Exception:
                    pass
            cards.append(card)
        if sec["kind"] == "series":
            self._series_cards[sec["index"]] = cards
    # 4. headers: reuse by position (text refreshed, collapse rebound),
    # destroy extras, create missing.
    try:
        _old_headers = list(getattr(self, "_series_headers", []) or [])
    except Exception:
        _old_headers = []
    _new_headers: list = []
    for pos, sec in enumerate(_sections):
        if pos < len(_old_headers):
            hdr = _old_headers[pos]
            try:
                self._retitle_header(hdr, sec["text"], sec["index"], sec["collapsed"])
            except Exception:
                pass
            _new_headers.append(hdr)
        else:
            try:
                hdr = self._make_series_header(
                    sec["text"], len(sec["items"]), hub_name=sec["hub"],
                    collapsed=sec["collapsed"], index=sec["index"],
                )
            except Exception:
                continue
            _new_headers.append(hdr)
    for hdr in _old_headers[len(_new_headers):]:
        try:
            self.items_layout.removeWidget(hdr)
        except Exception:
            pass
        try:
            # Hide before orphaning (stillborn-toplevel guard).
            hdr.hide()
            hdr.setParent(None)
            hdr.deleteLater()
        except Exception:
            pass
    self._series_headers = _new_headers
    # 5. plan target cells, then relayout ONLY when the live grid already
    # diverges. Append already places the fresh card at the tail; the
    # set_triage that follows describes the SAME plan. Re-adding every
    # widget identically there is a second visible reposition (bug 3:
    # "jumps twice"). Compute the target and skip the takeAt/addWidget
    # storm when the layout already matches — set_series then converges
    # to a no-op instead of jumping.
    #
    # Wide viewports split sections into two side-by-side bands (first
    # section left, the rest right, draggable separator between) so the
    # right half fills instead of staying empty; narrow windows stack
    # every section full-width as before.
    _plan: list[tuple] = []
    # Same eager responsive columns as rebuild_grid: a series view built
    # before the adapt timer must not plan at the stale GRID_COLUMNS.
    if self._view_mode == VIEW_GRID:
        try:
            self._applied_columns = int(self._compute_columns())
        except Exception:
            pass
    # Discriminator for the "splitter flashes on the first frames" report:
    # banding needs >= 2 sections, so log the section set + band inputs at
    # every series rebuild. Run with IMGSLI_GALLERY_DEBUG=1 to capture it.
    try:
        from tabs.image_gallery.debug import gallery_debug as _gdbg

        _gdbg(
            "layout: sections=%d kinds=%s ungrouped=%d cols=%s split_left=%s band_state=%s",
            len(_sections),
            [s.get("kind") for s in _sections],
            len(list(getattr(self, "_ungrouped", []) or [])),
            getattr(self, "grid_columns", None),
            getattr(self, "_split_left", None),
            getattr(self, "_band_state", None),
        )
    except Exception:
        pass
    try:
        _bands = self._plan_bands(_sections)
    except Exception:
        _bands = [(_sections, self.grid_columns, 0)]
    _band_state_new = None
    _plan_rows = 0
    _plan_hdr = 0
    for _subset, _bcols, _coff in _bands:
        try:
            _entries, _used, _plan_hdr = self._plan_band_entries(
                _subset, int(_bcols), int(_coff), 0, _new_headers, int(_plan_hdr))
        except Exception:
            continue
        _plan.extend(_entries)
        _plan_rows = max(int(_plan_rows), int(_used))
    if len(_bands) > 1:
        try:
            _sep = self._ensure_band_separator()
            _sep_col = int(_bands[0][1])  # left band width == separator column
            if _sep is not None:
                _plan.append((_sep, 0, _sep_col, max(1, int(_plan_rows)), 1))
                _band_state_new = (int(_bands[0][1]), int(_bands[1][1]), int(_sep_col))
        except Exception:
            _band_state_new = None
    try:
        self._band_state = _band_state_new
    except Exception:
        pass
    _layout_matches = False
    try:
        _layout_matches = self.items_layout.count() == len(_plan)
        if _layout_matches:
            for _w, _r, _c, _rs, _cs in _plan:
                _idx = self.items_layout.indexOf(_w)
                if _idx < 0:
                    _layout_matches = False
                    break
                _gr, _gc, _grs, _gcs = self.items_layout.getItemPosition(_idx)
                if (int(_gr), int(_gc), int(_grs), int(_gcs)) != (_r, _c, _rs, _cs):
                    _layout_matches = False
                    break
    except Exception:
        _layout_matches = False
    if _layout_matches:
        current_row = _plan_rows
        for _w, _r, _c, _rs, _cs in _plan:
            try:
                _w.show()
            except Exception:
                logger.debug("_rebuild_series: reveal matched widget failed", exc_info=True)
    else:
        # Drop layout items only (widgets stay alive/parented), re-add per
        # plan (stacked or banded — same math as the plan above).
        while self.items_layout.count():
            try:
                self.items_layout.takeAt(0)
            except Exception:
                break
        if _band_state_new is None:
            try:
                self._hide_band_separator()
            except Exception:
                pass
        current_row = 0
        for _w, _r, _c, _rs, _cs in _plan:
            try:
                self.items_layout.addWidget(_w, _r, _c, _rs, _cs)
                _w.show()
            except Exception:
                logger.debug("_rebuild_series: widget placement failed", exc_info=True)
        current_row = _plan_rows

    self._sync_series_column_widths(series_mode=True)
    try:
        # The separator column is a thin handle, not a card column —
        # _sync above pins every column to the card width.
        if self._band_state is not None:
            self.items_layout.setColumnMinimumWidth(
                int(self._band_state[2]), scaled_px(GRID_SEPARATOR_COL_W))
    except Exception:
        pass
    self.apply_selection(self._selection)
    self._update_host_height_for_series(current_row)
    if not _layout_matches:
        # Commit the new geometry synchronously before the next paint.
        # Without this the re-added cards lay out only on the following
        # event-loop turn, so an already-visible neighbour (e.g. the
        # UNGROUPED tail sliding up/down) keeps its stale rect for one
        # frame and paints over the freshly revealed series cards.
        try:
            self.items_layout.activate()
        except Exception:
            logger.debug("_rebuild_series: layout activate failed", exc_info=True)
    try:
        if _bar is not None:
            _bar.setValue(min(int(_saved_scroll), int(_bar.maximum())))
    except Exception:
        pass
    try:
        self._restore_focus(_focus_snapshot)
    except Exception:
        pass

def _rebuild_series_geometry(view) -> None:
    """Re-plan the series layout for a new width — geometry only, no re-stamp.

    Used by the resize path (``columns._adapt_columns_and_reflow``): the column
    count changed, so headers/bands/cells must move, but no card's CONTENT
    depends on the width. Cheap on purpose — a running analysis resizes with
    hundreds of live cards.
    """
    _rebuild_series(view, refresh_content=False)

def _tail_header_span(view) -> int:
    """Column span for the UNGROUPED tail header (right band when split)."""
    self = view
    try:
        st = getattr(self, "_band_state", None)
        if st:
            return max(1, int(st[1]))
    except Exception:
        pass
    try:
        return max(1, int(self.grid_columns))
    except Exception:
        return GRID_COLUMNS

def _would_band_with(view, sections_count: int) -> bool:
    """True when *sections_count* sections would lay out side-by-side."""
    self = view
    try:
        if self._view_mode == VIEW_LIST:
            return False
        return int(self._applied_columns) >= GRID_BAND_MIN_TOTAL and int(sections_count) >= 2
    except Exception:
        return False

def _refresh_ungrouped_header_count(view, total: int) -> None:
    """Recreate only the UNGROUPED tail header with a fresh count.

    One widget swapped in place (layout row preserved) — not the full
    teardown ``_rebuild_series`` performs. Everything else (series
    headers, all cards) is untouched.
    """
    self = view
    try:
        headers = list(getattr(self, "_series_headers", []) or [])
        pos = next(
            (i for i, h in enumerate(headers)
             if getattr(h, "objectName", lambda: "")() == "GallerySeriesHeader_ungrouped"),
            None,
        )
        if pos is None:
            return
        old = headers[pos]
        try:
            row = self._row_of(old)
        except Exception:
            row = None
        try:
            self.items_layout.removeWidget(old)
        except Exception:
            pass
        try:
            _old_btn = old.findChild(Button)
            if _old_btn is not None:
                _disconnect_btn_theme(_old_btn)
        except Exception:
            pass
        try:
            # Same stillborn-toplevel guard as _clear_series_headers:
            # hide before setParent(None), or the visible header maps
            # its own toplevel + activation token for a few ms.
            old.hide()
        except Exception:
            pass
        try:
            old.setParent(None)
            old.deleteLater()
        except Exception:
            pass
        header = self._make_series_header(
            self._ungrouped_header_text(int(total)), int(total),
            hub_name=None,
            collapsed=bool(getattr(self, "_tail_collapsed", False)), index=None,
        )
        headers[pos] = header
        self._series_headers = headers
        try:
            if row is None:
                row = int(self.items_layout.rowCount())
            self.items_layout.addWidget(header, row, 0, 1, self._tail_header_span())
            header.show()
        except Exception:
            pass
    except Exception:
        pass

def _row_of(view, widget) -> int | None:
    """Layout row of *widget* in the items grid (None when absent)."""
    self = view
    try:
        idx = self.items_layout.indexOf(widget)
        if idx < 0:
            return None
        r, _, _, _ = self.items_layout.getItemPosition(idx)
        return int(r)
    except Exception:
        return None

def _make_series_header(
    view,
    text: str,
    count: int = 0,
    hub_name: str | None = None,
    collapsed: bool = False,
    index: int | None = None,
) -> QWidget:
    """Series header — ghost Button with the 3×14 accent bar as its own layer (real_design.md:59)."""
    self = view
    is_collapsible = index is not None
    # The collapse arrow is a painter layer at the button's right edge,
    # never trailing text — long hub names elide without clipping it.
    display = _strip_header_arrow(text)
    # Container with 3×14 bar
    container = QWidget(self.items_host)
    container.setObjectName(f"GallerySeriesHeader_{index}" if is_collapsible else "GallerySeriesHeader_ungrouped")
    try:
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    except Exception:
        pass
    from PySide6.QtWidgets import QHBoxLayout

    lay = QHBoxLayout(container)
    lay.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
    lay.setSpacing(0)
    if is_collapsible:
        _header_col3 = _gallery_header_text_color()

        btn = Button(
            regions=[
                ButtonRegion(
                    id="_main",
                    rows=[ButtonRow(text=display.upper(), size=16, color=_header_col3, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True)],
                )
            ],
            variant="ghost",
            size=(0, 24),  # design px — Button scales internally (no scaled_px)
            # 3px bar + 12px gap the sibling widget used to occupy;
            # right reserve keeps the elided title clear of the arrow layer.
            content_padding=(scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0),
            extra_layers=[_SeriesHeaderAccentLayer(collapsible=is_collapsible),
                            _SeriesDropTargetLayer(),
                            _SeriesCollapseArrowLayer(collapsible=True, collapsed=collapsed)],
            parent=container,
        )
        btn.setObjectName(f"GallerySeriesHeaderBtn_{index}")
        # NOTE: no theme_changed.connect(btn.update) here on purpose —
        # Button.__init__ already subscribes, and a duplicate connection
        # is undisconnectable by slot (disconnect removes one, later
        # calls return False), leaving a stale slot that fires into the
        # dead wrapper on the next theme flip (order-dependent suite
        # crash: stale Button.update with garbage self).
        try:
            btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
        except Exception:
            pass
        try:
            self._series_header_labels[index] = display
        except Exception:
            pass
        # Right-click on the series header opens a menu (Ask AI over the
        # whole series); left-click still collapses/expands.
        try:
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, i=index, b=btn: self._handle_series_context(b, i, _pos)
            )
            btn._gallery_ctx_menu_wired = True  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            btn.setFixedHeight(scaled_px(24))
        except Exception:
            pass
        lay.addWidget(btn, 1)
        try:
            lay.setAlignment(btn, Qt.AlignmentFlag.AlignVCenter)
        except Exception:
            pass
        return container
    try:
        _header_col4 = _gallery_header_text_color()

        btn = Button(
            regions=[
                ButtonRegion(
                    id="_main",
                    rows=[ButtonRow(text=display.upper(), size=16, color=_header_col4, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0, elide=True)],
                )
            ],
            variant="ghost",
            size=(0, 24),  # design px — Button scales internally (no scaled_px)
            # 3px bar + 12px gap the sibling widget used to occupy; the
            # right reserve keeps the elided title clear of the arrow
            # layer. UNGROUPED is a NORMAL collapsible group (same
            # affordance as a series), so the provisional pool is not a
            # dead, glyph-less header while clustering runs.
            content_padding=(scaled_px(15), 0, scaled_px(SERIES_ARROW_RESERVE), 0),
            extra_layers=[_SeriesHeaderAccentLayer(collapsible=is_collapsible),
                            _SeriesDropTargetLayer(),
                            _SeriesCollapseArrowLayer(collapsible=True, collapsed=bool(collapsed))],
            parent=container,
        )
        btn.setObjectName("GallerySeriesHeader_ungrouped_btn")
        # NOTE: no theme_changed.connect(btn.update) — see above,
        # Button.__init__ already subscribes; duplicates are
        # undisconnectable and crash the suite via stale slots.
        try:
            btn.setFixedHeight(scaled_px(24))
        except Exception:
            pass
        try:
            btn.clicked.connect(lambda _checked=False: self._toggle_collapse(None))  # type: ignore[misc]
        except Exception:
            pass
        lay.addWidget(btn, 1)
        return container
    except Exception:
        # Fallback: Text container with theme token
        container = QWidget(self.items_host)
        container.setObjectName("GallerySeriesHeader")
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(container)
        lay.setContentsMargins(scaled_px(8), scaled_px(4), scaled_px(8), scaled_px(4))
        lay.setSpacing(0)
        lbl = Text(display, mode="plain", pixel_size=16, parent=container)
        lbl.setObjectName("GallerySeriesHeaderLabel")
        try:
            lbl.setBold(True)
        except Exception:
            pass
        lay.addWidget(lbl)
        lay.addStretch(1)
        try:
            from sli_ui_toolkit.managers import ThemeManager
            from ui.theming import resolve_theme_color

            token = "gallery.grid.background"
            bg = resolve_theme_color(ThemeManager.get_instance(), token)
            apply_opaque_widget_fill(container, bg)
        except Exception:
            pass
        try:
            container.setFixedHeight(scaled_px(24))
        except Exception:
            pass
        return container

def _toggle_collapse(view, index: int | None) -> None:
    """Toggle collapsed state for series *index* (None = UNGROUPED tail)."""
    self = view
    if index is None:
        try:
            self._tail_collapsed = not bool(getattr(self, "_tail_collapsed", False))
        except Exception:
            return
        try:
            self._rebuild_series()
        except Exception:
            pass
        return
    try:
        idx = int(index)
    except Exception:
        return
    try:
        cur = bool(self._collapsed.get(idx, False))
        self._collapsed[idx] = not cur
    except Exception:
        return
    # Rebuild series to reflect new collapsed state (keeps hub_names)
    try:
        self._rebuild_series()
    except Exception:
        pass

def _clear_series_headers(view) -> None:
    self = view
    for hdr in list(self._series_headers):
        try:
            self.items_layout.removeWidget(hdr)
        except Exception:
            pass
        try:
            _btn = hdr.findChild(Button)
            if _btn is not None:
                _disconnect_btn_theme(_btn)
        except Exception:
            pass
        try:
            # Hide BEFORE dropping the parent: a still-visible widget
            # reparented to None instantly becomes a top-level window
            # (own wl_surface + xdg_toplevel + activation token on
            # Wayland) for the ms until deleteLater fires — the
            # unconsumable startup sequence behind the per-switch
            # global busy cursor. Hidden widgets never map.
            hdr.hide()
        except Exception:
            pass
        try:
            hdr.setParent(None)
            hdr.deleteLater()
        except Exception:
            pass
    self._series_headers.clear()

def _update_host_height_for_series(view, total_rows: int) -> None:
    """Host height when series headers are present (headers + card rows)."""
    self = view
    if total_rows <= 0:
        try:
            self.items_host.setMinimumHeight(1)
        except Exception:
            pass
        return
    # Each header is one row of fixed 24px; cards use the mode height.
    # Count headers vs card rows: headers already counted in total_rows.
    # Approximate: total_rows includes header rows (1 row each) + card rows.
    # For precise height, sum header heights + card rows heights + spacings.
    num_headers = len(self._series_headers)
    # total_rows = num_headers + card_grid_rows
    card_rows = total_rows - num_headers
    header_h = scaled_px(24)
    card_h = self._card_height_px()
    spacing = scaled_px(GRID_SPACING)
    margins = scaled_px(GRID_MARGIN_TOP) + scaled_px(GRID_MARGIN_BOTTOM)
    # Header rows: header_h each; card rows: card_h each; spacing between every row.
    needed = margins
    if num_headers > 0:
        needed += num_headers * header_h
    if card_rows > 0:
        needed += card_rows * card_h
    # spacings = max(0, total_rows -1) * spacing
    if total_rows > 1:
        needed += (total_rows - 1) * spacing
    try:
        self.items_host.setMinimumHeight(needed)
    except Exception:
        pass

def retranslate_headers(view) -> None:
    """Re-resolve series/UNGROUPED header text + card content in place.

    Cheap chrome refresh for a live language switch: reuses the existing
    header (``_rebuild_series``'s surgical reconcile retitles headers and
    updates kept cards without hide/reparent) and card widgets, so scroll,
    focus and selection survive. On a flat (no-series) grid the header
    rebuild is skipped — ``_rebuild_series`` would tear the flat pool down
    — and only card content is refreshed.
    """
    self = view
    try:
        if getattr(self, "_series", None) is not None:
            self._rebuild_series()
            return
    except Exception:
        pass
    try:
        self.refresh_cards(list(getattr(self, "_items", None) or []))
    except Exception:
        pass
