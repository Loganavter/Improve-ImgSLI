"""Workspace tab order: drag-reorder persistence for the tab strip.

The strip itself is drag-movable out of the box
(``ui.main_window.ui.enable_workspace_tab_reordering``); this module is the
persistence side. ``AdaptiveTabStrip.tabMoved`` reports the tab's *final*
index after a drag, and the new visible order is written back into the
workspace session list — the single source of truth for tab order, which is
exactly the list a project file saves and restores. No second store, and no
persistence by index alone: tabs are identified by ``tabData`` (the session
id).

Kept out of ``workspace.py`` (which owns the per-tab presenters) so neither
module grows into the file-size audit limit for one feature.
"""

from __future__ import annotations

import logging

from ui.host_debug import workspace_transition_debug
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def connect_workspace_tab_reordering(presenter) -> bool:
    """Wire drag-reorder persistence onto the workspace tab strip.

    Returns False when the toolkit build has no ``tabMoved`` (a released
    toolkit older than the reorder API): the strip then stays click-only and
    nothing is persisted.
    """
    tabs = getattr(getattr(presenter, "ui", None), "workspace_tabs", None)
    connect = getattr(getattr(tabs, "tabMoved", None), "connect", None)
    if not callable(connect):
        return False
    connect(
        lambda from_index, to_index: on_workspace_tab_moved(
            presenter, from_index, to_index
        )
    )
    return True


def on_workspace_tab_moved(presenter, from_index: int, to_index: int) -> None:
    """Persist the strip's visible order after a user drag reorder.

    Nothing is switched: the active session id is untouched, so the tab that
    was current stays current at its new position. The whole visible order is
    read from ``tabData``; ids that no longer exist are skipped by the store,
    so a session closed mid-drag does not shuffle the rest.
    """
    ui = getattr(presenter, "ui", None)
    tabs = getattr(ui, "workspace_tabs", None)
    if tabs is None or getattr(ui, "_restoring_tab_order", False):
        # A rebuild (``sync_workspace_tabs``) is restoring the saved order —
        # persisting its intermediate moves would race the source of truth.
        return
    order: list[str] = []
    try:
        for index in range(tabs.count()):
            session_id = tabs.tabData(index)
            if session_id:
                order.append(session_id)
    except Exception:
        logger.exception("on_workspace_tab_moved: reading tab order failed")
        return
    if not order:
        return
    workspace = getattr(
        getattr(presenter, "main_controller", None), "workspace", None
    )
    reorder = getattr(workspace, "reorder_workspace_sessions", None)
    if not callable(reorder):
        return
    try:
        reorder(order)
    except Exception:
        logger.exception("on_workspace_tab_moved: persisting tab order failed")
        return
    workspace_transition_debug(
        "tab_moved from=%s to=%s order=%s", from_index, to_index, order
    )
