"""Virtualized grid for the Image Gallery tab — Stage 1 MVP.
Audit-Meta: pattern=state-machine size=exempt reason="single virtualized grid view — grid_columns/series headers/pool/marquee share one layout lifecycle"

Uses ``OverlayScrollArea`` + ``OpaqueFillHost`` + ``QGridLayout`` with a
reused ``Button`` pool (4 columns, rebuild_grid / refresh_card /
set_card_visible / apply_selection). Keeps the same contracts as
``session_picker/recent/items_view.py`` but simplified for a flat 4-column
layout (no list mode, no virtual row window for Stage 1). ``scaled_px`` is
used for every geometry constant; no ad-hoc stylesheets — painter pipeline
owns visuals.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.widgets import Button, ButtonRegion, ButtonRow, Label, OverlayScrollArea

from tabs.image_gallery.models import GalleryItem
from tabs.image_gallery.ui.card import (
    GALLERY_CARD_H,
    GALLERY_CARD_W,
    apply_gallery_selection,
    build_gallery_card,
    gallery_selection_accent,
    update_gallery_card,
)
from ui.widgets.shelf import OpaqueFillHost, apply_opaque_widget_fill

# real_design.md:2.3 — gap 24, root pad already 24, inner margins 0
GRID_COLUMNS = 4
GRID_SPACING = 24
GRID_MARGIN = 0
GRID_MARGIN_TOP = 0
GRID_MARGIN_BOTTOM = 0

# Optional virtual buffer for later full virtualization; not used in MVP rebuild
# but kept for marquee hit-testing parity.
VIRTUAL_ROW_BUFFER = 1


def _is_dark() -> bool:
    """Darkness for fallback selection — delegates to ``dots._is_dark``."""
    try:
        from tabs.image_gallery.ui.card.dots import _is_dark as _dots_is_dark

        return bool(_dots_is_dark())
    except Exception:
        return True


def _resolve_section_bar_color(collapsible: bool):
    """Section header bar color with a light/dark-aware fallback.

    Collapsible series: ``gallery.accent.bar`` → ``accent`` →
    ``#0078D4`` (light) / ``#0096FF`` (dark). UNGROUPED tail:
    ``dialog.border`` → ``#c0c0c0`` (light) / ``#555555`` (dark).
    """
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        mgr = _TM.get_instance()
        if collapsible:
            for tok in ("gallery.accent.bar", "accent"):
                c = _trc(mgr, tok)
                if c is not None:
                    return _QC(c) if isinstance(c, str) else c
        else:
            c = _trc(mgr, "dialog.border")
            if c is not None:
                return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if collapsible:
        return _QC("#0096FF") if _is_dark() else _QC("#0078D4")
    return _QC("#555555") if _is_dark() else _QC("#c0c0c0")


def _gallery_header_text_color():
    """Series header text: ``gallery.header.text`` → light/dark fallback."""
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        c = _trc(_TM.get_instance(), "gallery.header.text")
        if c is not None:
            return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if _is_dark():
        return _QC(154, 154, 154)
    return _QC(0x38, 0x38, 0x38)


def _grid_substrate_color():
    """Grid viewport substrate: gallery-scoped, NOT the global surface.

    Chain: ``gallery.grid.background`` → ``surface.background`` →
    ``#ffffff`` (light) / ``#2b2b2b`` (dark). White-cards + visible-borders
    philosophy (mockups v2/v3/v4-light): the grid is white and cards read
    via their 1px ``gallery.card.border`` hairline — the gray substrate is
    dead. ``Window``/``surface.background`` stay app-global near-white (a
    global ``#cecece`` leaked into every autoFillBackground widget app-wide —
    see plan 2026-09-23 rescope).
    Rule A: keyed on ``is_dark()`` (light default).
    """
    from PySide6.QtGui import QColor as _QC

    try:
        from sli_ui_toolkit.managers import ThemeManager as _TM
        from ui.theming import try_resolve_theme_color as _trc

        mgr = _TM.get_instance()
        for tok in ("gallery.grid.background", "surface.background"):
            c = _trc(mgr, tok)
            if c is not None:
                return _QC(c) if isinstance(c, str) else c
    except Exception:
        pass
    if _is_dark():
        return _QC(0x2B, 0x2B, 0x2B)
    return _QC(0xFF, 0xFF, 0xFF)


class _SeriesHeaderBar(QWidget):
    """3×14 section bar painted explicitly from a cached theme color.

    Replaces the palette/auto-fill path (THEMING.md warm-up quirk):
    background is painted in ``paintEvent`` from a cached ``QColor`` and
    re-resolved on ``theme_changed``.
    """

    def __init__(self, parent: QWidget | None = None, *, collapsible: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("GallerySeriesHeaderBar")
        self._collapsible = bool(collapsible)
        self._bar_color = _resolve_section_bar_color(self._collapsible)
        try:
            self.setFixedSize(scaled_px(3), scaled_px(14))
        except Exception:
            pass
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def _on_theme_changed(self) -> None:
        try:
            self._bar_color = _resolve_section_bar_color(self._collapsible)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event) -> None:  # noqa: N802
        try:
            from PySide6.QtGui import QPainter

            p = QPainter(self)
            try:
                p.fillRect(self.rect(), self._bar_color)
            except Exception:
                pass
            try:
                p.end()
            except Exception:
                pass
        except Exception:
            pass
        try:
            super().paintEvent(event)
        except Exception:
            pass


class GalleryGridView(QWidget):
    """Scrollable 4-column gallery grid with pooled Button cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GalleryGridView")
        self._items: list[GalleryItem] = []
        self._cards_by_path: dict[str, object] = {}
        self._pool: list[object] = []
        self._selection: set[str] = set()
        self._selection_accent = gallery_selection_accent()
        self._on_toggle = None
        self._on_context_menu = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = OverlayScrollArea(self)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)
        scroll.setAcceptDrops(True)
        root.addWidget(scroll, 1)
        self.scroll_area = scroll

        host = OpaqueFillHost()
        host.setAcceptDrops(True)
        host.setMouseTracking(True)
        host.installEventFilter(self)
        scroll.setWidget(host)
        self.items_host = host

        layout = QGridLayout()
        layout.setContentsMargins(
            scaled_px(GRID_MARGIN),
            scaled_px(GRID_MARGIN_TOP),
            scaled_px(GRID_MARGIN),
            scaled_px(GRID_MARGIN_BOTTOM),
        )
        layout.setHorizontalSpacing(scaled_px(GRID_SPACING))
        layout.setVerticalSpacing(scaled_px(GRID_SPACING))
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        host.setLayout(layout)
        self.items_layout = layout

        # Marquee gesture lives on the host; created lazily via marquee module.
        self._marquee_gesture = None
        self._marquee_additive = False
        self._marquee_base: set[str] = set()

        # Stage 2 series grouping — headers only for clusters ≥2, singles under UNGROUPED tail.
        self._series: list[list[GalleryItem]] | None = None
        self._ungrouped: list[GalleryItem] = []
        self._series_headers: list[QWidget] = []
        self._hub_names: list[str | None] = []
        self._collapsed: dict[int, bool] = {}
        self._series_cards: dict[int, list[object]] = {}
        # A2: mode for per-dot card colors (fidelity/camera/batch_synthetic) — proxied from widget set_triage.
        self._mode: object = None
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_gallery_theme_changed)
        except Exception:
            pass
        try:
            self.set_fill_color(_grid_substrate_color())
        except Exception:
            pass

    def _on_gallery_theme_changed(self) -> None:
        """Repaint grid surfaces on theme flip: accent, card fills, selection."""
        try:
            self.set_fill_color(_grid_substrate_color())
        except Exception:
            pass
        try:
            self._selection_accent = gallery_selection_accent()
        except Exception:
            pass
        try:
            cards = list(self._cards_by_path.values()) + list(self._pool)
            for card in cards:
                try:
                    card.update()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass
        try:
            self.update()
        except Exception:
            pass

    # -- configuration -----------------------------------------------------

    def configure(self, *, on_toggle=None, on_context_menu=None) -> None:
        self._on_toggle = on_toggle
        self._on_context_menu = on_context_menu

    # -- public API expected by controller/widget --------------------------

    # Systemic fix 2026-08-26: O(N) sync rebuild blocked UI for 1k+ items
    # (measured 7s for 1037). Chunk via event-loop so UI stays responsive.
    _REBUILD_CHUNK = 80
    _rebuild_pending: list[GalleryItem] | None = None
    _rebuild_index: int = 0

    def _resolve_mode(self, explicit: object = None) -> object:
        """Resolve current gallery mode (fidelity/camera/batch_synthetic) for per-dot colors."""
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

    def rebuild_grid(self, items: list[GalleryItem], mode: object = None, *, paint_selection: bool = True) -> None:
        """Clear and rebuild the 4-column grid from *items* (pool-reusing Buttons).

        ``mode`` controls per-dot artifact palette; proxied to ``build_gallery_card``.
        ``paint_selection=False`` skips the closing selection sweep — the
        widget passes it when a series restore follows in the same tick and
        sweeps once itself (else every rebuild pays two full sweeps).
        """
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
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            w = item.widget()
            if w is not None and w not in list(self._cards_by_path.values()) and w not in self._pool and w not in self._series_headers:
                w.setParent(None)

        self._items = list(items)
        self._series = None
        self._ungrouped = []
        self._hub_names = []
        self._collapsed = {}
        self._series_cards = {}
        self._cards_by_path.clear()

        if not items:
            self._update_host_height(0)
            return

        # Large folders: chunk to keep event loop alive (systemic vs 1037 sync)
        if len(items) > self._REBUILD_CHUNK * 2:
            self._rebuild_pending = list(items)
            self._rebuild_index = 0
            self._update_host_height(len(items))  # reserve height early so scrollbar correct
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, self._rebuild_next_chunk)
            return

        for idx, item in enumerate(items):
            card = self._acquire_card(item)
            self._cards_by_path[str(item.path)] = card
            r, c = divmod(idx, GRID_COLUMNS)
            self.items_layout.addWidget(card, r, c)
            card.show()

        if paint_selection:
            self.apply_selection(self._selection)
        self._update_host_height(len(items))

    def _rebuild_next_chunk(self) -> None:
        pending = getattr(self, "_rebuild_pending", None)
        if pending is None:
            return
        start = getattr(self, "_rebuild_index", 0)
        end = min(start + self._REBUILD_CHUNK, len(pending))
        for idx in range(start, end):
            item = pending[idx]
            card = self._acquire_card(item)
            self._cards_by_path[str(item.path)] = card
            r, c = divmod(idx, GRID_COLUMNS)
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

    # -- Stage 2 series grouping ----------------------------------------

    def set_series(
        self,
        series: list[list[GalleryItem]] | None,
        hub_names: list[str | None] | None = None,
        collapsed: dict[int, bool] | set[int] | list[bool] | None = None,
        mode: object = None,
    ) -> None:
        """Rebuild grid with series sections.

        *series* — list of clusters, each cluster ≥2 members. Singles
        (items not in any cluster) are collected under an ``UNGROUPED`` tail.
        ``None`` or empty clears series mode and falls back to flat ``rebuild_grid``.
        *hub_names* — per-series hub display name (e.g. source file name).
        *collapsed* — mapping of series index → collapsed bool (or set of collapsed indices).
        *mode* — gallery mode for per-dot colors (fidelity/camera/batch_synthetic), proxied to cards.
        """
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
            # Filter clusters ≥2 per spec.
            filtered = [list(s) for s in series if len(s) >= 2]
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
        # Normalize hub_names
        if hub_names is not None:
            try:
                self._hub_names = list(hub_names)[: len(filtered)]
                # Pad if shorter
                while len(self._hub_names) < len(filtered):
                    self._hub_names.append(None)
            except Exception:
                self._hub_names = [None] * len(filtered)
        else:
            self._hub_names = [None] * len(filtered)
        # Normalize collapsed
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

    def _retitle_header(self, header, text: str, index, collapsed: bool = False) -> None:
        """Refresh a reused series header in place (no destroy/create).

        Updates the label text, object names and the collapse-button closure
        (which captures the section index — a reused widget at a new
        position must toggle the new section). UNGROUPED headers (index
        None) get their toggle disconnected.
        """
        display = str(text or "").strip()
        is_collapsible = index is not None
        arrow = "▸" if collapsed else "▾"
        if is_collapsible:
            if not display.endswith("▾") and not display.endswith("▸"):
                display = f"{display} {arrow}"
            elif display[-1] in ("▾", "▸"):
                display = display[:-1].strip() + f" {arrow}"
        else:
            if display.endswith("▾") or display.endswith("▸"):
                display = display[:-1].strip()
        try:
            header.setObjectName(
                f"GallerySeriesHeader_{index}" if is_collapsible else "GallerySeriesHeader_ungrouped"
            )
        except Exception:
            pass
        try:
            btn = header.findChild(Button)
        except Exception:
            btn = None
        if btn is None:
            return
        try:
            btn.setObjectName(
                f"GallerySeriesHeaderBtn_{index}" if is_collapsible else "GallerySeriesHeader_ungrouped_btn"
            )
        except Exception:
            pass
        try:
            btn.update_region(
                "_main",
                rows=[ButtonRow(
                    text=display.upper(), size=11, color=_gallery_header_text_color(),
                    h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0,
                )],
            )
        except Exception:
            pass
        try:
            btn.clicked.disconnect()
        except Exception:
            pass
        if is_collapsible:
            try:
                btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
            except Exception:
                pass

    def _rebuild_series(self) -> None:
        """Internal: rebuild with series headers + UNGROUPED tail."""
        # Preserve scroll + keyboard focus across the teardown: heights land
        # identical, but the intermediate collapse clamps the scrollbar to 0
        # and reparenting drops focus to None (keyboard dead until a click).
        try:
            _bar = self.scroll_area.verticalScrollBar()
            _saved_scroll = int(_bar.value())
        except Exception:
            _bar = None
            _saved_scroll = 0
        _focus_path: str | None = None
        try:
            from PySide6.QtWidgets import QApplication as _QApp

            _fw = _QApp.focusWidget()
            _host = getattr(self, "items_host", None)
            if _fw is not None and _host is not None and _host.isAncestorOf(_fw):
                try:
                    _prop = _fw.property("gallery_path")
                    _focus_path = str(_prop) if _prop else None
                except Exception:
                    _focus_path = None
                if not _focus_path:
                    try:
                        _ip = getattr(getattr(_fw, "_gallery_item", None), "path", None)
                        _focus_path = str(_ip) if _ip else None
                    except Exception:
                        _focus_path = None
        except Exception:
            _focus_path = None
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
            while self.items_layout.count():
                try:
                    self.items_layout.takeAt(0)
                except Exception:
                    break
            self._cards_by_path.clear()
            self._series_cards = {}
            return
        try:
            _mode = self._resolve_mode()
        except Exception:
            _mode = None
        # 1. plan sections (same order/texts as the old full rebuild).
        _sections: list[dict] = []
        for idx, cluster in enumerate(list(self._series or [])):
            hub = self._hub_names[idx] if idx < len(self._hub_names) else None
            is_collapsed = bool(self._collapsed.get(idx, False))
            if hub:
                header_text = f"SERIES {idx + 1} · {hub} · {len(cluster)} VARIANTS"
            else:
                header_text = f"SERIES {idx + 1} · {len(cluster)} images"
            _sections.append({
                "kind": "series", "index": idx, "hub": hub,
                "collapsed": is_collapsed, "text": header_text,
                "items": list(cluster) if not is_collapsed else [],
            })
        if list(getattr(self, "_ungrouped", []) or []):
            _sections.append({
                "kind": "tail", "index": None, "hub": None,
                "collapsed": False,
                "text": f"UNGROUPED · {len(list(getattr(self, '_ungrouped', []) or []))}",
                "items": list(getattr(self, "_ungrouped", []) or []),
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
                        update_gallery_card(card, item, mode=_mode)  # type: ignore[arg-type]
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
                hdr.setParent(None)
                hdr.deleteLater()
            except Exception:
                pass
        self._series_headers = _new_headers
        # 5. relayout: drop layout items only (widgets stay alive/parented),
        # re-add per plan with the same row math as before.
        while self.items_layout.count():
            try:
                self.items_layout.takeAt(0)
            except Exception:
                break
        current_row = 0
        _hdr_pos = 0
        for sec in _sections:
            try:
                header = _new_headers[_hdr_pos]
                _hdr_pos += 1
            except Exception:
                continue
            try:
                self.items_layout.addWidget(header, current_row, 0, 1, GRID_COLUMNS)
                header.show()
            except Exception:
                pass
            current_row += 1
            if sec["kind"] == "series" and sec["collapsed"]:
                continue
            for pos, item in enumerate(sec["items"]):
                try:
                    card = self._cards_by_path.get(str(item.path))
                except Exception:
                    card = None
                if card is None:
                    continue
                try:
                    r, c = divmod(pos, GRID_COLUMNS)
                    self.items_layout.addWidget(card, current_row + r, c)
                    card.show()
                except Exception:
                    pass
            rows_needed = (len(sec["items"]) + GRID_COLUMNS - 1) // GRID_COLUMNS if sec["items"] else 0
            current_row += rows_needed

        self.apply_selection(self._selection)
        self._update_host_height_for_series(current_row)
        try:
            if _bar is not None:
                _bar.setValue(min(int(_saved_scroll), int(_bar.maximum())))
        except Exception:
            pass
        try:
            if _focus_path:
                _card = self._cards_by_path.get(_focus_path)
                if _card is not None and _card.isVisible() and _card.isEnabled():
                    _card.setFocus()
        except Exception:
            pass

    def append_new_cards(self, items: list[GalleryItem]) -> None:
        """Append-only fast path for pool growth (drop-append).

        Keeps every painted card/header in place — no flat teardown, no
        restore pass. New cards land in the UNGROUPED tail when a series
        view is live (creating the tail header on first use), else at the
        flat grid end. Falls back to a full ``rebuild_grid`` when there is
        no safe incremental plan (e.g. a chunked rebuild still in flight).
        """
        fresh = [it for it in (items or [])]
        if not fresh:
            return
        if getattr(self, "_rebuild_pending", None) is not None:
            self.rebuild_grid(list(getattr(self, "_items", []) or []) + list(fresh))
            return
        try:
            self._items = list(getattr(self, "_items", []) or []) + list(fresh)
        except Exception:
            pass
        if getattr(self, "_series", None) is None:
            try:
                start = max(0, len(list(getattr(self, "_items", []) or [])) - len(fresh))
                for pos, item in enumerate(fresh):
                    card = self._acquire_card(item)
                    self._cards_by_path[str(item.path)] = card
                    r, c = divmod(start + pos, GRID_COLUMNS)
                    self.items_layout.addWidget(card, r, c)
                    card.show()
            except Exception:
                pass
            try:
                self._update_host_height(len(list(getattr(self, "_items", []) or [])))
            except Exception:
                pass
        else:
            try:
                if not list(getattr(self, "_ungrouped", []) or []):
                    row = int(self.items_layout.rowCount())
                    header = self._make_series_header(
                        f"UNGROUPED · {len(fresh)}", len(fresh),
                        hub_name=None, collapsed=False, index=None,
                    )
                    self._series_headers.append(header)
                    self.items_layout.addWidget(header, row, 0, 1, GRID_COLUMNS)
                    header.show()
                else:
                    self._refresh_ungrouped_header_count(len(list(getattr(self, "_ungrouped", []) or [])) + len(fresh))
                base = int(self.items_layout.rowCount())
                pos0 = len(list(getattr(self, "_ungrouped", []) or []))
                for pos, item in enumerate(fresh):
                    card = self._acquire_card(item)
                    self._cards_by_path[str(item.path)] = card
                    r, c = divmod(pos0 + pos, GRID_COLUMNS)
                    self.items_layout.addWidget(card, base + r, c)
                    card.show()
                try:
                    self._ungrouped = list(getattr(self, "_ungrouped", []) or []) + list(fresh)
                except Exception:
                    pass
            except Exception:
                pass
            try:
                self._update_host_height_for_series(int(self.items_layout.rowCount()))
            except Exception:
                pass
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass

    def _refresh_ungrouped_header_count(self, total: int) -> None:
        """Recreate only the UNGROUPED tail header with a fresh count.

        One widget swapped in place (layout row preserved) — not the full
        teardown ``_rebuild_series`` performs. Everything else (series
        headers, all cards) is untouched.
        """
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
                old.setParent(None)
                old.deleteLater()
            except Exception:
                pass
            header = self._make_series_header(
                f"UNGROUPED · {int(total)}", int(total),
                hub_name=None, collapsed=False, index=None,
            )
            headers[pos] = header
            self._series_headers = headers
            try:
                if row is None:
                    row = int(self.items_layout.rowCount())
                self.items_layout.addWidget(header, row, 0, 1, GRID_COLUMNS)
                header.show()
            except Exception:
                pass
        except Exception:
            pass

    def _row_of(self, widget) -> int | None:
        """Layout row of *widget* in the items grid (None when absent)."""
        try:
            idx = self.items_layout.indexOf(widget)
            if idx < 0:
                return None
            r, _, _, _ = self.items_layout.getItemPosition(idx)
            return int(r)
        except Exception:
            return None

    def _make_series_header(
        self,
        text: str,
        count: int = 0,
        hub_name: str | None = None,
        collapsed: bool = False,
        index: int | None = None,
    ) -> QWidget:
        """Series header — accent bar 3×14 + ghost Button (real_design.md:59)."""
        is_collapsible = index is not None
        arrow = "▸" if collapsed else "▾"
        display = text.strip()
        # Only collapsible series get arrow; UNGROUPED has no arrow (SVG)
        if is_collapsible:
            if not display.endswith("▾") and not display.endswith("▸"):
                display = f"{display} {arrow}"
            else:
                if display[-1] in ("▾", "▸"):
                    display = display[:-1].strip() + f" {arrow}"
        else:
            # Strip any arrow for UNGROUPED
            if display.endswith("▾") or display.endswith("▸"):
                display = display[:-1].strip()
        # Container with 3×14 bar
        container = QWidget(self.items_host)
        container.setObjectName(f"GallerySeriesHeader_{index}" if is_collapsible else "GallerySeriesHeader_ungrouped")
        from PySide6.QtWidgets import QHBoxLayout

        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, scaled_px(4), 0, scaled_px(4))
        lay.setSpacing(scaled_px(12))
        # Accent bar 3×14 — explicitly painted themed widget (no palette fill).
        bar = _SeriesHeaderBar(container, collapsible=is_collapsible)
        lay.addWidget(bar)
        try:
            lay.setAlignment(bar, Qt.AlignmentFlag.AlignVCenter)
        except Exception:
            pass
        if is_collapsible:
            _header_col3 = _gallery_header_text_color()

            btn = Button(
                regions=[
                    ButtonRegion(
                        id="_main",
                        rows=[ButtonRow(text=display.upper(), size=11, color=_header_col3, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0)],
                    )
                ],
                variant="ghost",
                size=(0, scaled_px(24)),
                parent=container,
            )
            btn.setObjectName(f"GallerySeriesHeaderBtn_{index}")
            try:
                btn.clicked.connect(lambda _checked=False, idx=index: self._toggle_collapse(idx))  # type: ignore[misc]
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
                        rows=[ButtonRow(text=display.upper(), size=11, color=_header_col4, h_align=Qt.AlignmentFlag.AlignLeft, ratio=1.0)],
                    )
                ],
                variant="ghost",
                size=(0, scaled_px(24)),
                parent=container,
            )
            btn.setObjectName("GallerySeriesHeader_ungrouped_btn")
            try:
                btn.setEnabled(False)
            except Exception:
                pass
            try:
                btn.setFixedHeight(scaled_px(24))
            except Exception:
                pass
            lay.addWidget(btn, 1)
            return container
        except Exception:
            # Fallback: Label container with theme token
            container = QWidget(self.items_host)
            container.setObjectName("GallerySeriesHeader")
            from PySide6.QtWidgets import QHBoxLayout

            lay = QHBoxLayout(container)
            lay.setContentsMargins(scaled_px(8), scaled_px(4), scaled_px(8), scaled_px(4))
            lay.setSpacing(0)
            lbl = Label(display, pixel_size=11, parent=container)
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

    def _toggle_collapse(self, index: int | None) -> None:
        """Toggle collapsed state for series *index* and rebuild."""
        if index is None:
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

    def _clear_series_headers(self) -> None:
        for hdr in list(self._series_headers):
            try:
                self.items_layout.removeWidget(hdr)
            except Exception:
                pass
            try:
                hdr.setParent(None)
                hdr.deleteLater()
            except Exception:
                pass
        self._series_headers.clear()

    def _update_host_height_for_series(self, total_rows: int) -> None:
        """Host height when series headers are present (headers + card rows)."""
        if total_rows <= 0:
            try:
                self.items_host.setMinimumHeight(1)
            except Exception:
                pass
            return
        # Each header is one row of fixed 24px; cards still use GALLERY_CARD_H.
        # Count headers vs card rows: headers already counted in total_rows.
        # Approximate: total_rows includes header rows (1 row each) + card rows.
        # For precise height, sum header heights + card rows heights + spacings.
        num_headers = len(self._series_headers)
        # total_rows = num_headers + card_grid_rows
        card_rows = total_rows - num_headers
        header_h = scaled_px(24)
        card_h = scaled_px(GALLERY_CARD_H)
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

    def refresh_card(self, item: GalleryItem) -> None:
        card = self._cards_by_path.get(str(item.path))
        if card is None:
            return
        try:
            update_gallery_card(card, item, mode=self._resolve_mode())  # type: ignore[arg-type]
        except Exception:
            pass
        # Re-apply selection tint in case accent changed.
        self.apply_selection(self._selection)

    def refresh_cards(self, items) -> None:
        """Batch card refresh: one content update per card, ONE selection sweep.

        Delivery handlers (artifact/fidelity analysis) used to call
        ``refresh_card`` per item, each re-running ``apply_selection`` over
        the whole grid — O(N^2) region updates + repaints on the UI thread
        in a single delivery, stalling the event loop (compositor busy
        cursor, dropped overlay frames) exactly when quick look shows new
        severities. Single-call behavior of ``refresh_card`` is unchanged.
        """
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
        for item in items:
            try:
                card = self._cards_by_path.get(str(item.path))
            except Exception:
                continue
            if card is None:
                continue
            try:
                update_gallery_card(card, item, mode=mode)  # type: ignore[arg-type]
            except Exception:
                pass
        try:
            self.apply_selection(self._selection)
        except Exception:
            pass

    def set_card_visible(self, path: Path, visible: bool) -> None:
        card = self._cards_by_path.get(str(path))
        if card is not None:
            try:
                card.setVisible(bool(visible))
            except Exception:
                pass

    def apply_selection(self, selected: set[Path] | set[str] | None = None) -> None:
        if selected is None:
            selected = self._selection
        # Normalize to str set.
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
            try:
                apply_gallery_selection(card, want, accent=accent)  # type: ignore[arg-type]
            except Exception:
                pass
            try:
                card._gallery_sel_applied = (want, accent_key)  # type: ignore[attr-defined]
            except Exception:
                pass

    def refresh_selection_accent(self) -> None:
        self._selection_accent = gallery_selection_accent()
        if self._marquee_gesture is not None:
            try:
                self._marquee_gesture.set_accent(self._selection_accent)
            except Exception:
                pass
        self.apply_selection(self._selection)

    # -- pool helpers ------------------------------------------------------

    def _acquire_card(self, item: GalleryItem):
        _mode = self._resolve_mode()
        if self._pool:
            card = self._pool.pop()
            try:
                card.setParent(self.items_host)
            except Exception:
                pass
            try:
                update_gallery_card(card, item, mode=_mode)  # type: ignore[arg-type]
            except Exception:
                pass
            # Rebind click to current toggle handler (pool may carry old closure).
            self._rebind_card(card)
            return card
        return build_gallery_card(
            item,
            parent=self.items_host,
            on_activate=self._handle_toggle,
            on_context_menu=self._handle_context_menu,
            mode=_mode,
        )

    def _recycle_card(self, str_path: str) -> None:
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

    def _rebind_card(self, card) -> None:
        # Disconnect previous regionClicked/rightClicked if possible, then reconnect via helper.
        # Easiest: disconnect all and rebind via build helper's internal.
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
        # Re-install handlers with current callbacks.
        from tabs.image_gallery.ui.card import _bind_gallery_card  # local import to avoid cycle

        _bind_gallery_card(card, on_activate=self._handle_toggle, on_context_menu=self._handle_context_menu)

    def _handle_toggle(self, path: Path, additive: bool = False) -> None:
        if callable(self._on_toggle):
            try:
                self._on_toggle(path, additive)
            except TypeError:
                self._on_toggle(path)

    def _handle_context_menu(self, path: Path | None) -> None:
        if callable(self._on_context_menu) and path is not None:
            try:
                self._on_context_menu(path)
            except Exception:
                pass

    def _update_host_height(self, item_count: int) -> None:
        # Let host grow with content; scroll area will show scrollbar as needed.
        # Host height is derived from row count * stride + margins.
        if item_count <= 0:
            try:
                self.items_host.setMinimumHeight(1)
            except Exception:
                pass
            return
        rows = (item_count + GRID_COLUMNS - 1) // GRID_COLUMNS
        stride = scaled_px(GALLERY_CARD_H) + scaled_px(GRID_SPACING)
        margins = scaled_px(GRID_MARGIN_TOP) + scaled_px(GRID_MARGIN_BOTTOM)
        needed = margins + rows * scaled_px(GALLERY_CARD_H) + max(0, rows - 1) * scaled_px(GRID_SPACING)
        # Also ensure stride accounts for content padding already in card height.
        _ = stride  # keep for future virtualization parity
        try:
            self.items_host.setMinimumHeight(needed)
        except Exception:
            pass

    # -- helpers for marquee / external callers ----------------------------

    @property
    def grid_columns(self) -> int:
        return GRID_COLUMNS

    @property
    def items(self) -> list[GalleryItem]:
        return list(self._items)

    def card_for(self, path: Path | str):  # type: ignore[no-untyped-def]
        return self._cards_by_path.get(str(path))

    def set_fill_color(self, color) -> None:
        try:
            apply_opaque_widget_fill(self.items_host, color)
            apply_opaque_widget_fill(self.scroll_area.viewport(), color)
            apply_opaque_widget_fill(self.scroll_area, color)
        except Exception:
            pass

    # -- eventFilter for marquee empty-area drag ---------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # Delegate to marquee module if available.
        try:
            from tabs.image_gallery.ui import marquee as _marquee

            if _marquee.event_filter(self, watched, event):
                return True
        except Exception:
            pass
        return super().eventFilter(watched, event)
