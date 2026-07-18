"""Scrollable grid/list of recent project cards."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGridLayout, QSizePolicy, QVBoxLayout, QWidget
from sli_ui_toolkit.widgets import Button, OverlayScrollArea

from services.io.recent_projects import (
    VIEW_GRID,
    VIEW_LIST,
    RecentProjectRecord,
)
from tabs.session_picker.recent.cards import (
    build_grid_card,
    build_list_card,
    update_grid_card,
    update_list_card,
)
from tabs.session_picker.recent.corner_cover import (
    ViewportCornerCover,
    ViewportCornerCoverSync,
)
from tabs.session_picker.recent.layout import (
    GRID_CARD_H,
    ITEMS_MARGIN,
    ITEMS_MARGIN_RIGHT,
    ITEMS_SPACING,
    LIST_CARD_H,
    PANEL_RADIUS,
    content_height_for_rows,
    grid_columns_for_width,
    grid_row_count,
    scroll_viewport_height,
)
from tabs.session_picker.recent.shelf_chrome import OpaqueFillHost, ShelfChrome


def _restore_updates(owner: QWidget, was_updating: bool) -> None:
    """Never leave updates disabled after a visible layout pass.

    Nested callers used to restore ``False`` and punch CSD holes on tab return.
    """
    owner.setUpdatesEnabled(True if owner.isVisible() else was_updating)


class RecentItemsView(QWidget):
    """Owns the scroll area + card grid; sync/relayout without shelf chrome.

    Card identity is keyed by project path. Same-mode refreshes and language
    changes update widgets in place (Session Picker create-cards pattern).
    Destroy/rebuild only when view mode flips or the shelf goes empty↔items.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RecentItemsView")
        self._records: list[RecentProjectRecord] = []
        self._view_mode = VIEW_GRID
        self._grid_columns = 1
        self._cards_by_path: dict[str, Button] = {}
        self._tr: Callable[..., str] | None = None
        self._context = None
        self._on_activate: Callable[[RecentProjectRecord, bool], None] | None = None
        self._on_context_menu: Callable[[RecentProjectRecord], None] | None = None
        self._content_width_provider: Callable[[], int] = lambda: 0
        self._on_viewport_height_changed: Callable[[], None] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = OverlayScrollArea(self)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll.setFixedHeight(
            scroll_viewport_height(content_rows=1, card_h=GRID_CARD_H)
        )
        # Draw the bar over the viewport; cards keep a larger right margin instead.
        scroll.set_reserve_scrollbar_space(False)
        # Panel already paints a rounded shelf. A 1-bit viewport mask here
        # fights the main-window CSD bottom clip when the shelf grows to a
        # second grid row and leaves black wedges in the window corners.
        scroll.set_corner_radius(0)
        scroll.setAcceptDrops(True)
        scroll.setVisible(False)
        root.addWidget(scroll)
        self.scroll = scroll

        # Explicit-paint content well — palette autofill under CSD is flaky.
        self.items_host = OpaqueFillHost()
        self.items_host.setAcceptDrops(True)
        scroll.setWidget(self.items_host)
        self.items_layout = QGridLayout(self.items_host)
        self.items_layout.setContentsMargins(
            ITEMS_MARGIN, ITEMS_MARGIN, ITEMS_MARGIN_RIGHT, ITEMS_MARGIN
        )
        self.items_layout.setHorizontalSpacing(ITEMS_SPACING)
        self.items_layout.setVerticalSpacing(ITEMS_SPACING)
        self.items_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        # AA rounded content well: rectangular Window fill + shelf-colored corners.
        self.corner_cover = ViewportCornerCover(scroll, radius=PANEL_RADIUS)
        self._corner_sync = ViewportCornerCoverSync(scroll, self.corner_cover)

    def configure(
        self,
        *,
        tr: Callable[..., str],
        context,
        on_activate: Callable[[RecentProjectRecord, bool], None],
        on_context_menu: Callable[[RecentProjectRecord], None],
        content_width_provider: Callable[[], int],
        on_viewport_height_changed: Callable[[], None] | None = None,
    ) -> None:
        self._tr = tr
        self._context = context
        self._on_activate = on_activate
        self._on_context_menu = on_context_menu
        self._content_width_provider = content_width_provider
        self._on_viewport_height_changed = on_viewport_height_changed

    @property
    def grid_columns(self) -> int:
        return self._grid_columns

    def card_for(self, path: str) -> Button | None:
        return self._cards_by_path.get(path)

    def apply_surface_colors(self, *, content_bg: QColor, shelf_bg: QColor) -> None:
        ShelfChrome.apply_opaque_widget_fill(self.items_host, content_bg)
        ShelfChrome.apply_opaque_widget_fill(self.scroll.viewport(), content_bg)
        ShelfChrome.apply_opaque_widget_fill(self.scroll, content_bg)
        self.corner_cover.set_color(shelf_bg)
        self._corner_sync.sync()

    def apply_opaque_fill(self, color: QColor) -> None:
        self.apply_surface_colors(content_bg=color, shelf_bg=color)

    def set_visible_for_content(self, has_items: bool) -> None:
        self.items_host.setVisible(has_items)
        self.scroll.setVisible(has_items)
        self.setVisible(has_items)

    def resolve_grid_columns(self) -> int:
        return grid_columns_for_width(max(0, int(self._content_width_provider())))

    def rebuild(
        self,
        *,
        records: list[RecentProjectRecord],
        view_mode: str,
        updates_owner: QWidget,
    ) -> None:
        """Public entry: prefer identity-preserving sync over destroy/rebuild."""
        self.sync(
            records=records,
            view_mode=view_mode,
            updates_owner=updates_owner,
        )

    def sync(
        self,
        *,
        records: list[RecentProjectRecord],
        view_mode: str,
        updates_owner: QWidget,
    ) -> None:
        # One atomic paint: intermediate empty/1-col/ghost-card frames are
        # what made the shelf look jittery on window create.
        was_updating = updates_owner.updatesEnabled()
        updates_owner.setUpdatesEnabled(False)
        try:
            mode_changed = view_mode != self._view_mode
            was_empty = not self._records
            now_empty = not records
            self._records = list(records)
            self._view_mode = view_mode
            self.set_visible_for_content(not now_empty)

            if now_empty:
                self._destroy_all_cards()
                self.sync_scroll_viewport_height()
                return

            if mode_changed or was_empty:
                self._rebuild_all_cards()
                return

            self._sync_card_pool()
        finally:
            _restore_updates(updates_owner, was_updating)

    def retranslate_cards(self) -> None:
        """Patch localized copy on live cards — never destroy/rebuild."""
        if not self._records or self._tr is None:
            return
        updater = (
            update_list_card if self._view_mode == VIEW_LIST else update_grid_card
        )
        for record in self._records:
            card = self._cards_by_path.get(record.path)
            if card is None:
                continue
            updater(
                card,
                record,
                tr=self._tr,
                context=self._context,
            )

    def relayout_grid_if_needed(self, *, updates_owner: QWidget) -> bool:
        """Move existing grid cards into a new column count. Returns True if done."""
        if self._view_mode != VIEW_GRID or not self._records:
            return False
        columns = self.resolve_grid_columns()
        if columns == self._grid_columns:
            return False
        was_updating = updates_owner.updatesEnabled()
        updates_owner.setUpdatesEnabled(False)
        try:
            cards = self._take_grid_cards_in_order()
            if len(cards) != len(self._records):
                for widget in cards:
                    self._discard_card_widget(widget)
                return False
            self.items_layout.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self._reset_column_stretch(list_mode=False, columns=columns)
            self._grid_columns = columns
            for index, card in enumerate(cards):
                row, col = divmod(index, columns)
                self.items_layout.addWidget(
                    card,
                    row,
                    col,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
            self.sync_scroll_viewport_height()
            return True
        finally:
            _restore_updates(updates_owner, was_updating)

    def sync_scroll_viewport_height(self) -> None:
        """Fit content up to two grid rows; scrollbar only when taller than that."""
        count = len(self._records)
        if count <= 0:
            self.scroll.setVisible(False)
            self.items_host.setMinimumHeight(0)
            return
        if self._view_mode == VIEW_LIST:
            rows = count
            card_h = LIST_CARD_H
        else:
            columns = max(1, self._grid_columns)
            rows = grid_row_count(count, columns)
            card_h = GRID_CARD_H
        needed = content_height_for_rows(rows, card_h=card_h)
        viewport = scroll_viewport_height(content_rows=rows, card_h=card_h)
        # widgetResizable would otherwise squash the host to the viewport and
        # never enable scrolling — pin the full content height as a minimum.
        self.items_host.setMinimumHeight(needed)
        prev_h = self.scroll.height()
        self.scroll.setFixedHeight(viewport)
        if prev_h != viewport and self._on_viewport_height_changed is not None:
            self._on_viewport_height_changed()

    def _card_kwargs(self) -> dict:
        return {
            "parent": self.items_host,
            "tr": self._tr,
            "context": self._context,
            "on_activate": self._on_activate,
            "on_context_menu": self._on_context_menu,
        }

    def _rebuild_all_cards(self) -> None:
        self._destroy_all_cards()
        card_kwargs = self._card_kwargs()
        if self._view_mode == VIEW_LIST:
            self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._reset_column_stretch(list_mode=True, columns=1)
            self._grid_columns = 1
            for row, record in enumerate(self._records):
                card = build_list_card(record, **card_kwargs)
                self._cards_by_path[record.path] = card
                self.items_layout.addWidget(card, row, 0)
        else:
            columns = self.resolve_grid_columns()
            self.items_layout.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self._reset_column_stretch(list_mode=False, columns=columns)
            self._grid_columns = columns
            for index, record in enumerate(self._records):
                card = build_grid_card(record, **card_kwargs)
                self._cards_by_path[record.path] = card
                r, c = divmod(index, columns)
                self.items_layout.addWidget(
                    card,
                    r,
                    c,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
        self.sync_scroll_viewport_height()

    def _sync_card_pool(self) -> None:
        """Update/create/remove cards by path; re-slot into layout order."""
        wanted = {record.path for record in self._records}
        for path in list(self._cards_by_path):
            if path not in wanted:
                self._discard_card_widget(self._cards_by_path.pop(path))

        updater = (
            update_list_card if self._view_mode == VIEW_LIST else update_grid_card
        )
        builder = (
            build_list_card if self._view_mode == VIEW_LIST else build_grid_card
        )
        card_kwargs = self._card_kwargs()
        for record in self._records:
            card = self._cards_by_path.get(record.path)
            if card is None:
                card = builder(record, **card_kwargs)
                self._cards_by_path[record.path] = card
            else:
                updater(
                    card,
                    record,
                    tr=self._tr,
                    context=self._context,
                )

        while self.items_layout.count():
            self.items_layout.takeAt(0)

        if self._view_mode == VIEW_LIST:
            self.items_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self._reset_column_stretch(list_mode=True, columns=1)
            self._grid_columns = 1
            for row, record in enumerate(self._records):
                self.items_layout.addWidget(
                    self._cards_by_path[record.path], row, 0
                )
        else:
            columns = self.resolve_grid_columns()
            self.items_layout.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            self._reset_column_stretch(list_mode=False, columns=columns)
            self._grid_columns = columns
            for index, record in enumerate(self._records):
                r, c = divmod(index, columns)
                self.items_layout.addWidget(
                    self._cards_by_path[record.path],
                    r,
                    c,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
        self.sync_scroll_viewport_height()

    def _destroy_all_cards(self) -> None:
        for path in list(self._cards_by_path):
            self._discard_card_widget(self._cards_by_path.pop(path))
        while self.items_layout.count():
            item = self.items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                self._discard_card_widget(widget)
        self._cards_by_path.clear()

    @staticmethod
    def _discard_card_widget(widget: QWidget) -> None:
        # takeAt leaves the widget parented to the host — without reparenting
        # it keeps painting under the next grid and looks like cards "jump".
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    def _reset_column_stretch(self, *, list_mode: bool, columns: int) -> None:
        clear_to = max(columns, self._grid_columns, 1) + 1
        for col in range(clear_to):
            self.items_layout.setColumnStretch(
                col, 1 if list_mode and col == 0 else 0
            )

    def _take_grid_cards_in_order(self) -> list[QWidget]:
        """Detach grid cards in record order without destroying them."""
        cols = max(1, self._grid_columns)
        cards: list[QWidget] = []
        for index in range(len(self._records)):
            row, col = divmod(index, cols)
            item = self.items_layout.itemAtPosition(row, col)
            widget = item.widget() if item is not None else None
            if widget is not None:
                cards.append(widget)
        while self.items_layout.count():
            self.items_layout.takeAt(0)
        return cards


def request_window_chrome_refresh(widget: QWidget) -> None:
    """Re-apply CSD bottom clip after the shelf height changes in-place."""
    win = widget.window()
    if win is None:
        return
    apply_mask = getattr(win, "_apply_rounded_mask", None)

    def _refresh() -> None:
        if callable(apply_mask):
            try:
                apply_mask()
            except Exception:
                pass
        win.update()

    QTimer.singleShot(0, _refresh)
