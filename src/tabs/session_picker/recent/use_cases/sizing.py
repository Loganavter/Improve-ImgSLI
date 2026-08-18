"""Viewport sizing calculations for the Recent Projects shelf.

Computes how many rows of recent-project cards fit in the available window
space, handling both live geometry (after the first layout pass) and
pre-layout estimates (before the page is ever shown — critical for
Wayland, where the maximized state is applied asynchronously).
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, cast

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import scaled_px

from tabs.host_helpers import estimate_prelayout_width
from tabs.session_picker.geometry import (
    SESSION_PICKER_PAGE_HORIZONTAL_MARGINS,
    SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR,
)

if TYPE_CHECKING:
    from tabs.session_picker.recent.panel import RecentProjectsPanel

logger = logging.getLogger("ImproveImgSLI")


def _shelf_resize_debug(message: str, *args) -> None:
    flag = os.environ.get("IMGSLI_SHELF_RESIZE_DEBUG", "").strip().lower()
    if flag in ("", "0", "false", "no", "off"):
        return
    try:
        logger.info(
            "[shelf-resize] " + (message % args if args else message)
        )
    except Exception:
        pass


_PRELAYOUT_HEIGHT_BUFFER_PX = 32


def _prelayout_height_buffer() -> int:
    return scaled_px(_PRELAYOUT_HEIGHT_BUFFER_PX)


def window_will_fill_screen(window) -> bool:
    """Whether the top-level window will end up maximized/fullscreen.

    ``isMaximized()``/``isFullScreen()`` cover the already-applied state; the
    persisted ``window_was_maximized`` flag covers platforms that apply
    window states asynchronously (Wayland only configures the surface after
    show), where the state is still ``False`` during the pre-layout content
    build even though the window will fill the screen on the first frame.
    """
    if window is None:
        _shelf_resize_debug("window_will_fill_screen: window is None")
        return False
    if window.isMaximized() or window.isFullScreen():
        _shelf_resize_debug(
            "window_will_fill_screen: state already applied (maximized=%s fullscreen=%s)",
            window.isMaximized(),
            window.isFullScreen(),
        )
        return True
    store = getattr(window, "store", None)
    settings = getattr(store, "settings", None)
    flag = bool(getattr(settings, "window_was_maximized", False))
    _shelf_resize_debug(
        "window_will_fill_screen: store=%s settings=%s was_maximized=%s -> %s",
        store is not None,
        settings is not None,
        flag,
        flag,
    )
    return flag


def _prelayout_screen(window):
    """Best-guess screen for a not-yet-shown window; falls back to primary."""
    screen = getattr(window, "screen", None)
    screen = screen() if callable(screen) else None
    if screen is None:
        screen = QApplication.primaryScreen()
    return screen


def recent_viewport_max_height(panel: RecentProjectsPanel) -> int:
    """Max vertical space for the recent items viewport.

    Computes how much of the page-scroll viewport is left below this panel's
    top edge (minus the page's bottom margin and the panel's own header +
    margins). Returns 0 before the page is laid out, so the items view falls
    back to its fixed two-row cap.
    """
    # Live geometry after the first layout pass is ground truth.
    if panel.testAttribute(Qt.WidgetAttribute.WA_Resized):
        try:
            page = panel.parentWidget()
            if page is not None:
                scroll_viewport = page.parentWidget()
                if scroll_viewport is not None and scroll_viewport.height() > 0:
                    viewport_h = scroll_viewport.height()
                    y = panel.mapTo(page, QPoint(0, 0)).y()
                    header = getattr(panel, "_header", None)
                    header_h = (
                        header.sizeHint().height()
                        if header is not None and header.sizeHint().isValid()
                        else 0
                    )
                    root = panel.layout()
                    margins = (
                        cast(tuple[int, int, int, int], root.getContentsMargins())
                        if root is not None
                        else (0, 0, 0, 0)
                    )
                    spacing = root.spacing() if root is not None else 0
                    top_margin = margins[1]
                    bottom_margin = margins[3]
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
                        "recent_viewport_max_height (live) viewport_h=%d panel_y=%d "
                        "header=%d page_bottom=%d -> available=%d (panel_h=%d)",
                        viewport_h,
                        y,
                        header_h,
                        page_bottom_margin,
                        available,
                        panel.height(),
                    )
                    return int(available)
        except Exception:
            pass
    return estimate_prelayout_viewport_height(panel)


def estimate_prelayout_viewport_height(panel: RecentProjectsPanel) -> int:
    """Best-guess available viewport height before the first layout pass.

    The main window geometry is restored (LoadWindowStateStep) before content
    builds, so the viewport height is real even though this panel has never
    been laid out. The chrome above the shelf is read from the page layout
    itself rather than hardcoded pixels.
    """
    try:
        window = panel.window()
        if window is None:
            return 0
        if window_will_fill_screen(window):
            screen = _prelayout_screen(window)
            window_h = (
                int(screen.availableGeometry().height())
                if screen is not None
                else 0
            )
            _shelf_resize_debug(
                "estimate_prelayout_viewport_height: fill-screen height=%d "
                "(screen=%s)",
                window_h,
                type(screen).__name__ if screen is not None else None,
            )
        else:
            window_h = int(window.height())
            _shelf_resize_debug(
                "estimate_prelayout_viewport_height: window height=%d",
                window_h,
            )
        if window_h <= 0:
            return 0
        title_bar = getattr(window, "_custom_title_bar", None)
        title_h = title_bar.height() if title_bar is not None else 0
        viewport_h = max(0, window_h - title_h)

        chrome = 0
        parent = panel.parentWidget()
        layout = parent.layout() if parent is not None else None
        if layout is None:
            return 0
        margins = cast(tuple[int, int, int, int], layout.getContentsMargins())
        spacing = layout.spacing()
        above = 0
        seen = 0
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if widget is panel:
                break
            if widget is not None:
                above += max(0, widget.sizeHint().height())
                seen += 1
        chrome = margins[1] + above + max(0, seen - 1) * spacing + margins[3]
        header = getattr(panel, "_header", None)
        header_h = header.sizeHint().height() if header is not None else 0
        root = panel.layout()
        root_margins = (
            cast(tuple[int, int, int, int], root.getContentsMargins())
            if root is not None
            else (0, 0, 0, 0)
        )
        root_spacing = root.spacing() if root is not None else 0
        chrome += (
            header_h + root_spacing + root_margins[1] + root_margins[3]
        )
        chrome += _prelayout_height_buffer()
        return max(0, viewport_h - chrome)
    except Exception:
        return 0


def grid_content_width(panel: RecentProjectsPanel) -> int:
    """Content width for the recent items grid.

    Scroll fills the panel horizontally; width can be 0 before the first
    layout pass. estimate_prelayout_width falls back to the main-window width
    in that case instead of guessing via a static floor.
    """
    layout = panel.layout()
    margins = layout.contentsMargins() if layout is not None else None
    horizontal_margins = (
        margins.left() + margins.right() if margins is not None else 0
    )
    if panel.testAttribute(Qt.WidgetAttribute.WA_Resized):
        width = max(0, int(panel.width()))
    else:
        estimate = estimate_prelayout_width(
            panel,
            horizontal_chrome=scaled_px(SESSION_PICKER_PAGE_HORIZONTAL_MARGINS),
            floor=scaled_px(SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR)
            + horizontal_margins,
        )
        width = estimate
        window = panel.window()
        fill = window_will_fill_screen(window)
        screen = _prelayout_screen(window) if fill else None
        screen_w = -1
        if screen is not None:
            screen_w = (
                int(screen.availableGeometry().width())
                - scaled_px(SESSION_PICKER_PAGE_HORIZONTAL_MARGINS)
            )
            width = max(width, screen_w)
        _shelf_resize_debug(
            "grid_content_width prelayout: estimate=%d fill_screen=%s "
            "screen=%s screen_w=%d -> %d (window_w=%d)",
            estimate,
            fill,
            type(screen).__name__ if screen is not None else None,
            screen_w,
            width,
            int(window.width()) if window is not None else -1,
        )
    return max(width - horizontal_margins, SESSION_PICKER_RECENT_CONTENT_WIDTH_FLOOR)


def on_ui_scale_changed(panel: RecentProjectsPanel, _factor: float) -> None:
    """Re-apply scale-dependent shelf geometry after a live UiScale change."""
    _shelf_resize_debug("ui scale changed -> factor=%s", _factor)
    root = panel.layout()
    if root is not None:
        from tabs.session_picker.recent.panel import (
            SHELF_MARGIN_BOTTOM,
            SHELF_MARGIN_LEFT,
            SHELF_MARGIN_RIGHT,
            SHELF_MARGIN_TOP,
            SHELF_SPACING,
        )

        root.setContentsMargins(
            scaled_px(SHELF_MARGIN_LEFT),
            scaled_px(SHELF_MARGIN_TOP),
            scaled_px(SHELF_MARGIN_RIGHT),
            scaled_px(SHELF_MARGIN_BOTTOM),
        )
        root.setSpacing(scaled_px(SHELF_SPACING))
    if panel._empty_zone is not None:
        panel._empty_zone.reapply_scaled_height()
    if not panel._layout_ready or not panel._records:
        panel._sync_shelf_panel_height()
        panel.update()
        return
    if panel._sync_settle_in_progress:
        return
    panel._sync_settle_in_progress = True
    try:
        panel._items.reapply_scaled_geometry(updates_owner=panel)
        panel._sync_shelf_panel_height()
        if panel._shelf_height_settle_pending:
            panel._shelf_height_settle_pending = False
            panel._settle_shelf_height()
    finally:
        panel._sync_settle_in_progress = False
    panel.update()
