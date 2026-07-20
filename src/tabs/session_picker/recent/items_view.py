"""Scrollable grid/list of recent project cards (row-window virtualized)."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import (
    QGridLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from sli_ui_toolkit.widgets import Button, MarqueeBandGesture, OverlayScrollArea

from services.io.recent_projects import (
    VIEW_GRID,
    VIEW_LIST,
    RecentProjectRecord,
)
from tabs.session_picker.recent.cards import (
    apply_fixed_card_size,
    apply_list_card_size,
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
    GRID_CARD_W,
    ITEMS_MARGIN,
    ITEMS_MARGIN_RIGHT,
    ITEMS_SPACING,
    LIST_CARD_H,
    PANEL_RADIUS,
    VIRTUAL_ROW_BUFFER,
    content_height_for_rows,
    grid_columns_for_width,
    grid_row_count,
    row_stride,
    scroll_viewport_height,
    visible_row_window,
)
from tabs.session_picker.recent.selection import (
    apply_card_selected,
    ctrl_held,
    paths_intersecting_rect,
    preview_selection,
    selection_accent_color,
)
from tabs.session_picker.recent.shelf_chrome import OpaqueFillHost, ShelfChrome


def _restore_updates(owner: QWidget, was_updating: bool) -> None:
    """Never leave updates disabled after a visible layout pass.

    Nested callers used to restore ``False`` and punch CSD holes on tab return.
    """
    owner.setUpdatesEnabled(True if owner.isVisible() else was_updating)


class RecentItemsView(QWidget):
    """Owns the scroll area + virtualized card window without shelf chrome.

    Only cards in the scroll viewport (+ ``VIRTUAL_ROW_BUFFER`` rows) are live
    ``Button`` widgets. Host height stays full-content so the scrollbar range
    is correct. Card identity for the live window is keyed by project path.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("RecentItemsView")
        self._records: list[RecentProjectRecord] = []
        self._view_mode = VIEW_GRID
        self._grid_columns = 1
        self._cards_by_path: dict[str, Button] = {}
        self._pool: list[Button] = []
        self._window: tuple[int, int] = (0, -1)
        self._tr: Callable[..., str] | None = None
        self._context = None
        self._on_activate: Callable[..., None] | None = None
        self._on_context_menu: Callable[[RecentProjectRecord], None] | None = None
        self._content_width_provider: Callable[[], int] = lambda: 0
        self._on_viewport_height_changed: Callable[[], None] | None = None
        self._updates_owner: QWidget | None = None
        self._selection_paths: Callable[[], set[str]] = lambda: set()
        self._on_marquee_commit: Callable[[set[str], bool], None] | None = None
        self._on_marquee_preview: Callable[[set[str], bool], None] | None = None
        self._marquee_gesture: MarqueeBandGesture | None = None
        self._marquee_additive = False
        self._marquee_base: set[str] = set()
        self._selection_accent = selection_accent_color()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = OverlayScrollArea(self)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll.setFixedHeight(
            scroll_viewport_height(content_rows=1, card_h=GRID_CARD_H)
        )
        scroll.set_reserve_scrollbar_space(False)
        scroll.set_corner_radius(0)
        scroll.setAcceptDrops(True)
        scroll.setVisible(False)
        root.addWidget(scroll)
        self.scroll = scroll

        self.items_host = OpaqueFillHost()
        self.items_host.setAcceptDrops(True)
        self.items_host.setMouseTracking(True)
        self.items_host.installEventFilter(self)
        scroll.setWidget(self.items_host)
        self.items_layout = QGridLayout()
        self.items_layout.setContentsMargins(
            ITEMS_MARGIN, ITEMS_MARGIN, ITEMS_MARGIN_RIGHT, ITEMS_MARGIN
        )
        self.items_layout.setHorizontalSpacing(ITEMS_SPACING)
        self.items_layout.setVerticalSpacing(ITEMS_SPACING)
        self.items_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )

        self.corner_cover = ViewportCornerCover(scroll, radius=PANEL_RADIUS)
        self._corner_sync = ViewportCornerCoverSync(scroll, self.corner_cover)

        bar = scroll.verticalScrollBar()
        bar.valueChanged.connect(self._on_scroll_value_changed)

    def configure(
        self,
        *,
        tr: Callable[..., str],
        context,
        on_activate: Callable[..., None],
        on_context_menu: Callable[[RecentProjectRecord], None],
        content_width_provider: Callable[[], int],
        on_viewport_height_changed: Callable[[], None] | None = None,
        selection_paths: Callable[[], set[str]] | None = None,
        on_marquee_commit: Callable[[set[str], bool], None] | None = None,
        on_marquee_preview: Callable[[set[str], bool], None] | None = None,
    ) -> None:
        self._tr = tr
        self._context = context
        self._on_activate = on_activate
        self._on_context_menu = on_context_menu
        self._content_width_provider = content_width_provider
        self._on_viewport_height_changed = on_viewport_height_changed
        if selection_paths is not None:
            self._selection_paths = selection_paths
        self._on_marquee_commit = on_marquee_commit
        self._on_marquee_preview = on_marquee_preview
        self._selection_accent = selection_accent_color(
            getattr(self, "_theme_manager", None)
        )

    @property
    def grid_columns(self) -> int:
        return self._grid_columns

    @property
    def live_card_count(self) -> int:
        return len(self._cards_by_path)

    def card_for(self, path: str) -> Button | None:
        return self._cards_by_path.get(path)

    def apply_selection(self, selected: set[str] | None = None) -> None:
        """Sync accent fill on live cards to ``selected`` (or provider)."""
        paths = self._selection_paths() if selected is None else selected
        accent = self._selection_accent
        for path, card in self._cards_by_path.items():
            apply_card_selected(card, path in paths, accent=accent)

    def refresh_selection_accent(self) -> None:
        self._selection_accent = selection_accent_color(
            getattr(self, "_theme_manager", None)
        )
        if self._marquee_gesture is not None:
            self._marquee_gesture.set_accent(self._selection_accent)
        self.apply_selection()

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

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if watched is self.items_host:
            if event.type() == QEvent.Type.MouseButtonPress and isinstance(
                event, QMouseEvent
            ):
                return self._host_mouse_press(event)
        return super().eventFilter(watched, event)

    def _ensure_marquee_gesture(self) -> MarqueeBandGesture:
        if self._marquee_gesture is None:
            self._marquee_gesture = MarqueeBandGesture(
                self.items_host,
                parent=self,
                clip_widget=self.scroll.viewport(),
                on_update=self._on_marquee_rect_update,
                on_finish=self._on_marquee_rect_finish,
            )
        else:
            self._marquee_gesture.set_clip_widget(self.scroll.viewport())
        self._marquee_gesture.set_accent(self._selection_accent)
        return self._marquee_gesture

    def _paths_for_marquee_rect(self, rect: QRect) -> set[str]:
        if rect.isEmpty():
            return set()
        host_w = max(self.items_host.width(), self._content_width_provider())
        return paths_intersecting_rect(
            self._records,
            rect,
            view_mode=self._view_mode,
            columns=self._grid_columns,
            host_width=host_w,
        )

    def _on_marquee_rect_update(self, rect: QRect) -> None:
        paths = self._paths_for_marquee_rect(rect)
        if self._on_marquee_preview is not None:
            self._on_marquee_preview(paths, self._marquee_additive)
        else:
            preview = preview_selection(
                self._marquee_base, paths, additive=self._marquee_additive
            )
            self.apply_selection(preview)

    def _on_marquee_rect_finish(self, rect: QRect) -> None:
        if rect.isEmpty():
            if self._on_marquee_commit is not None and not self._marquee_additive:
                self._on_marquee_commit(set(), False)
            return
        paths = self._paths_for_marquee_rect(rect)
        if self._on_marquee_commit is not None:
            self._on_marquee_commit(paths, self._marquee_additive)

    def _host_mouse_press(self, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        child = self.items_host.childAt(event.position().toPoint())
        if child is not None:
            return False
        self._marquee_additive = ctrl_held(event.modifiers())
        self._marquee_base = set(self._selection_paths())
        gesture = self._ensure_marquee_gesture()
        if not gesture.start(event.position().toPoint()):
            return False
        # Live clear (non-additive) so the band starts empty immediately.
        if self._on_marquee_preview is not None:
            self._on_marquee_preview(set(), self._marquee_additive)
        return True

    def rebuild(
        self,
        *,
        records: list[RecentProjectRecord],
        view_mode: str,
        updates_owner: QWidget,
    ) -> None:
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
        was_updating = updates_owner.updatesEnabled()
        updates_owner.setUpdatesEnabled(False)
        try:
            self._updates_owner = updates_owner
            mode_changed = view_mode != self._view_mode
            now_empty = not records
            self._records = list(records)
            self._view_mode = view_mode
            self.set_visible_for_content(not now_empty)

            if now_empty:
                self._destroy_all_cards()
                self._clear_pool()
                self._window = (0, -1)
                self.sync_scroll_viewport_height()
                return

            if mode_changed:
                self._destroy_all_cards()
                self._clear_pool()
                self._window = (0, -1)

            if self._view_mode == VIEW_LIST:
                self._grid_columns = 1
            else:
                self._grid_columns = self.resolve_grid_columns()

            self.sync_scroll_viewport_height()
            self._refresh_visible_window(force=True)
        finally:
            _restore_updates(updates_owner, was_updating)

    def retranslate_cards(self) -> None:
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
        if self._view_mode != VIEW_GRID or not self._records:
            return False
        columns = self.resolve_grid_columns()
        if columns == self._grid_columns:
            return False
        was_updating = updates_owner.updatesEnabled()
        updates_owner.setUpdatesEnabled(False)
        try:
            self._updates_owner = updates_owner
            self._grid_columns = columns
            self.sync_scroll_viewport_height()
            self._refresh_visible_window(force=True)
            return True
        finally:
            _restore_updates(updates_owner, was_updating)

    def sync_scroll_viewport_height(self) -> None:
        count = len(self._records)
        if count <= 0:
            self.scroll.setVisible(False)
            self.items_host.setMinimumHeight(0)
            self.items_host.resize(self.items_host.width(), 0)
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
        width = max(self.scroll.viewport().width(), self._content_width_provider())
        self.items_host.setMinimumSize(max(1, int(width)), needed)
        self.items_host.resize(max(1, int(width)), needed)
        prev_h = self.scroll.height()
        self.scroll.setFixedHeight(viewport)
        if prev_h != viewport and self._on_viewport_height_changed is not None:
            self._on_viewport_height_changed()

    def _on_scroll_value_changed(self, _value: int) -> None:
        self._refresh_visible_window(force=False)

    def _card_h(self) -> int:
        return LIST_CARD_H if self._view_mode == VIEW_LIST else GRID_CARD_H

    def _total_rows(self) -> int:
        count = len(self._records)
        if count <= 0:
            return 0
        if self._view_mode == VIEW_LIST:
            return count
        return grid_row_count(count, max(1, self._grid_columns))

    def _compute_window(self) -> tuple[int, int]:
        return visible_row_window(
            self.scroll.verticalScrollBar().value(),
            self.scroll.viewport().height(),
            row_stride_px=row_stride(self._card_h()),
            total_rows=self._total_rows(),
            buffer=VIRTUAL_ROW_BUFFER,
        )

    def _paths_for_window(self, first_row: int, last_row: int) -> list[str]:
        if last_row < first_row or not self._records:
            return []
        columns = max(1, self._grid_columns)
        if self._view_mode == VIEW_LIST:
            start = first_row
            end = last_row + 1
        else:
            start = first_row * columns
            end = (last_row + 1) * columns
        end = min(end, len(self._records))
        start = max(0, start)
        return [self._records[i].path for i in range(start, end)]

    def _refresh_visible_window(self, *, force: bool) -> None:
        if not self._records:
            return
        first, last = self._compute_window()
        if not force and (first, last) == self._window:
            self._place_live_cards(first, last)
            self.apply_selection()
            return
        self._window = (first, last)
        wanted = set(self._paths_for_window(first, last))

        for path in list(self._cards_by_path):
            if path not in wanted:
                self._recycle_card(path)

        records_by_path = {r.path: r for r in self._records}
        for path in wanted:
            record = records_by_path.get(path)
            if record is None:
                continue
            card = self._cards_by_path.get(path)
            if card is None:
                card = self._acquire_card(record)
                self._cards_by_path[path] = card
            else:
                self._update_card(card, record)
            card.show()

        self._place_live_cards(first, last)
        self.apply_selection()

    def _place_live_cards(self, first_row: int, last_row: int) -> None:
        if last_row < first_row:
            return
        card_h = self._card_h()
        stride = row_stride(card_h)
        columns = max(1, self._grid_columns)
        host_w = max(self.items_host.width(), self._content_width_provider())
        list_w = max(1, int(host_w) - ITEMS_MARGIN - ITEMS_MARGIN_RIGHT)

        for index, record in enumerate(self._records):
            card = self._cards_by_path.get(record.path)
            if card is None:
                continue
            if self._view_mode == VIEW_LIST:
                row = index
                x = ITEMS_MARGIN
                w = list_w
                apply_list_card_size(card, LIST_CARD_H)
            else:
                row, col = divmod(index, columns)
                x = ITEMS_MARGIN + col * (GRID_CARD_W + ITEMS_SPACING)
                w = GRID_CARD_W
                apply_fixed_card_size(card, GRID_CARD_W, GRID_CARD_H)
            if row < first_row or row > last_row:
                continue
            y = ITEMS_MARGIN + row * stride
            card.setGeometry(x, y, w, card_h)
            card.raise_()

    def _card_kwargs(self) -> dict:
        return {
            "parent": self.items_host,
            "tr": self._tr,
            "context": self._context,
            "on_activate": self._on_activate,
            "on_context_menu": self._on_context_menu,
        }

    def _recycle_card(self, path: str) -> None:
        card = self._cards_by_path.pop(path, None)
        if card is None:
            return
        apply_card_selected(card, False, accent=self._selection_accent)
        card.hide()
        if len(self._pool) < 24:
            card.setParent(self)
            self._pool.append(card)
        else:
            self._discard_card_widget(card)

    def _acquire_card(self, record: RecentProjectRecord) -> Button:
        if self._pool:
            card = self._pool.pop()
            card.setParent(self.items_host)
            self._update_card(card, record)
            return card
        builder = (
            build_list_card if self._view_mode == VIEW_LIST else build_grid_card
        )
        return builder(record, **self._card_kwargs())

    def _update_card(self, card: Button, record: RecentProjectRecord) -> None:
        updater = (
            update_list_card if self._view_mode == VIEW_LIST else update_grid_card
        )
        updater(
            card,
            record,
            tr=self._tr,
            context=self._context,
        )

    def _destroy_all_cards(self) -> None:
        for path in list(self._cards_by_path):
            self._discard_card_widget(self._cards_by_path.pop(path))
        self._cards_by_path.clear()

    def _clear_pool(self) -> None:
        for card in self._pool:
            self._discard_card_widget(card)
        self._pool.clear()

    @staticmethod
    def _discard_card_widget(widget: QWidget) -> None:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()


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
