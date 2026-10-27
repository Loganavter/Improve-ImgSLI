"""View mode + responsive column math (grid_view package, plan C1)."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

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

from tabs.image_gallery.ui.grid_view import GRID_COLUMNS, GRID_COLUMNS_MAX, GRID_SPACING, VIEW_GRID, VIEW_LIST, logger

def set_view_mode(view, mode: object) -> None:
    """Switch grid/list builders + placement (one view, recent parity).

    Accepts ``"grid"``/``"list"`` (``VIEW_GRID``/``VIEW_LIST``) or bool
    (``True`` = list, matching the toolbar toggle). Destroys the card
    pool and live cards (builders must never mix), then rebuilds from
    the current items and re-applies the live series state.
    """
    self = view
    try:
        if isinstance(mode, bool):
            want = VIEW_LIST if mode else VIEW_GRID
        else:
            want = VIEW_LIST if str(mode).lower() == VIEW_LIST else VIEW_GRID
    except Exception:
        want = VIEW_GRID
    if want == self._view_mode and self._cards_by_path:
        return
    # Capture keyboard focus BEFORE the pool teardown (cards are destroyed
    # and rebuilt in the new builder) so it returns to the same path.
    _focus_snapshot = self._focus_snapshot()
    try:
        series = list(self._series) if self._series is not None else None
        hubs = list(self._hub_names)
        collapsed = dict(self._collapsed)
    except Exception:
        series, hubs, collapsed = None, [], {}
    # Destroy pool (mixed builders must never share it).
    try:
        for card in list(self._pool):
            try:
                # Hide before unparenting: a still-visible widget handed a
                # new top-level parent can flash for a frame.
                card.hide()
                card.setParent(None)
                card.deleteLater()
            except Exception:
                pass
        self._pool = []
    except Exception:
        pass
    self._view_mode = want
    if want == VIEW_GRID:
        # Fresh mode: re-derive responsive columns for this viewport
        # (a list→grid switch must not inherit a stale narrow count).
        try:
            self._applied_columns = int(self._compute_columns())
        except Exception:
            pass
    try:
        items = list(self._items)
    except Exception:
        items = []
    try:
        self.rebuild_grid(items)
    except Exception:
        return
    if series is not None:
        try:
            self.set_series(series, hub_names=hubs, collapsed=collapsed)
        except Exception:
            pass
    # Belt-and-braces commit: the flat rebuild and the series relayout
    # each activate their own branch, but the mode swap must never leave
    # a stale frame even if one of those branches fail-opened above.
    try:
        self.items_layout.activate()
    except Exception:
        logger.debug("set_view_mode: layout activate failed", exc_info=True)
    self._restore_focus(_focus_snapshot)

def _card_height_px(view) -> int:
    self = view
    return scaled_px(LIST_CARD_H) if self._view_mode == VIEW_LIST else scaled_px(GALLERY_CARD_H)

def _sync_series_column_widths(view, *, series_mode: bool) -> None:
    """Keep series headers full-width when clusters collapse.

    A header spans ``grid_columns``. With every cluster collapsed the
    layout holds no cards, so ``QGridLayout`` shrinks its columns to
    zero and the header ``Button`` elides its text (``ElideRight``) —
    e.g. ``SERIES 1 · hub · 3 VARIANTS ▼`` degrades to ``SERIES 1 ·``.
    Pinning each column to the card width in series mode keeps the
    header at the full grid width; flat mode resets to 0 so a
    partially-filled last row does not force extra width.

    The layout is NOT recreated across a grid↔list switch, so every
    column a previous mode may have pinned has to be reset — leftover
    min-widths on the now-empty grid columns (1..3 in list mode) squeeze
    column 0 to its sizeHint and the series header elides/disappears.
    """
    self = view
    try:
        cols = int(self.grid_columns)
    except Exception:
        return
    # Reset EVERY column the layout currently carries, not just the ones
    # the current mode uses: the responsive/banded grid can pin more than
    # GRID_COLUMNS (wide viewports grow, bands add a separator column), and
    # a grid→list switch keeps the same QGridLayout. Leftover card-width
    # minimums on those higher columns (e.g. 4,5 after a 6-col banded grid)
    # steal width from the stretched list column and leave a dead strip on
    # the right.
    try:
        _layout_cols = int(self.items_layout.columnCount())
    except Exception:
        _layout_cols = 0
    max_cols = max(int(GRID_COLUMNS), int(cols or 1), int(_layout_cols))
    is_list = self._view_mode == VIEW_LIST
    try:
        # List: fill horizontally (one stretched column). Grid: natural
        # left-aligned card layout.
        self.items_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop
            if is_list
            else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        )
    except Exception:
        pass
    for c in range(max_cols):
        try:
            self.items_layout.setColumnStretch(c, 1 if (is_list and c == 0) else 0)
        except Exception:
            continue
        try:
            self.items_layout.setColumnMinimumWidth(c, 0)
        except Exception:
            continue
    if is_list or not series_mode or cols <= 1:
        return
    try:
        card_w = int(scaled_px(GALLERY_CARD_W))
    except Exception:
        return
    for c in range(cols):
        try:
            self.items_layout.setColumnMinimumWidth(c, card_w)
        except Exception:
            continue

def _grid_stride_px(view) -> int:
    """Card width + gap: horizontal pitch of one grid column."""
    self = view
    try:
        return int(scaled_px(GALLERY_CARD_W)) + int(scaled_px(GRID_SPACING))
    except Exception:
        return 274

def _available_grid_width(view) -> int:
    """Viewport width available for cards (0 when unknown/hidden)."""
    self = view
    try:
        for src in (self.scroll_area.viewport(), self.items_host, self):
            try:
                w = int(src.width())
            except Exception:
                continue
            if w > 0:
                return w
    except Exception:
        pass
    return 0

def _compute_columns(view) -> int:
    """Column count for the current viewport width.

    Wide viewports grow past GRID_COLUMNS so cards fill the right half
    instead of hugging the left edge. Never shrinks below GRID_COLUMNS
    (narrow-window parity; hidden/offscreen views keep 4).
    """
    self = view
    if self._view_mode == VIEW_LIST:
        return 1
    try:
        if not self.isVisible():
            return GRID_COLUMNS
    except Exception:
        return GRID_COLUMNS
    avail = self._available_grid_width()
    if avail <= 0:
        return GRID_COLUMNS
    try:
        spacing = int(scaled_px(GRID_SPACING))
    except Exception:
        spacing = 24
    stride = self._grid_stride_px()
    if stride <= 0:
        return GRID_COLUMNS
    try:
        fit = int((avail + spacing) // stride)
    except Exception:
        return GRID_COLUMNS
    if fit < GRID_COLUMNS:
        return GRID_COLUMNS
    return max(GRID_COLUMNS, min(GRID_COLUMNS_MAX, fit))

def _adapt_columns_and_reflow(view) -> None:
    """Recompute columns after a resize settles; reflow when changed.

    The reflow is GEOMETRY-ONLY: a window-edge drag (also while a folder is
    analysing) must move the cards, never re-create them or re-stamp their
    content — see ``_rebuild_series_geometry`` and ``_reflow_flat(only_built)``.
    """
    self = view
    try:
        if self._view_mode == VIEW_LIST:
            return
        new = int(self._compute_columns())
    except Exception:
        return
    try:
        if new == int(self._applied_columns):
            return
        self._applied_columns = int(new)
        self._split_left = None
    except Exception:
        return
    try:
        if self._series is not None:
            # Surgical reconcile WITHOUT the per-card content refresh: the
            # plan (headers/bands/cells) is recomputed, every live widget is
            # re-used. Refreshing content here cost one ``update_gallery_card``
            # per card on every resize tick of a running analysis.
            geometry_only = getattr(self, "_rebuild_series_geometry", None)
            if callable(geometry_only):
                geometry_only()
            else:
                self._rebuild_series()
        elif getattr(self, "_rebuild_pending", None) is not None:
            # A chunked build is still landing (large folder). Place the cards
            # that already exist and leave ``_rebuild_pending``/``_rebuild_index``
            # ALONE so the chunk timer finishes the pool at the new count —
            # cancelling the build here used to truncate the grid, and a plain
            # ``_reflow_flat`` pulled the whole pool in synchronously (an O(N)
            # card build on the GUI thread, mid-analysis).
            _reflow_flat(self, only_built=True)
        else:
            _reflow_flat(self)
    except Exception:
        logger.debug("_adapt_columns_and_reflow failed", exc_info=True)

def _reflow_flat(view, *, only_built: bool = False) -> None:
    """Re-place flat-grid cards for a new column count (no pool churn).

    Unlike ``rebuild_grid`` this never recycles cards: live widgets are
    only re-added at new positions, so a window-edge drag reflows
    without content refreshes. ``only_built=True`` additionally skips
    *acquiring* cards that a chunked rebuild has not created yet, so a
    resize during that build stays O(built) instead of pulling the whole
    pool in.
    """
    self = view
    try:
        items = list(self._items or [])
    except Exception:
        items = []
    if not items:
        try:
            self._hide_band_separator()
        except Exception:
            pass
        self._sync_series_column_widths(series_mode=False)
        self._update_host_height(0)
        return
    while self.items_layout.count():
        try:
            self.items_layout.takeAt(0)
        except Exception:
            break
    try:
        self._hide_band_separator()
    except Exception:
        pass
    for idx, item in enumerate(items):
        try:
            key = str(item.path)
        except Exception:
            continue
        card = self._cards_by_path.get(key)
        if card is None:
            if only_built:
                continue
            try:
                card = self._acquire_card(item)
            except Exception:
                continue
            self._cards_by_path[key] = card
        try:
            r, c = divmod(idx, self.grid_columns)
        except Exception:
            r, c = idx, 0
        try:
            self.items_layout.addWidget(card, r, c)
            card.show()
        except Exception:
            logger.debug("_reflow_flat: card placement failed", exc_info=True)
    try:
        self.apply_selection(self._selection)
    except Exception:
        pass
    self._sync_series_column_widths(series_mode=False)
    self._update_host_height(len(items))
    try:
        self.items_layout.activate()
    except Exception:
        logger.debug("_reflow_flat: layout activate failed", exc_info=True)
    try:
        self._schedule_visible_range_emit()
    except Exception:
        pass

def resize_event(view, event) -> None:  # noqa: N802
    # resizeEvent tail: start the debounced column-adapt timer.
    self = view
    try:
        self._adapt_timer.start()
    except Exception:
        pass

# -- the grid follows its container, even when a stacked layout skips it -----
#
# OWNER BUG (2026-10-27, live): "while the analysis runs the window can be
# resized but the cards stay glued to their old places; once it finishes the
# resize moves them freely again".
#
# The grid does not own its resize source: it is a page of the gallery
# ``QStackedWidget``. ``widget_parts.status.set_scanning`` (the S1
# scanning/triage window, i.e. exactly the frames where the card badges spin)
# switches the CURRENT page to the empty/scanning surface and only calls
# ``show()`` on the grid ("keep in stack but not current"). QStackedLayout
# lays out the CURRENT page only — in StackOne mode ``setGeometry`` skips
# every other child — and the empty surface is a transparent blank canvas, so
# the cards stay on screen at the size they had when the page was switched
# away. The grid then never gets a ``resizeEvent``: no ``_adapt_timer``, no
# ``_compute_columns``, no reflow — the whole resize path is dead until
# ``set_triage`` makes the grid current again and its geometry snaps. That
# snap is the "after the analysis it works again".
#
# Hence the grid watches the container itself: a shown-but-not-current page
# adopts the rect the stack WOULD give it, and the ordinary resize path below
# takes over. Same rect as the stack's own activation => no jump on restore.


def _container_of(view):
    """The widget whose layout is supposed to give this view its geometry."""
    self = view
    try:
        return self.parentWidget()
    except Exception:
        return None


def watch_container(view) -> None:
    """(Re)install the container filter on the CURRENT parent widget.

    The thin owner calls this from ``__init__``, ``showEvent`` and on
    ``QEvent.ParentChange`` — the widget is reparented into the content stack
    after construction, so the filter target moves.
    """
    self = view
    prev = getattr(self, "_watched_container", None)
    cur = _container_of(self)
    if prev is cur:
        return
    if prev is not None:
        try:
            prev.removeEventFilter(self)
        except Exception:
            pass
    try:
        self._watched_container = cur
    except Exception:
        return
    if cur is not None:
        try:
            cur.installEventFilter(self)
        except Exception:
            pass


def sync_container_geometry(view) -> bool:
    """Adopt the container's content rect when its layout skipped this page.

    Only a shown page of a ``QStackedWidget`` that is NOT the current one can
    be in that state (see the block comment above); everywhere else the
    container's layout owns the geometry and this is a no-op. Returns True
    when the geometry was adopted.
    """
    self = view
    parent = _container_of(self)
    if parent is None:
        return False
    try:
        if not self.isVisible():
            return False
        if not isinstance(parent, QStackedWidget):
            return False
        if parent.currentWidget() is self:
            return False
        rect = parent.contentsRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        if self.geometry() == rect:
            return False
        self.setGeometry(rect)
        return True
    except Exception:
        return False


def container_event_filter(view, watched, event) -> bool:
    """Follow a container resize/show while this page is not the current one.

    Always returns False: the container's own handling is untouched.
    """
    self = view
    try:
        if watched is not getattr(self, "_watched_container", None):
            return False
        if event.type() not in (QEvent.Type.Resize, QEvent.Type.Show):
            return False
        sync_container_geometry(self)
    except Exception:
        pass
    return False


def container_show_event(view, event) -> None:  # noqa: N802
    """Re-target the container filter and adopt its rect (see the block above)."""
    self = view
    watch_container(self)
    sync_container_geometry(self)

