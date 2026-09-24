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

    def rebuild_grid(self, items: list[GalleryItem], mode: object = None) -> None:
        """Clear and rebuild the 4-column grid from *items* (pool-reusing Buttons).

        ``mode`` controls per-dot artifact palette; proxied to ``build_gallery_card``.
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

    def _rebuild_series(self) -> None:
        """Internal: rebuild with series headers + UNGROUPED tail."""
        # Recycle cards.
        for path in list(self._cards_by_path):
            self._recycle_card(path)
        self._clear_series_headers()
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            w = item.widget()
            if w is not None and w not in list(self._cards_by_path.values()) and w not in self._pool:
                w.setParent(None)
        self._cards_by_path.clear()
        self._series_cards = {}

        if self._series is None:
            return
        current_row = 0
        # Series sections
        for idx, cluster in enumerate(self._series):
            hub = self._hub_names[idx] if idx < len(self._hub_names) else None
            is_collapsed = bool(self._collapsed.get(idx, False))
            # Build header text: SERIES i · {hub_name} · {n} VARIANTS
            if hub:
                header_text = f"SERIES {idx + 1} · {hub} · {len(cluster)} VARIANTS"
            else:
                header_text = f"SERIES {idx + 1} · {len(cluster)} images"
            header = self._make_series_header(header_text, len(cluster), hub_name=hub, collapsed=is_collapsed, index=idx)
            self._series_headers.append(header)
            self.items_layout.addWidget(header, current_row, 0, 1, GRID_COLUMNS)
            current_row += 1
            if is_collapsed:
                # Skip cards for collapsed section
                continue
            cards: list[object] = []
            for pos, item in enumerate(cluster):
                card = self._acquire_card(item)
                self._cards_by_path[str(item.path)] = card
                cards.append(card)
                r, c = divmod(pos, GRID_COLUMNS)
                self.items_layout.addWidget(card, current_row + r, c)
                card.show()
            self._series_cards[idx] = cards
            rows_needed = (len(cluster) + GRID_COLUMNS - 1) // GRID_COLUMNS if cluster else 0
            current_row += rows_needed
        # UNGROUPED tail — format "UNGROUPED · N" (real_design.md:59, no "images")
        if self._ungrouped:
            header = self._make_series_header(f"UNGROUPED · {len(self._ungrouped)}", len(self._ungrouped), hub_name=None, collapsed=False, index=None)
            self._series_headers.append(header)
            self.items_layout.addWidget(header, current_row, 0, 1, GRID_COLUMNS)
            current_row += 1
            for pos, item in enumerate(self._ungrouped):
                card = self._acquire_card(item)
                self._cards_by_path[str(item.path)] = card
                r, c = divmod(pos, GRID_COLUMNS)
                self.items_layout.addWidget(card, current_row + r, c)
                card.show()
            rows_needed = (len(self._ungrouped) + GRID_COLUMNS - 1) // GRID_COLUMNS
            current_row += rows_needed

        self.apply_selection(self._selection)
        self._update_host_height_for_series(current_row)

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
        for str_path, card in self._cards_by_path.items():
            try:
                apply_gallery_selection(card, str_path in norm, accent=accent)  # type: ignore[arg-type]
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
