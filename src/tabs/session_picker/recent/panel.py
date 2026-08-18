"""Resolve/Shotcut-style recent projects shelf for the Session Picker."""

from __future__ import annotations

import logging
import os
from typing import Callable, cast

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget
from sli_ui_toolkit.i18n import translatable_callback
from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.widgets import (
    Button,
    ContextMenuAction,
    popup_context_menu_for_anchor,
)

from ui.theming import resolve_theme_color

logger = logging.getLogger("ImproveImgSLI")
from ui.widgets.shelf import (
    PANEL_RADIUS,
    SHELF_MARGIN_BOTTOM,
    SHELF_MARGIN_LEFT,
    SHELF_MARGIN_RIGHT,
    SHELF_MARGIN_TOP,
    SHELF_SPACING,
    ShelfWidget,
    apply_opaque_widget_fill,
)


def _shelf_resize_debug(message: str, *args) -> None:
    flag = os.environ.get("IMGSLI_SHELF_RESIZE_DEBUG", "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return
    try:
        logging.getLogger("ImproveImgSLI").info(
            "[shelf-resize] " + (message % args if args else message)
        )
    except Exception:
        pass


# Root layout margins/spacing (design px) for the shelf content — re-applied
# on live UiScale changes (see ``_on_ui_scale_changed``); build and handler
# share these so they can never drift apart.
_PANEL_MARGIN_LEFT = 16
_PANEL_MARGIN_TOP = 14
_PANEL_MARGIN_RIGHT = 16
_PANEL_MARGIN_BOTTOM = 14
_PANEL_SPACING = 10


# get_recent_sort_mode/get_recent_view_mode/list_recent_projects/
# record_recent_project/remove_recent_project/sort_recent_projects are not
# called directly in this file -- use_cases/refresh.py and
# use_cases/selection_ops.py re-import them from *this* module (not from
# services.io.recent_projects) so that tests monkeypatching
# "tabs.session_picker.recent.panel.<name>" keep working after the split.
from services.io.recent_projects import (
    get_recent_sort_mode,
    get_recent_sort_order,
    get_recent_view_mode,
    list_recent_projects,
    notify_recent_cap_eviction,
    record_recent_project,
    remove_recent_project,
    RecentProjectRecord,
    sort_recent_projects,
    VIEW_LIST,
)
from tabs.host_helpers import estimate_prelayout_width
from tabs.session_picker.geometry import (
    SESSION_PICKER_PAGE_HORIZONTAL_MARGINS,
    SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR,
)
from tabs.session_picker.recent.drop_controller import RecentDropController
from ui.widgets.shelf.empty_drop_zone import EmptyDropZone
from tabs.session_picker.recent.header_bar import RecentHeaderBar
from tabs.session_picker.recent.items_view import (
    RecentItemsView,
    request_window_chrome_refresh,
)
from tabs.session_picker.recent.use_cases import refresh as refresh_use_cases
from tabs.session_picker.recent.use_cases import selection_ops
from tabs.session_picker.recent.use_cases import sizing


def _shelf_resize_debug(message: str, *args) -> None:
    flag = os.environ.get("IMGSLI_SHELF_RESIZE_DEBUG", "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return
    try:
        logging.getLogger("ImproveImgSLI").info(
            "[shelf-resize] " + (message % args if args else message)
        )
    except Exception:
        pass


# Root layout margins/spacing (design px) for the shelf content — re-applied
# on live UiScale changes (see ``_on_ui_scale_changed``); build and handler
# share these so they can never drift apart.
_PANEL_MARGIN_LEFT = 16
_PANEL_MARGIN_TOP = 14
_PANEL_MARGIN_RIGHT = 16
_PANEL_MARGIN_BOTTOM = 14
_PANEL_SPACING = 10


class RecentProjectsPanel(ShelfWidget):
    """Shelf host: chrome + title from ``ShelfWidget``; composes header
    controls, items view, empty zone, and drops.

    The shared shelf (``ui.widgets.shelf.ShelfWidget``) owns the two-layer
    chrome (host surface + rounded panel) and the header/content structure;
    this panel only decides *what* goes in: sort/view chips on top and the
    items view + empty drop zone as content.
    """

    def __init__(self, parent=None, *, tr: Callable[..., str], context=None):
        super().__init__(parent)
        self._tr = tr
        self._context = context
        self._on_open: Callable[[str], None] | None = None
        self._view_mode = get_recent_view_mode()
        self._sort_mode = get_recent_sort_mode()
        self._sort_order = get_recent_sort_order()
        self._records: list[RecentProjectRecord] = []
        # False until the first synchronous refresh builds cards (or empty zone).
        self._layout_ready = False
        self._selected_paths: set[str] = set()
        # Set by ``_on_shelf_height_changed`` when a relayout changed the scroll
        # viewport height; consumed by ``_deferred_relayout`` to re-settle the
        # panel height after the parent page layout re-runs.
        self._shelf_height_settle_pending = False
        # Coalesces resize-driven relayouts to the next event-loop turn.
        self._relayout_timer: QTimer | None = None
        # Runs the height settle on a separate turn after the relayout.
        self._settle_timer: QTimer | None = None
        # False until the first paint. Resize-driven relayouts are deferred to
        # 0-timers normally, but before the first paint those timers can only
        # fire after the first frame was already presented (see
        # ``_schedule_deferred_relayout``) — settle synchronously instead.
        self._painted_once = False
        # Guards re-entrancy of the synchronous first settle.
        self._sync_settle_in_progress = False
        self.setObjectName("RecentProjectsPanel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        # Prefer painting a full shelf fill without claiming OpaquePaintEvent —
        # that flag + a skipped/disabled update leaves CSD holes on tab return.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)
        self._build()
        self._sync_opaque_fills()
        self._sync_shelf_panel_height()
        window = self.window()
        if window is not None and window is not self:
            window.installEventFilter(self)
        translatable_callback(
            self, lambda _lang: self._retranslate(), defer_when_hidden=True
        )
        UiScale.get_instance().scale_changed.connect(self._on_ui_scale_changed)

    def set_open_project_handler(self, handler: Callable[[str], None] | None) -> None:
        self._on_open = handler

    def resizeEvent(self, event) -> None:  # noqa: N802
        _shelf_resize_debug(
            "panel.resizeEvent size=%s -> %s scroll=%d",
            event.oldSize(),
            event.size(),
            getattr(self._items.scroll_area, "height", lambda: -1)(),
        )
        super().resizeEvent(event)
        self._sync_shelf_panel_height()
        self._items.resync_corner_cover()
        if not self._layout_ready or not self._records:
            return
        # Defer the relayout to the next event-loop turn and coalesce: a resize
        # may arrive while the parent page layout is still mid-activation, so
        # re-running that layout inside resizeEvent is a no-op and the panel
        # height would lag the new scroll height by one pass (the "jumps one
        # part first" artifact). Running later lets ``_settle_shelf_height``
        # re-activate the layout synchronously. Crucially we must NOT hold
        # updates disabled here — under the translucent CSD window that punches
        # see-through holes in the freshly exposed panel area during the drag.
        self._schedule_deferred_relayout()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        # The panel's own resizeEvent does not fire when the window grows but
        # the shelf is capped at its available space (the page layout hands
        # the extra to the stretch instead). Watch the top-level window so the
        # shelf expands to fit the new available height (see
        # _recent_viewport_max_height) instead of staying at its old size.
        if (
            event.type() == QEvent.Type.Resize
            and watched is self.window()
            and self.isVisible()
        ):
            _shelf_resize_debug(
                "window resizeEvent size=%s (panel=%d scroll=%d)",
                event.size(),
                self.height(),
                getattr(self._items.scroll_area, "height", lambda: -1)(),
            )
            self._sync_shelf_panel_height()
            self._schedule_deferred_relayout()
        return super().eventFilter(watched, event)

    def _sync_shelf_panel_height(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.sync_shelf_panel_height(self)

    def _schedule_deferred_relayout(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.schedule_deferred_relayout(self)

    def _deferred_relayout(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.deferred_relayout(self)

    def _schedule_height_settle(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.schedule_height_settle(self)

    def _on_shelf_height_changed(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.on_shelf_height_changed(self)

    def _settle_shelf_height(self) -> None:
        from tabs.session_picker.recent.use_cases import layout

        layout.settle_shelf_height(self)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._painted_once = True
        if not hasattr(self, "_paint_count"):
            self._paint_count = 0
        self._paint_count += 1
        _shelf_resize_debug(
            "paint #%d panel=%dx%d scroll_h=%d cols=%d visible=%s",
            self._paint_count,
            self.width(),
            self.height(),
            getattr(self._items.scroll_area, "height", lambda: -1)(),
            getattr(self._items, "grid_columns", -1),
            self.isVisible(),
        )
        super().paintEvent(event)
        if self._drop.drag_active:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            accent = QColor(resolve_theme_color(self._theme_manager, "accent"))
            fill = QColor(accent)
            fill.setAlpha(36)
            path = QPainterPath()
            rect = self.rect().adjusted(0, 0, -1, -1)
            path.addRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
            painter.fillPath(path, fill)
            pen = QPen(accent, 2.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            painter.end()

    def _on_shelf_theme_changed(self) -> None:
        # ShelfWidget calls this; children may not exist yet during __init__.
        if getattr(self, "_header", None) is not None:
            self._sync_header_controls()
        self._sync_opaque_fills()
        self._sync_empty_zone_colors()
        items = getattr(self, "_items", None)
        if items is not None:
            items.refresh_selection_accent()
        super()._on_shelf_theme_changed()

    def _header_button_bg(self):
        return self.header_button_bg()

    def _apply_opaque_widget_fill(self, widget: QWidget | None, color) -> None:
        apply_opaque_widget_fill(widget, color)

    def _sync_opaque_fills(self) -> None:
        if getattr(self, "_items", None) is None:
            return
        self._items.apply_surface_colors(
            content_bg=self.content_bg(),
            shelf_bg=self.panel_bg(),
        )

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
        # Prefer page-driven on_page_shown(); sync first fill if we somehow
        # became visible without an explicit populate.
        if not self._layout_ready:
            self.refresh()

    def on_page_shown(self) -> None:
        """Called when Session Picker becomes the active workspace page again."""
        self._sync_opaque_fills()
        self._sync_empty_zone_colors()
        if not self._layout_ready:
            self.refresh()
            self.recover_opaque_surface()
            return
        # Do not destroy/rebuild cards on every tab return — that races the CSD
        # mask and leaves transparent holes. Soft-refresh only when MRU/prefs
        # actually changed.
        self._soft_refresh()
        self.recover_opaque_surface()

    def refresh(self) -> None:
        refresh_use_cases.refresh(self)

    def _soft_refresh(self) -> None:
        refresh_use_cases.soft_refresh(self)

    def _build(self) -> None:
        self.set_title(self._tr("recent.title", "Recent"))

        self._header = RecentHeaderBar(self, tr=self._tr)
        self._header.prefs_changed.connect(self._on_header_prefs_changed)
        self.add_header_widget(self._header)
        self._header.installEventFilter(self)

        self._items = RecentItemsView(self)
        self._items.configure(
            tr=self._tr,
            context=self._context,
            on_activate=self._on_card_activate,
            on_context_menu=self._show_context_menu,
            content_width_provider=self._grid_content_width,
            max_viewport_height_provider=self._recent_viewport_max_height,
            on_viewport_height_changed=self._on_shelf_height_changed,
            selection_paths=lambda: set(self._selected_paths),
            on_marquee_commit=self._on_marquee_commit,
            on_marquee_preview=self._on_marquee_preview,
        )
        self.add_content_widget(self._items)

        self._empty_zone = EmptyDropZone(self)
        self._sync_empty_zone_texts()
        self._sync_empty_zone_colors()
        self.add_content_widget(self._empty_zone)

        self._drop = RecentDropController(
            self,
            on_paths=self._pin_dropped_paths,
            on_active_changed=self._on_drag_active_changed,
        )
        self._drop.install(
            (
                self,
                self._items.scroll_area,
                self._items.items_host,
                self._empty_zone,
            )
        )
        self._sync_header_controls()

    def _on_ui_scale_changed(self, _factor: float) -> None:
        """Re-apply scale-dependent shelf geometry after a live UiScale change."""
        sizing.on_ui_scale_changed(self, _factor)

    def _on_header_prefs_changed(self) -> None:
        # Header already persisted prefs; re-read and refresh cards.
        self.refresh()

    def _on_drag_active_changed(self, active: bool) -> None:
        if self._empty_zone is not None:
            self._empty_zone.set_drag_active(active)
        self.update()

    def _pin_dropped_paths(self, paths: list[str]) -> None:
        refresh_use_cases.pin_dropped_paths(self, paths)

    def _retranslate(self) -> None:
        self.set_title(self._tr("recent.title", "Recent"))
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
        colors = self.empty_zone_colors()
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

    def _recent_viewport_max_height(self) -> int:
        return sizing.recent_viewport_max_height(self)

    def _estimate_prelayout_viewport_height(self) -> int:
        return sizing.estimate_prelayout_viewport_height(self)

    def _grid_content_width(self) -> int:
        return sizing.grid_content_width(self)

    def _rebuild_items(self) -> None:
        refresh_use_cases.rebuild_items(self)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selected_paths:
                self._remove_selected_paths()
                event.accept()
                logger.debug("[shelf-nav] keyPressEvent Del/Bs -> remove %d selected", len(self._selected_paths))
                return
        if key == Qt.Key.Key_Escape:
            if self._selected_paths:
                self._clear_selection()
                event.accept()
                logger.debug("[shelf-nav] keyPressEvent Escape -> clear selection")
                return
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            # If focus is on a header button, let the event propagate up to
            # SessionPickerWidget → tab strip instead of sending back to cards.
            focused = QApplication.focusWidget()
            header = getattr(self, "_header", None)
            if header is not None and focused is not None:
                buttons = [
                    b for b in (header.sort_button, header.sort_order_button, header.view_button)
                    if b.isVisible()
                ]
                if focused in buttons:
                    # Up from first header button → exit the shelf entirely
                    event.ignore()
                    super().keyPressEvent(event)
                    return
            page = self.parentWidget()
            while page is not None and not hasattr(page, "_focus_create_card"):
                page = page.parentWidget()
            if page is not None:
                if page._focus_create_card(-1):
                    event.accept()
                    logger.debug("[shelf-nav] Up/Left -> handoff to page create-cards")
                    return
        super().keyPressEvent(event)

    def _on_marquee_preview(self, paths: set[str], additive: bool) -> None:
        selection_ops.on_marquee_preview(self, paths, additive)

    def _on_marquee_commit(self, paths: set[str], additive: bool) -> None:
        selection_ops.on_marquee_commit(self, paths, additive)

    def _clear_selection(self) -> None:
        selection_ops.clear_selection(self)

    def _on_card_activate(
        self,
        record: RecentProjectRecord,
        missing: bool,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        selection_ops.on_card_activate(self, record, missing, modifiers)

    def focus_recent_item(self, first: bool) -> bool:
        """Focus the first (``first=True``) or last recent item card.

        Returns False when the shelf is empty or has no live cards — the
        caller (SessionPickerWidget) then falls back to wrapping within the
        create-cards.
        """
        items = getattr(self, "_items", None)
        if items is None or not getattr(items, "_records", None):
            logger.debug(
                "[shelf-nav] focus_recent_item first=%s -> False (empty shelf)", first
            )
            return False
        result = items.navigate_focus(1 if first else -1)
        logger.debug(
            "[shelf-nav] focus_recent_item first=%s -> %s", first, result
        )
        return result

    def focus_header_control(self, first: bool) -> bool:
        """Focus the first or last visible header-bar control button.

        Returns False when the header has no visible controls.
        """
        header = getattr(self, "_header", None)
        if header is None:
            logger.debug(
                "[shelf-nav] focus_header_control first=%s -> False (no header)", first
            )
            return False
        buttons = [
            b
            for b in (header.sort_button, header.sort_order_button, header.view_button)
            if b.isVisible()
        ]
        if not buttons:
            logger.debug(
                "[shelf-nav] focus_header_control first=%s -> False (no visible buttons)", first
            )
            return False
        buttons[0 if first else -1].setFocus(Qt.FocusReason.OtherFocusReason)
        logger.debug(
            "[shelf-nav] focus_header_control first=%s -> True (button=%s)",
            first,
            type(buttons[0 if first else -1]).__name__,
        )
        return True

    def set_keyboard_handoff(self, callback) -> None:
        """Set a callback invoked when keyboard navigation would leave the
        shelf going upward/leftward past the first item (hands focus back to
        the create-cards)."""
        if getattr(self, "_items", None) is not None:
            self._items._keyboard_handoff = callback

    def _activate(self, record: RecentProjectRecord, missing: bool) -> None:
        selection_ops.activate(self, record, missing)

    def _show_context_menu(self, record: RecentProjectRecord) -> None:
        selection_ops.show_context_menu(self, record)

    def _remove_record(self, record: RecentProjectRecord) -> None:
        selection_ops.remove_record(self, record)

    def _remove_selected_paths(self) -> None:
        selection_ops.remove_selected_paths(self)