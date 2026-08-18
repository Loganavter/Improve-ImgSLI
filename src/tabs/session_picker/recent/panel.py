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


# Safety margin (px) for the pre-layout height estimate: sizeHint() reports a
# widget a few px taller than its final laid-out height, and a single grid row
# is ~140 px. Keep the estimate slightly *under* the real available space so
# the first frame never overestimates (a grow is less jarring than a shrink).
# Computed lazily so a live UI-scale change is always picked up.
_PRELAYOUT_HEIGHT_BUFFER_PX = 32

# Root layout margins/spacing (design px) for the shelf content — re-applied
# on live UiScale changes (see ``_on_ui_scale_changed``); build and handler
# share these so they can never drift apart.
_PANEL_MARGIN_LEFT = 16
_PANEL_MARGIN_TOP = 14
_PANEL_MARGIN_RIGHT = 16
_PANEL_MARGIN_BOTTOM = 14
_PANEL_SPACING = 10


def _prelayout_height_buffer() -> int:
    return scaled_px(_PRELAYOUT_HEIGHT_BUFFER_PX)


class _ShelfChromeCompat:
    """Legacy view over the shared shelf chrome for ``panel._chrome`` reads."""

    def __init__(self, shelf: ShelfWidget) -> None:
        self._shelf = shelf

    @property
    def content_bg(self) -> QColor:
        return self._shelf.content_bg()

    @property
    def panel_bg(self) -> QColor:
        return self._shelf.panel_bg()

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


def _window_will_fill_screen(window) -> bool:
    """Whether the top-level window will end up maximized/fullscreen.

    ``isMaximized()``/``isFullScreen()`` cover the already-applied state; the
    persisted ``window_was_maximized`` flag covers platforms that apply
    window states asynchronously (Wayland only configures the surface after
    show), where the state is still ``False`` during the pre-layout content
    build even though the window will fill the screen on the first frame.
    The two always agree at startup: the geometry manager sets/clears the
    maximized state from exactly this flag before content builds.
    """
    if window is None:
        _shelf_resize_debug("_window_will_fill_screen: window is None")
        return False
    if window.isMaximized() or window.isFullScreen():
        _shelf_resize_debug(
            "_window_will_fill_screen: state already applied (maximized=%s fullscreen=%s)",
            window.isMaximized(),
            window.isFullScreen(),
        )
        return True
    store = getattr(window, "store", None)
    settings = getattr(store, "settings", None)
    flag = bool(getattr(settings, "window_was_maximized", False))
    _shelf_resize_debug(
        "_window_will_fill_screen: store=%s settings=%s was_maximized=%s -> %s",
        store is not None,
        settings is not None,
        flag,
        flag,
    )
    return flag


