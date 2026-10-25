"""Virtualized grid for the Image Gallery tab — Stage 1 MVP.
Audit-Meta: pattern=thin-owner size=exempt reason="thin owner + ui/grid_view/* submodules (plan-gallery-split-2026-10-17 Part C1)"

Uses ``OverlayScrollArea`` + ``OpaqueFillHost`` + ``QGridLayout`` with a
reused ``Button`` pool (responsive columns, rebuild_grid / refresh_card /
set_card_visible / apply_selection). Wide viewports grow past GRID_COLUMNS
so cards fill the right half; with 2+ sections and enough width the first
section lays out left and the rest right with a draggable center splitter.
Keeps the same contracts as
``session_picker/recent/items_view.py``: list mode reuses this ONE view and
only swaps the card builders (``ui/list/``) + placement columns.
``scaled_px`` is used for every geometry constant; no ad-hoc stylesheets —
painter pipeline owns visuals.
"""

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

# View modes (recent items_view parity): one view, builders + columns swap.
VIEW_GRID = "grid"
VIEW_LIST = "list"

# real_design.md:2.3 — gap 24, root pad already 24, inner margins 0
GRID_COLUMNS = 4
GRID_SPACING = 24
GRID_MARGIN = 0
GRID_MARGIN_TOP = 0
GRID_MARGIN_BOTTOM = 0
# Responsive grid: wide viewports grow past GRID_COLUMNS so the right half
# fills instead of staying empty (fixed 4 left the whole right side blank
# on ~1900px windows). Never shrinks below GRID_COLUMNS (narrow parity +
# offscreen tests stay at 4).
GRID_COLUMNS_MAX = 12
# Side-by-side series bands need at least this many total columns: the first
# section goes left, the rest stack right, with a draggable separator column
# between them (the "center splitter"). Below this — single stacked band.
GRID_BAND_MIN_TOTAL = 6
GRID_SEPARATOR_COL_W = 8
# Series-header collapse arrow: painted as a button layer at the right
# edge (never trailing text) — long hub names elide without eating it.
# The title row reserves this width via right content_padding.
SERIES_ARROW_RESERVE = 22

# Optional virtual buffer for later full virtualization; not used in MVP rebuild
# but kept for marquee hit-testing parity.
VIRTUAL_ROW_BUFFER = 1


# -- package split: bodies moved to sibling submodules (plan-gallery-split-2026-10-17, Part C1) --
# GalleryGridView keeps thin per-method delegators; every moved name is re-exported here.
from .layers import (
    _BandSeparatorHandle,
    _SeriesCollapseArrowLayer,
    _SeriesDropTargetLayer,
    _SeriesHeaderAccentLayer,
    _disconnect_btn_theme,
    _gallery_header_text_color,
    _grid_substrate_color,
    _is_dark,
    _resolve_section_bar_color,
    _strip_header_arrow,
)
from .filters import _CardKeyFilter, _CardPressDragFilter
from .nav_section import GalleryGridNavSection
from .context import _cluster_series_id, _header_button, _section_members
from .drag_source import (
    GALLERY_DRAG_PREVIEW_EDGE,
    _card_drag_path,
    _drag_owner,
    _ensure_card_drag,
    _ensure_card_keys,
    build_card_drag,
    build_gallery_drag_mime,
    clear_card_press,
    compose_gallery_drag_pixmap,
    dragged_paths_for_press,
    maybe_start_card_drag,
    note_card_press,
    resolve_gallery_drag_pixmap,
    should_start_gallery_drag,
)
from .columns import (
    _adapt_columns_and_reflow,
    _available_grid_width,
    _card_height_px,
    _compute_columns,
    _grid_stride_px,
    _reflow_flat,
    _sync_series_column_widths,
    set_view_mode,
)
from .bands import (
    _bands_active,
    _ensure_band_separator,
    _hide_band_separator,
    _nudge_split_by_px,
    _plan_band_entries,
    _plan_bands,
    nav_columns_for,
    set_split_left,
)
from .nav import (
    _activate_card,
    _block_entry,
    _block_exit,
    _focus_reason,
    _focus_snapshot,
    _live_cards_in_order,
    _live_headers_in_order,
    _menu_card,
    _nav_bands,
    _restore_focus,
    ensure_card_visible,
    focus_card,
    focus_first_card,
    focus_last_card,
    focused_card,
    focused_header,
    forward_key_to_owner,
    handle_navigation_key,
    move_focus,
    select_all_cards,
)
from .rebuild import (
    _promote_flat_ungrouped,
    _rebuild_next_chunk,
    _resolve_mode,
    _resolve_profile,
    append_new_cards,
    rebuild_grid,
)
from .series import (
    _clear_series_headers,
    _make_series_header,
    _rebuild_series,
    _refresh_ungrouped_header_count,
    _retitle_header,
    _row_of,
    _tail_header_span,
    _toggle_collapse,
    _update_host_height_for_series,
    _would_band_with,
    retranslate_headers,
    set_series,
    set_series_attention,
)
from .pool import (
    _acquire_card,
    _activity_translate,
    _handle_toggle,
    _rebind_card,
    _recycle_card,
    _sync_activity,
    _ungrouped_header_text,
)
from .marquee import (
    _update_host_height,
    apply_selection,
    card_for,
    grid_columns,
    items,
    refresh_card,
    refresh_cards,
    refresh_selection_accent,
    set_card_visible,
    set_fill_color,
)
from . import bands, columns, context, drag_source, filters, layers, marquee, nav, pool, rebuild
from . import series as series_mod

