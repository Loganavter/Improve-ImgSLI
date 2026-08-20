"""TabRegistry use_cases: theme-appearance flush for visible/hidden workspace pages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tabs.registry import TabRegistry

logger = logging.getLogger("ImproveImgSLI")


def apply_appearance(registry: "TabRegistry", host_window) -> None:
    """Refresh theme-owned chrome; skip hidden workspace pages.

    Hidden tabs (e.g. Image Compare while the session picker is up) are
    marked stale and flushed on the next ``flush_stale_appearance`` /
    session switch — theme flips stay responsive.
    """
    ui = getattr(host_window, "ui", None)
    stack = getattr(ui, "workspace_stack", None)
    current = stack.currentWidget() if stack is not None else None
    for session_type, tab in registry._tabs.items():
        page = registry._pages.get(session_type)
        if current is not None and page is not None and page is not current:
            registry._appearance_stale.add(session_type)
            continue
        try:
            tab.apply_appearance(host_window)
            registry._appearance_stale.discard(session_type)
        except Exception as e:
            logger.error(f"Tab appearance error ({tab.session_type}): {e}")


def flush_stale_appearance(registry: "TabRegistry", host_window) -> None:
    """Apply deferred theme chrome for the currently visible tab page."""
    if not registry._appearance_stale:
        return
    ui = getattr(host_window, "ui", None)
    stack = getattr(ui, "workspace_stack", None)
    current = stack.currentWidget() if stack is not None else None
    if current is None:
        return
    for session_type in tuple(registry._appearance_stale):
        if registry._pages.get(session_type) is not current:
            continue
        tab = registry._tabs.get(session_type)
        if tab is None:
            registry._appearance_stale.discard(session_type)
            continue
        try:
            tab.apply_appearance(host_window)
            registry._appearance_stale.discard(session_type)
        except Exception as e:
            logger.error(f"Tab appearance flush error ({session_type}): {e}")