def _prelayout_screen(window):
    """Best-guess screen for a not-yet-shown window (its ``screen()`` is
    usually ``None`` before the first map); falls back to the primary screen."""
    screen = getattr(window, "screen", None)
    screen = screen() if callable(screen) else None
    if screen is None:
        from PySide6.QtWidgets import QApplication

        screen = QApplication.primaryScreen()
    return screen


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

    # --- test / legacy aliases (owned by composed children) -----------------

    @property
    def _panel_bg(self):
        return self.panel_bg()

    @_panel_bg.setter
    def _panel_bg(self, value) -> None:
        self._shelf_panel = QColor(value)
        self.update()

    @property
    def _chrome(self):
        """Legacy test accessor: ``panel._chrome.content_bg`` (shelf chrome)."""
        return _ShelfChromeCompat(self)

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
        return self._items.scroll_area

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
        # Title now lives on the shared shelf.
        return self.title_label()

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
        ShelfWidget.apply_opaque_widget_fill(widget, color)

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
        # Shelf root margins/spacing come from ShelfWidget defaults (scaled).
        root = self.root_layout()

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
        _shelf_resize_debug("ui scale changed -> factor=%s", _factor)
        root = self.layout()
        if root is not None:
            root.setContentsMargins(
                scaled_px(SHELF_MARGIN_LEFT),
                scaled_px(SHELF_MARGIN_TOP),
                scaled_px(SHELF_MARGIN_RIGHT),
                scaled_px(SHELF_MARGIN_BOTTOM),
            )
            root.setSpacing(scaled_px(SHELF_SPACING))
        if self._empty_zone is not None:
            self._empty_zone.reapply_scaled_height()
        if not self._layout_ready or not self._records:
            self._sync_shelf_panel_height()
            self.update()
            return
        if self._sync_settle_in_progress:
            return
        self._sync_settle_in_progress = True
        try:
            self._items.reapply_scaled_geometry(updates_owner=self)
            self._sync_shelf_panel_height()
            if self._shelf_height_settle_pending:
                self._shelf_height_settle_pending = False
                self._settle_shelf_height()
        finally:
            self._sync_settle_in_progress = False
        self.update()

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
        """Max vertical space for the recent items viewport.

        The shelf should show as many rows as fit in the window below the
        create-cards instead of a hardcoded two rows. Computes how much of the
        page-scroll viewport is left below this panel's top edge (minus the
        page's bottom margin and the panel's own header + margins). Returns 0
        before the page is laid out, so the items view falls back to its fixed
        two-row cap.
        """
        # Live geometry after the first layout pass is ground truth.
        if self.testAttribute(Qt.WidgetAttribute.WA_Resized):
            try:
                page = self.parentWidget()
                if page is not None:
                    scroll_viewport = page.parentWidget()
                    if scroll_viewport is not None and scroll_viewport.height() > 0:
                        viewport_h = scroll_viewport.height()
                        y = self.mapTo(page, QPoint(0, 0)).y()
                        header = getattr(self, "_header", None)
                        header_h = (
                            header.sizeHint().height()
                            if header is not None and header.sizeHint().isValid()
                            else 0
                        )
                        root = self.layout()
                        margins = (
                            cast(tuple[int, int, int, int], root.getContentsMargins())
                            if root is not None
                            else (0, 0, 0, 0)
                        )
                        spacing = root.spacing() if root is not None else 0
                        top_margin = margins[1]
                        bottom_margin = margins[3]
                        # Session picker page content layout bottom margin (48,40,48,40).
                        page_bottom_margin = scaled_px(40)
                        available = (
                            viewport_h
                            - y
                            - page_bottom_margin
                            - header_h
                            - spacing
                            - top_margin
                            - bottom_margin
                        )
                        _shelf_resize_debug(
                            "_recent_viewport_max_height (live) viewport_h=%d panel_y=%d "
                            "header=%d page_bottom=%d -> available=%d (panel_h=%d)",
                            viewport_h,
                            y,
                            header_h,
                            page_bottom_margin,
                            available,
                            self.height(),
                        )
                        # Keep the sign: a *negative* available means the host
                        # measured the space and there is no room even for one
                        # row — ``scroll_viewport_height`` caps at one scaled
                        # row then, instead of misreading 0 as "no signal"
                        # and keeping the fixed two-row fallback.
                        return int(available)
            except Exception:
                pass
        # Pre-layout estimate from the already-restored window geometry (the
        # main window is sized by LoadWindowStateStep before content builds,
        # mirroring estimate_prelayout_width) so the first frame does not
        # flash the fixed two-row cap and then jump when the real height is
        # known.
        return self._estimate_prelayout_viewport_height()

    def _estimate_prelayout_viewport_height(self) -> int:
        """Best-guess available viewport height before the first layout pass.

        Mirrors ``estimate_prelayout_width``: the main window geometry is
        restored (LoadWindowStateStep) before content builds, so the viewport
        height is real even though this panel has never been laid out. The
        chrome above the shelf is read from the page layout itself (sum of the
        sibling widgets' ``sizeHint`` heights + the layout's own spacings and
        margins) rather than hardcoded pixels, so it stays correct when the
        create-cards/title change.
        """
        try:
            window = self.window()
            if window is None:
                return 0
            if _window_will_fill_screen(window):
                screen = _prelayout_screen(window)
                window_h = (
                    int(screen.availableGeometry().height())
                    if screen is not None
                    else 0
                )
                _shelf_resize_debug(
                    "_estimate_prelayout_viewport_height: fill-screen height=%d "
                    "(screen=%s)",
                    window_h,
                    type(screen).__name__ if screen is not None else None,
                )
            else:
                window_h = int(window.height())
                _shelf_resize_debug(
                    "_estimate_prelayout_viewport_height: window height=%d",
                    window_h,
                )
            if window_h <= 0:
                return 0
            title_bar = getattr(window, "_custom_title_bar", None)
            title_h = title_bar.height() if title_bar is not None else 0
            viewport_h = max(0, window_h - title_h)

            # Chrome above the shelf viewport = page layout (top margin +
            # every sibling before this panel + inter-item spacing + bottom
            # margin) + the panel's own header + root margins.
            chrome = 0
            parent = self.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is None:
                # Not inside a real page (bare panel in tests) — no way to
                # estimate; the items view falls back to its fixed cap.
                return 0
            margins = cast(tuple[int, int, int, int], layout.getContentsMargins())
            spacing = layout.spacing()
            above = 0
            seen = 0
            for i in range(layout.count()):
                item = layout.itemAt(i)
                widget = item.widget() if item is not None else None
                if widget is self:
                    break
                if widget is not None:
                    above += max(0, widget.sizeHint().height())
                    seen += 1
            chrome = margins[1] + above + max(0, seen - 1) * spacing + margins[3]
            header = getattr(self, "_header", None)
            header_h = header.sizeHint().height() if header is not None else 0
            root = self.layout()
            root_margins = (
                cast(tuple[int, int, int, int], root.getContentsMargins())
                if root is not None
                else (0, 0, 0, 0)
            )
            root_spacing = root.spacing() if root is not None else 0
            chrome += (
                header_h + root_spacing + root_margins[1] + root_margins[3]
            )
            # sizeHint() overreports a pre-layout widget's final height by a
            # small, theme/font-dependent amount; leave a buffer under a grid
            # row so the first frame never overestimates the available space
            # (a one-row grow on the next pass is less jarring than a shrink).
            chrome += _prelayout_height_buffer()
            return max(0, viewport_h - chrome)
        except Exception:
            return 0

    def _grid_content_width(self) -> int:
        # Scroll fills the panel horizontally; width can be 0 before the first
        # layout pass (the synchronous refresh() in SessionPickerWidget._build()
        # runs before this page is ever shown). estimate_prelayout_width falls
        # back to the already-known main-window width in that case (see its
        # docstring) instead of guessing via a static floor — this makes the
        # very first grid build pick the right column/row count instead of
        # under-guessing and visibly re-flowing on the first real resize.
        layout = self.layout()
        margins = layout.contentsMargins() if layout is not None else None
        horizontal_margins = (
            margins.left() + margins.right() if margins is not None else 0
        )
        if self.testAttribute(Qt.WidgetAttribute.WA_Resized):
            # Once this panel has actually been laid out, its own width is the
            # ground truth — do NOT let estimate_prelayout_width override it.
            # That helper's isMaximized/isFullScreen branch exists for the
            # pre-layout build, but during the fullscreen→windowed transition
            # Qt can deliver the restored-size resize while isFullScreen() is
            # still reporting True; the estimate would then keep returning the
            # fullscreen width and the grid would never shrink back. The live
            # geometry here is correct in both directions of travel.
            width = max(0, int(self.width()))
        else:
            estimate = estimate_prelayout_width(
                self,
                # The page content margins are scaled_px(48) per side, so the
                # real-px chrome between the window and this panel grows with
                # the UI scale factor.
                horizontal_chrome=scaled_px(SESSION_PICKER_PAGE_HORIZONTAL_MARGINS),
                floor=scaled_px(SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR)
                + horizontal_margins,
            )
            width = estimate
            # Wayland applies the maximized state only after show, so the
            # helper's isMaximized() branch misses it during the pre-layout
            # build; the persisted flag says the window will fill the screen,
            # and building the grid for the transitional (normal) width then
            # reflowing to the screen width is exactly the visible second
            # frame this estimate exists to prevent.
            window = self.window()
            fill = _window_will_fill_screen(window)
            screen = _prelayout_screen(window) if fill else None
            screen_w = -1
            if screen is not None:
                screen_w = (
                    int(screen.availableGeometry().width())
                    - scaled_px(SESSION_PICKER_PAGE_HORIZONTAL_MARGINS)
                )
                width = max(width, screen_w)
            _shelf_resize_debug(
                "_grid_content_width prelayout: estimate=%d fill_screen=%s "
                "screen=%s screen_w=%d -> %d (window_w=%d)",
                estimate,
                fill,
                type(screen).__name__ if screen is not None else None,
                screen_w,
                width,
                int(window.width()) if window is not None else -1,
            )
        return max(width - horizontal_margins, SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR)

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