"""Resolve/Shotcut-style recent projects shelf for the Session Picker."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
)
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget
from sli_ui_toolkit.i18n import translatable_callback
from sli_ui_toolkit.widgets import ThemedWidget

from services.io.recent_projects import (
    get_recent_sort_mode,
    get_recent_sort_order,
    get_recent_view_mode,
    list_recent_projects,
    record_recent_project,
    remove_recent_project,
    RecentProjectRecord,
    sort_recent_projects,
    VIEW_GRID,
)
from tabs.session_picker.recent.context_menu import open_recent_project_menu
from tabs.session_picker.recent.drop_controller import RecentDropController
from tabs.session_picker.recent.empty_drop_zone import EmptyDropZone
from tabs.session_picker.recent.header_bar import RecentHeaderBar
from tabs.session_picker.recent.items_view import (
    RecentItemsView,
    request_window_chrome_refresh,
)
from tabs.session_picker.recent.shelf_chrome import ShelfChrome


class RecentProjectsPanel(ThemedWidget, QWidget):
    """Shelf host: composes header, items view, empty zone, chrome, and drops."""

    def __init__(self, parent=None, *, tr: Callable[..., str], context=None):
        # Chrome before QWidget init — ThemedWidget may call on_theme_changed
        # during super().__init__.
        self._chrome = ShelfChrome()
        super().__init__(parent)
        self._tr = tr
        self._context = context
        self._on_open: Callable[[str], None] | None = None
        self._view_mode = get_recent_view_mode()
        self._sort_mode = get_recent_sort_mode()
        self._sort_order = get_recent_sort_order()
        self._records: list[RecentProjectRecord] = []
        # First paint waits for a deferred layout pass so cards are not shown
        # at 1-column / empty-shelf geometry and then jump.
        self._layout_ready = False
        self._initial_refresh_scheduled = False
        self.setObjectName("RecentProjectsPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAcceptDrops(True)
        # Prefer painting a full shelf fill without claiming OpaquePaintEvent —
        # that flag + a skipped/disabled update leaves CSD holes on tab return.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        self._build()
        self._sync_opaque_fills()
        translatable_callback(self, lambda _lang: self._retranslate())

    # --- test / legacy aliases (owned by composed children) -----------------

    @property
    def _panel_bg(self):
        return self._chrome.panel_bg

    @_panel_bg.setter
    def _panel_bg(self, value) -> None:
        self._chrome.panel_bg = value

    @property
    def _drag_active(self) -> bool:
        return self._drop.drag_active

    @_drag_active.setter
    def _drag_active(self, value: bool) -> None:
        self._drop.drag_active = bool(value)

    @property
    def _grid_columns(self) -> int:
        return self._items.grid_columns

    @_grid_columns.setter
    def _grid_columns(self, value: int) -> None:
        self._items._grid_columns = max(1, int(value))

    @property
    def _scroll(self):
        return self._items.scroll

    @property
    def _items_host(self):
        return self._items.items_host

    @property
    def _items_layout(self):
        return self._items.items_layout

    @property
    def _sort_button(self):
        return self._header.sort_button

    @property
    def _sort_order_button(self):
        return self._header.sort_order_button

    @property
    def _view_button(self):
        return self._header.view_button

    @property
    def _title_label(self):
        return self._header.title_label

    def set_open_project_handler(self, handler: Callable[[str], None] | None) -> None:
        self._on_open = handler

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._layout_ready:
            return
        if self._view_mode != VIEW_GRID or not self._records:
            return
        if not self._items.relayout_grid_if_needed(updates_owner=self):
            # Layout/record drift — fall back to a full rebuild.
            if self._items.resolve_grid_columns() != self._items.grid_columns:
                self._rebuild_items()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        self._chrome.paint_shelf(
            painter,
            widget=self,
            event_rect=event.rect(),
            theme_manager=self._theme_manager,
            drag_active=self._drop.drag_active,
        )
        painter.end()

    def on_theme_changed(self) -> None:
        chrome = getattr(self, "_chrome", None)
        if chrome is None:
            super().on_theme_changed()
            return
        chrome.update_from_theme(self._theme_manager)
        # ThemedWidget calls this from __init__ before children exist.
        if getattr(self, "_header", None) is not None:
            self._sync_header_controls()
        self._sync_opaque_fills()
        self._sync_empty_zone_colors()
        self.update()
        super().on_theme_changed()

    def _header_button_bg(self):
        return self._chrome.header_button_bg()

    def _apply_opaque_widget_fill(self, widget: QWidget | None, color) -> None:
        ShelfChrome.apply_opaque_widget_fill(widget, color)

    def _sync_opaque_fills(self) -> None:
        if getattr(self, "_items", None) is None:
            return
        self._chrome.apply_opaque_fills(items_view=self._items)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        self._drop.handle_drag_enter(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:  # noqa: N802
        self._drop.handle_drag_move(event)

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        self._drop.handle_drag_leave(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self._drop.handle_drop(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        # Prefer page-driven on_page_shown(); keep a deferred first layout only.
        if not self._layout_ready:
            self.schedule_initial_layout()

    def on_page_shown(self) -> None:
        """Called when Session Picker becomes the active workspace page again."""
        self._sync_opaque_fills()
        self._sync_empty_zone_colors()
        if not self._layout_ready:
            self.schedule_initial_layout()
            return
        # Do not destroy/rebuild cards on every tab return — that races the CSD
        # mask and leaves transparent holes. Soft-refresh only when MRU/prefs
        # actually changed.
        self._soft_refresh()
        self.update()

    def schedule_initial_layout(self) -> None:
        """Defer the first card build until geometry is settled."""
        if self._layout_ready or self._initial_refresh_scheduled:
            return
        self._initial_refresh_scheduled = True
        QTimer.singleShot(0, self._run_initial_layout)

    def _run_initial_layout(self) -> None:
        self._initial_refresh_scheduled = False
        if not self._layout_ready:
            self.refresh()

    def refresh(self) -> None:
        self._view_mode = get_recent_view_mode()
        self._sort_mode = get_recent_sort_mode()
        self._sort_order = get_recent_sort_order()
        records = list_recent_projects(drop_missing=False)
        self._records = sort_recent_projects(
            records,
            sort_by=self._sort_mode,
            sort_order=self._sort_order,
        )
        self._rebuild_items()
        self._sync_header_controls()
        self._sync_opaque_fills()
        self._layout_ready = True

    def _soft_refresh(self) -> None:
        """Update shelf contents only when records or view prefs changed."""
        view_mode = get_recent_view_mode()
        sort_mode = get_recent_sort_mode()
        sort_order = get_recent_sort_order()
        records = sort_recent_projects(
            list_recent_projects(drop_missing=False),
            sort_by=sort_mode,
            sort_order=sort_order,
        )
        same_prefs = (
            view_mode == self._view_mode
            and sort_mode == self._sort_mode
            and sort_order == self._sort_order
        )
        same_records = [
            (r.path, r.opened_at, r.display_name, r.session_types)
            for r in self._records
        ] == [
            (r.path, r.opened_at, r.display_name, r.session_types)
            for r in records
        ]
        if same_prefs and same_records:
            self._sync_header_controls()
            return
        self._view_mode = view_mode
        self._sort_mode = sort_mode
        self._sort_order = sort_order
        self._records = records
        self._rebuild_items()
        self._sync_header_controls()
        self._sync_opaque_fills()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        self._header = RecentHeaderBar(self, tr=self._tr)
        self._header.prefs_changed.connect(self._on_header_prefs_changed)
        root.addWidget(self._header)

        self._items = RecentItemsView(self)
        self._items.configure(
            tr=self._tr,
            context=self._context,
            on_activate=self._activate,
            on_context_menu=self._show_context_menu,
            content_width_provider=self._grid_content_width,
            on_viewport_height_changed=lambda: request_window_chrome_refresh(self),
        )
        root.addWidget(self._items)

        self._empty_zone = EmptyDropZone(self)
        self._sync_empty_zone_texts()
        self._sync_empty_zone_colors()
        root.addWidget(self._empty_zone)

        self._drop = RecentDropController(
            self,
            on_paths=self._pin_dropped_paths,
            on_active_changed=self._on_drag_active_changed,
        )
        self._drop.install(
            (
                self,
                self._items.scroll,
                self._items.items_host,
                self._empty_zone,
            )
        )
        self._sync_header_controls()

    def _on_header_prefs_changed(self) -> None:
        # Header already persisted prefs; re-read and refresh cards.
        self.refresh()

    def _on_drag_active_changed(self, active: bool) -> None:
        if self._empty_zone is not None:
            self._empty_zone.set_drag_active(active)
        self.update()

    def _pin_dropped_paths(self, paths: list[str]) -> None:
        for path in paths:
            try:
                record_recent_project(path)
            except Exception:
                continue
        self.refresh()

    def _retranslate(self) -> None:
        self._sync_header_controls()
        self._sync_empty_zone_texts()
        # Same as create-cards: patch copy in place. Destroy/rebuild under a
        # translucent CSD parent leaves see-through holes after language Apply.
        self._items.retranslate_cards()
        self.recover_opaque_surface()

    def recover_opaque_surface(self) -> None:
        """Re-apply shelf fills and force a paint after theme/layout churn."""
        self._sync_opaque_fills()
        self._sync_empty_zone_colors()
        self.update()
        request_window_chrome_refresh(self)

    def _sync_empty_zone_texts(self) -> None:
        if self._empty_zone is None:
            return
        self._empty_zone.set_texts(
            title=self._tr("recent.empty_title", "Load your first project"),
            hint=self._tr(
                "recent.empty_hint",
                "Drop a .imgsli file here to pin it",
            ),
        )

    def _sync_empty_zone_colors(self) -> None:
        zone = getattr(self, "_empty_zone", None)
        if zone is None:
            return
        colors = self._chrome.empty_zone_colors(self._theme_manager)
        zone.set_palette_colors(**colors)

    def _sync_header_controls(self) -> None:
        if getattr(self, "_header", None) is None:
            return
        self._header.sync(
            sort_mode=self._sort_mode,
            sort_order=self._sort_order,
            view_mode=self._view_mode,
            has_items=bool(getattr(self, "_records", None)),
            chip_bg=self._header_button_bg(),
        )

    def _grid_content_width(self) -> int:
        # Scroll fills the panel horizontally; its sizeHint can be tiny before
        # the first layout pass, so never trust viewport width alone.
        return max(0, int(self.width()))

    def _rebuild_items(self) -> None:
        has_items = bool(self._records)
        if self._empty_zone is not None:
            self._empty_zone.setVisible(not has_items)
        self._header.set_controls_visible(has_items)
        self._items.rebuild(
            records=self._records,
            view_mode=self._view_mode,
            updates_owner=self,
        )
        self._sync_opaque_fills()

    def _activate(self, record: RecentProjectRecord, missing: bool) -> None:
        # Re-check on disk: cards can stay "alive" after the file was deleted.
        exists = Path(record.path).is_file()
        if missing or not exists:
            # Keep the pinned entry. Removal is only via the context menu.
            # If the card still looked "alive", rebuild into the missing state.
            if not missing:
                self.refresh()
            return
        if self._on_open is not None:
            self._on_open(record.path)

    def _show_context_menu(self, record: RecentProjectRecord) -> None:
        open_recent_project_menu(
            source_widget=self.window() or self,
            record=record,
            tr=self._tr,
            on_open=lambda r: self._activate(r, missing=False),
            on_remove=self._remove_record,
        )

    def _remove_record(self, record: RecentProjectRecord) -> None:
        remove_recent_project(record.path)
        self.refresh()