class GalleryGridView(QWidget):
    """Scrollable 4-column gallery grid with pooled Button cards."""

    # Phase 2a — visible-range signals (wave B prioritizes these paths).
    # Emitted (debounced) with a ``list[Path]`` payload in display order.
    visible_range_changed = Signal(object)
    VISIBLE_RANGE_DEBOUNCE_MS = 120
    # Overscan above/below the viewport, in screenfuls.
    VISIBLE_RANGE_OVERSCAN_SCREENS = 1

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
        self._on_empty_context_menu = None
        self._on_series_context_menu = None
        self._series_header_labels: dict[int, str] = {}

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

        # Phase 2a — debounced visible-range recompute. Rapid scrolls
        # restart the single-shot timer, so per-pixel valueChanged storms
        # coalesce into one emit (see _emit_visible_range).
        self._visible_debounce = QTimer(self)
        self._visible_debounce.setSingleShot(True)
        self._visible_debounce.setInterval(self.VISIBLE_RANGE_DEBOUNCE_MS)
        self._visible_debounce.timeout.connect(self._emit_visible_range)
        self._last_visible_paths: list[str] | None = None
        self.scroll_area.verticalScrollBar().valueChanged.connect(self._schedule_visible_range_emit)
        self.scroll_area.horizontalScrollBar().valueChanged.connect(self._schedule_visible_range_emit)

        # Marquee gesture lives on the host; created lazily via marquee module.
        self._marquee_gesture = None
        self._marquee_additive = False
        self._marquee_base: set[str] = set()

        # Wave A drag source: card-press origin (global pos + path). Card
        # press-drag starts a QDrag; empty-host press-drag stays marquee
        # (marquee refuses non-empty hosts) — never both from one gesture.
        self._drag_press_path: str | None = None
        self._drag_press_pos: QPoint | None = None

        # Stage 2 series grouping — headers only for clusters ≥2, singles under UNGROUPED tail.
        self._series: list[list[GalleryItem]] | None = None
        # Cross-series routing hint (task-gallery-ai-routing-jev-2026-10-09):
        # series ids that need a human first — rendered as a marker on the
        # series header. Additive; empty = no marker.
        self._series_attention: set[str] = set()
        self._ungrouped: list[GalleryItem] = []
        self._series_headers: list[QWidget] = []
        self._hub_names: list[str | None] = []
        self._collapsed: dict[int, bool] = {}
        # UNGROUPED tail collapse (index-less section) — same affordance as a
        # series header, so the provisional pool is a normal group from the
        # first frame instead of a dead, glyph-less header.
        self._tail_collapsed: bool = False
        self._series_cards: dict[int, list[object]] = {}
        # View mode: grid (4-col cards) or list (1-col rows). Pool is
        # flushed on switch so builders never mix (see set_view_mode).
        self._view_mode: str = VIEW_GRID
        # Responsive columns: how many card columns the last layout used.
        # Grows past GRID_COLUMNS on wide viewports (right half fills);
        # offscreen/hidden views stay at GRID_COLUMNS (test parity).
        self._applied_columns: int = GRID_COLUMNS
        # Center-splitter override: left-band column count set by dragging
        # the band separator (None = auto half). Reset on width change.
        self._split_left: int | None = None
        # Last side-by-side band geometry: (left_cols, right_cols, sep_col)
        # or None when sections stack in one full-width band.
        self._band_state: tuple[int, int, int] | None = None
        self._band_separator: QWidget | None = None
        # Debounced column adaptation on resizes (dragging a window edge
        # must not replan per pixel — one reflow after it settles).
        self._activity = ActivityPulse(self, translate=self._activity_translate)
        self._adapt_timer = QTimer(self)
        self._adapt_timer.setSingleShot(True)
        try:
            self._adapt_timer.setInterval(150)
        except Exception:
            pass
        try:
            self._adapt_timer.timeout.connect(self._adapt_columns_and_reflow)
        except Exception:
            pass
        # A2: mode for per-dot card colors (fidelity/camera/batch_synthetic) — proxied from widget set_triage.
        self._mode: object = None
        try:
            from sli_ui_toolkit.managers import ThemeManager

            ThemeManager.get_instance().theme_changed.connect(self._on_gallery_theme_changed)
        except Exception:
            pass
        # Teardown hygiene: header buttons (and this view) hold
        # ``theme_changed`` slots on a process-wide singleton that does NOT
        # auto-disconnect dead Python callables — drop them when the C++
        # object dies so later theme flips never re-enter the event loop
        # through destroyed widgets (see _disconnect_btn_theme).
        try:
            self.destroyed.connect(self._disconnect_theme_slots)
        except Exception:
            pass
        try:
            self.set_fill_color(_grid_substrate_color())
        except Exception:
            pass
        # NavigationManager section (registered by the tab on activate): the
        # grid owns arrow keys on live cards + cross-section trial-dispatch.
        self._nav_section = GalleryGridNavSection(self)

    @property
    def nav_section(self) -> "GalleryGridNavSection":
        """The ``NavigationSection`` describing the card grid's arrows."""
        return self._nav_section

    def _disconnect_theme_slots(self, _obj=None) -> None:
        """Drop all ``theme_changed`` slots owned by this view (teardown).

        Runs on ``destroyed``: only signal-side surgery (no C++ touches),
        so it is safe while children are already half-gone.
        """
        try:
            from sli_ui_toolkit.managers import ThemeManager

            sig = ThemeManager.get_instance().theme_changed
        except Exception:
            return
        try:
            sig.disconnect(self._on_gallery_theme_changed)
        except Exception:
            pass
        try:
            headers = list(getattr(self, "_series_headers", []) or [])
        except Exception:
            headers = []
        for hdr in headers:
            try:
                btn = hdr.findChild(Button)
            except Exception:
                btn = None
            if btn is None:
                continue
            try:
                sig.disconnect(btn.update)
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

    def configure(
        self,
        *,
        on_toggle=None,
        on_context_menu=None,
        on_empty_context_menu=None,
        on_series_context_menu=None,
    ) -> None:
        self._on_toggle = on_toggle
        self._on_context_menu = on_context_menu
        self._on_empty_context_menu = on_empty_context_menu
        if on_series_context_menu is not None:
            self._on_series_context_menu = on_series_context_menu

    # -- view mode (recent items_view parity) --------------------------------

    def set_view_mode(self, mode: object) -> None:
        return columns.set_view_mode(self, mode)

    def _card_height_px(self) -> int:
        return columns._card_height_px(self)

    def _sync_series_column_widths(self, *, series_mode: bool) -> None:
        return columns._sync_series_column_widths(self, series_mode=series_mode)

    def _grid_stride_px(self) -> int:
        return columns._grid_stride_px(self)

    def _available_grid_width(self) -> int:
        return columns._available_grid_width(self)

    def _compute_columns(self) -> int:
        return columns._compute_columns(self)

    def resizeEvent(self, event) -> None:  # noqa: N802
        try:
            super().resizeEvent(event)
        except Exception:
            pass
        columns.resize_event(self, event)

    def _adapt_columns_and_reflow(self) -> None:
        return columns._adapt_columns_and_reflow(self)

    def _reflow_flat(self) -> None:
        return columns._reflow_flat(self)

    # -- side-by-side series bands + center splitter ---------------------

    def _bands_active(self) -> bool:
        return bands._bands_active(self)

    def _plan_bands(self, sections: list[dict]) -> list[tuple[list[dict], int, int]]:
        return bands._plan_bands(self, sections)

    def _plan_band_entries(
        self,
        subset: list[dict],
        band_cols: int,
        col_off: int,
        base_row: int,
        headers: list,
        hdr_start: int,
    ) -> tuple[list[tuple], int, int]:
        return bands._plan_band_entries(self, subset, band_cols, col_off, base_row, headers, hdr_start)

    def _ensure_band_separator(self):
        return bands._ensure_band_separator(self)

    def _hide_band_separator(self) -> None:
        return bands._hide_band_separator(self)

    def _nudge_split_by_px(self, dx: int) -> bool:
        return bands._nudge_split_by_px(self, dx)

    def set_split_left(self, left_cols: int) -> None:
        return bands.set_split_left(self, left_cols)

    def nav_columns_for(self, path=None) -> int:
        return bands.nav_columns_for(self, path)

    # -- keyboard focus navigation (grid + list) ---------------------------
    #
    # Mirrors the working sibling ``tabs.session_picker.recent.items_view``:
    # index-driven focus movement over the live cards with an explicit
    # "scroll target into view" pass. Cards keep *real* Qt focus (the toolkit
    # Button ring / NavigationManager model) — no second focus model, no
    # custom "current index" ring.

    def _focus_reason(self):
        return nav._focus_reason(self)

    def _live_cards_in_order(self) -> list:
        return nav._live_cards_in_order(self)

    def _live_headers_in_order(self) -> list:
        return nav._live_headers_in_order(self)

    def focused_card(self):
        return nav.focused_card(self)

    def focused_header(self):
        return nav.focused_header(self)

    def ensure_card_visible(self, card) -> None:
        return nav.ensure_card_visible(self, card)

    def focus_card(self, card, reason=None) -> bool:
        return nav.focus_card(self, card, reason)

    def focus_first_card(self, reason=None) -> bool:
        return nav.focus_first_card(self, reason)

    def focus_last_card(self, reason=None) -> bool:
        return nav.focus_last_card(self, reason)

    def _nav_bands(self) -> list[list[dict]]:
        return nav._nav_bands(self)

    @staticmethod
    def _block_entry(blk):
        return nav._block_entry(blk)

    @staticmethod
    def _block_exit(blk):
        return nav._block_exit(blk)

    def move_focus(self, key) -> bool:
        return nav.move_focus(self, key)

    def _activate_card(self, card) -> bool:
        return nav._activate_card(self, card)

    def _menu_card(self, card) -> bool:
        return nav._menu_card(self, card)

    def select_all_cards(self) -> bool:
        return nav.select_all_cards(self)

    def forward_key_to_owner(self, event) -> bool:
        return nav.forward_key_to_owner(self, event)

    def handle_navigation_key(self, event) -> bool:
        return nav.handle_navigation_key(self, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Grid view itself focused (widget-level arrows bootstrap onto the
        # first card); ignore otherwise so unhandled keys keep propagating.
        if nav.key_press_event(self, event):
            return
        super().keyPressEvent(event)

    def _focus_snapshot(self):
        return nav._focus_snapshot(self)

    def _restore_focus(self, snapshot) -> bool:
        return nav._restore_focus(self, snapshot)

    # -- public API expected by controller/widget --------------------------

    # Systemic fix 2026-08-26: O(N) sync rebuild blocked UI for 1k+ items
    # (measured 7s for 1037). Chunk via event-loop so UI stays responsive.
    _REBUILD_CHUNK = 80
    _rebuild_pending: list[GalleryItem] | None = None
    _rebuild_index: int = 0

    def _resolve_mode(self, explicit: object = None) -> object:
        return rebuild._resolve_mode(self, explicit)

    def _resolve_profile(self, explicit: object = None) -> object:
        return rebuild._resolve_profile(self, explicit)

    def rebuild_grid(self, items: list[GalleryItem], mode: object = None, *, paint_selection: bool = True, flat_ungrouped: bool = False) -> None:
        return rebuild.rebuild_grid(self, items, mode, paint_selection=paint_selection, flat_ungrouped=flat_ungrouped)

    def _promote_flat_ungrouped(self) -> None:
        return rebuild._promote_flat_ungrouped(self)

    def _rebuild_next_chunk(self) -> None:
        return rebuild._rebuild_next_chunk(self)

    # -- Phase 2a visible range ----------------------------------------
    # Wave B (thumbnail prioritization) calls visible_paths() and listens
    # to visible_range_changed. Geometry comes from layout/card geometry
    # only — never from pixmap data or arrival order. Pure additive API:
    # no existing rebuild/refresh/selection/scroll path changes behavior.

    def visible_paths(self) -> list[Path]:
        """Paths of cards intersecting the viewport (+ vertical overscan).

        Returns the ``item.path`` objects (the same identity
        ``controller._find_item`` compares with ``==``), in top-to-bottom
        display order (card ``y``, then ``x``). A partially visible card
        at the viewport edge counts as visible. Empty grid -> ``[]``.
        """
        try:
            items = list(getattr(self, "_items", None) or [])
        except Exception:
            return []
        if not items:
            return []
        try:
            viewport = self.scroll_area.viewport()
            vh = viewport.height()
            vw = viewport.width()
        except Exception:
            return [it.path for it in items]
        if vh <= 0 or vw <= 0:
            # Not laid out yet (never shown): fail open with everything
            # in display order so callers never starve thumbnails.
            return [it.path for it in items]
        try:
            vbar = self.scroll_area.verticalScrollBar()
            hbar = self.scroll_area.horizontalScrollBar()
            vval = int(vbar.value())
            hval = int(hbar.value())
        except Exception:
            vval, hval = 0, 0
        try:
            overscan = int(vh * self.VISIBLE_RANGE_OVERSCAN_SCREENS)
        except Exception:
            overscan = int(vh)
        y0 = vval - overscan
        y1 = vval + vh + overscan
        x0 = hval
        x1 = hval + vw
        scored: list[tuple[int, int, object]] = []
        for item in items:
            try:
                card = self._cards_by_path.get(str(item.path))
            except Exception:
                card = None
            if card is None:
                continue
            try:
                g = card.geometry()
            except Exception:
                continue
            # Card geometry is in items_host coordinates; the visible
            # host rect starts at the scrollbar values. Inclusive edges:
            # a partially visible card at the boundary counts.
            if g.right() >= x0 and g.left() <= x1 and g.bottom() >= y0 and g.top() <= y1:
                scored.append((int(g.y()), int(g.x()), item.path))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [p for _, _, p in scored]

    def _schedule_visible_range_emit(self, *_args) -> None:
        """Restart the single-shot debounce timer (scroll storms coalesce)."""
        try:
            self._visible_debounce.start()
        except Exception:
            pass

    def _emit_visible_range(self) -> None:
        """Recompute and emit visible_range_changed if the set changed."""
        try:
            paths = self.visible_paths()
        except Exception:
            return
        try:
            key = [str(p) for p in paths]
        except Exception:
            return
        if key == self._last_visible_paths:
            return
        self._last_visible_paths = key
        try:
            self.visible_range_changed.emit(list(paths))
        except Exception:
            pass

    # -- Stage 2 series grouping ----------------------------------------

    def set_series(
        self,
        series: list[list[GalleryItem]] | None,
        hub_names: list[str | None] | None = None,
        collapsed: dict[int, bool] | set[int] | list[bool] | None = None,
        mode: object = None,
    ) -> None:
        return series_mod.set_series(self, series, hub_names, collapsed, mode)

    def _retitle_header(self, header, text: str, index, collapsed: bool = False) -> None:
        return series_mod._retitle_header(self, header, text, index, collapsed)

    def set_series_attention(self, series_ids) -> None:
        return series_mod.set_series_attention(self, series_ids)

    def _rebuild_series(self) -> None:
        return series_mod._rebuild_series(self)

    def append_new_cards(self, items: list[GalleryItem]) -> None:
        return rebuild.append_new_cards(self, items)

    def _tail_header_span(self) -> int:
        return series_mod._tail_header_span(self)

    def _would_band_with(self, sections_count: int) -> bool:
        return series_mod._would_band_with(self, sections_count)

    def _refresh_ungrouped_header_count(self, total: int) -> None:
        return series_mod._refresh_ungrouped_header_count(self, total)

    def _row_of(self, widget) -> int | None:
        return series_mod._row_of(self, widget)

    def _make_series_header(
        self,
        text: str,
        count: int = 0,
        hub_name: str | None = None,
        collapsed: bool = False,
        index: int | None = None,
    ) -> QWidget:
        return series_mod._make_series_header(self, text, count, hub_name, collapsed, index)

    def _toggle_collapse(self, index: int | None) -> None:
        return series_mod._toggle_collapse(self, index)

    def _clear_series_headers(self) -> None:
        return series_mod._clear_series_headers(self)

    def _update_host_height_for_series(self, total_rows: int) -> None:
        return series_mod._update_host_height_for_series(self, total_rows)

    def refresh_card(self, item: GalleryItem) -> None:
        return marquee.refresh_card(self, item)

    def refresh_cards(self, items) -> None:
        return marquee.refresh_cards(self, items)

    def retranslate_headers(self) -> None:
        return series_mod.retranslate_headers(self)

    def set_card_visible(self, path: Path, visible: bool) -> None:
        return marquee.set_card_visible(self, path, visible)

    def apply_selection(self, selected: set[Path] | set[str] | None = None) -> None:
        return marquee.apply_selection(self, selected)

    def refresh_selection_accent(self) -> None:
        return marquee.refresh_selection_accent(self)

    # -- pool helpers ------------------------------------------------------

    def _acquire_card(self, item: GalleryItem):
        return pool._acquire_card(self, item)

    def _sync_activity(self, card) -> None:
        return pool._sync_activity(self, card)

    def _activity_translate(self, key: str, default: str) -> str:
        return pool._activity_translate(self, key, default)

    def _ungrouped_header_text(self, count: int) -> str:
        return pool._ungrouped_header_text(self, count)

    def _recycle_card(self, str_path: str) -> None:
        return pool._recycle_card(self, str_path)

    def _rebind_card(self, card) -> None:
        # Disconnect previous regionClicked/rightClicked if possible, then reconnect via helper.
        # Easiest: disconnect all and rebind via build helper's internal.
        return pool._rebind_card(self, card)

    def _handle_toggle(self, path: Path, additive: bool = False) -> None:
        return pool._handle_toggle(self, path, additive)

    # -- Wave A drag source: card press origin + QDrag kickoff ---------------

    def _ensure_card_drag(self, card) -> None:
        return drag_source._ensure_card_drag(self, card)

    def _ensure_card_keys(self, card) -> None:
        return drag_source._ensure_card_keys(self, card)

    def note_card_press(self, path: Path, global_pos: QPoint) -> None:
        return drag_source.note_card_press(self, path, global_pos)

    def clear_card_press(self) -> None:
        return drag_source.clear_card_press(self)

    def _drag_owner(self):
        return drag_source._drag_owner(self)

    def build_card_drag(self, card, global_pos: QPoint):  # type: ignore[no-untyped-def]
        return drag_source.build_card_drag(self, card, global_pos)

    def maybe_start_card_drag(self, card, global_pos: QPoint) -> bool:
        return drag_source.maybe_start_card_drag(self, card, global_pos)

    def _handle_context_menu(self, path: Path | None) -> None:
        return context._handle_context_menu(self, path)

    def _handle_series_context(self, anchor, index, local_pos=None) -> None:
        return context._handle_series_context(self, anchor, index, local_pos)

    def _update_host_height(self, item_count: int) -> None:
        # Let host grow with content; scroll area will show scrollbar as needed.
        # Host height is derived from row count * stride + margins.
        return marquee._update_host_height(self, item_count)

    # -- helpers for marquee / external callers ----------------------------

    @property
    def grid_columns(self) -> int:
        return marquee.grid_columns(self)

    @property
    def items(self) -> list[GalleryItem]:
        return marquee.items(self)

    def card_for(self, path: Path | str):  # type: ignore[no-untyped-def]
        return marquee.card_for(self, path)

    def set_fill_color(self, color) -> None:
        return marquee.set_fill_color(self, color)

    # -- eventFilter for marquee empty-area drag ---------------------------

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        # Delegate to marquee module if available.
        if marquee.event_filter(self, watched, event):
            return True
        return super().eventFilter(watched, event)
