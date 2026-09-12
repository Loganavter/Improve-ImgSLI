"""Layout, sizing, and height settle for ``RecentProjectsPanel``.

Split from ``panel.py`` to keep that class down to composition/wiring,
following the ``use_cases`` pattern (see docs/dev/CODE_PATTERNS.md).

Every function takes the panel as its first argument and reads/writes its
instance state (``_header_host``, ``_items``, ``_layout_ready``, ``_records``,
``_view_mode``, timers, …) directly.
"""

from __future__ import annotations

import logging
from typing import cast

from PySide6.QtCore import QTimer

from services.io.recent_projects import VIEW_LIST

logger = logging.getLogger(__name__)


def _shelf_resize_debug(message: str, *args) -> None:
    logger.debug(message, *args)


def sync_shelf_panel_height(panel) -> None:
    """Make the panel's height equal header + spacing + content + margins *now*.

    The default layout sizeHint lags the scroll's just-changed fixed height
    by one layout pass, so the first frame would show a short panel with the
    scroll overflowing its rounded bottom ("jumps one part first").
    setFixedHeight sidesteps this: the layout gives the panel exactly this
    height synchronously, so the panel and scroll never disagree.  The
    layout spacing is part of the vertical footprint: omitting it makes
    the panel 10px short, the items view gets compressed and the scroll
    (with its bottom corner rounding) is clipped by it."""
    header = getattr(panel, "_header_host", None)
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
    scroll = getattr(panel, "_items", None)
    scroll_h = scroll.scroll_area.height() if scroll is not None else 0
    new_h = max(
        1, header_h + spacing + scroll_h + margins[1] + margins[3]
    )
    _shelf_resize_debug(
        "_sync_shelf_panel_height header=%d scroll=%d spacing=%d margins=%d -> panel_h=%d (was %d)",
        header_h,
        scroll_h,
        spacing,
        margins[1] + margins[3],
        new_h,
        panel.height(),
    )
    panel.setFixedHeight(new_h)


def schedule_deferred_relayout(panel) -> None:
    if not panel._painted_once:
        if panel._sync_settle_in_progress:
            return
        panel._sync_settle_in_progress = True
        try:
            deferred_relayout(panel)
            if panel._shelf_height_settle_pending:
                panel._shelf_height_settle_pending = False
                settle_shelf_height(panel)
        finally:
            panel._sync_settle_in_progress = False
        return
    if panel._relayout_timer is None:
        panel._relayout_timer = QTimer(panel)
        panel._relayout_timer.setSingleShot(True)
        panel._relayout_timer.setInterval(0)
        panel._relayout_timer.timeout.connect(lambda: deferred_relayout(panel))
    _shelf_resize_debug(
        "schedule deferred_relayout (active=%s) scroll=%d panel=%d visible=%s",
        panel._relayout_timer.isActive(),
        getattr(panel._items.scroll_area, "height", lambda: -1)(),
        panel.height(),
        panel.isVisible(),
    )
    panel._relayout_timer.start()


def deferred_relayout(panel) -> None:
    _shelf_resize_debug(
        "deferred_relayout scroll=%d panel=%d",
        getattr(panel._items.scroll_area, "height", lambda: -1)(),
        panel.height(),
    )
    if not panel._layout_ready or not panel._records:
        return
    panel._shelf_height_settle_pending = False
    if panel._view_mode == VIEW_LIST:
        panel._items.relayout_list_if_needed(updates_owner=panel)
    else:
        relayouted = panel._items.relayout_grid_if_needed(updates_owner=panel)
        if not relayouted:
            if panel._items.resolve_grid_columns() != panel._items.grid_columns:
                panel._rebuild_items()
    if panel._shelf_height_settle_pending:
        schedule_height_settle(panel)


def schedule_height_settle(panel) -> None:
    if panel._settle_timer is None:
        panel._settle_timer = QTimer(panel)
        panel._settle_timer.setSingleShot(True)
        panel._settle_timer.setInterval(0)
        panel._settle_timer.timeout.connect(lambda: settle_shelf_height(panel))
    _shelf_resize_debug(
        "schedule height_settle (active=%s) scroll=%d panel=%d",
        panel._settle_timer.isActive(),
        getattr(panel._items.scroll_area, "height", lambda: -1)(),
        panel.height(),
    )
    panel._settle_timer.start()


def on_shelf_height_changed(panel) -> None:
    """Called when the scroll viewport height changed during a relayout."""
    panel._shelf_height_settle_pending = True
    _shelf_resize_debug(
        "on_shelf_height_changed scroll=%d panel=%d",
        getattr(panel._items.scroll_area, "height", lambda: -1)(),
        panel.height(),
    )
    sync_shelf_panel_height(panel)
    from tabs.session_picker.recent.items_view import request_window_chrome_refresh

    request_window_chrome_refresh(panel)


def settle_shelf_height(panel) -> None:
    """Re-run the parent layout so the panel height catches the scroll."""
    _shelf_resize_debug(
        "settle_shelf_height scroll=%d panel=%d",
        getattr(panel._items.scroll_area, "height", lambda: -1)(),
        panel.height(),
    )
    panel.updateGeometry()
    parent = panel.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is not None:
        layout.activate()
    panel.update()
