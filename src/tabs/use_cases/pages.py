"""TabRegistry use_cases: lazy page creation/assembly for tab widgets."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PySide6.QtWidgets import QStackedWidget, QWidget

from tabs.use_cases import capability_routing

if TYPE_CHECKING:
    from tabs.contract import TabContext, TabContract
    from tabs.registry import TabRegistry

logger = logging.getLogger("ImproveImgSLI")


def install_pages(
    registry: "TabRegistry", stack: QStackedWidget, context: "TabContext"
) -> None:
    """Register tab types without creating pages (lazy initialization).

    Pages are created on-demand when a tab is first shown via
    ``activate()`` → ``_ensure_page()``.  This avoids building 30+
    widgets for tabs the user may never visit.
    """
    registry._context = context
    registry._stack = stack
    capability_routing.contribute_all_settings(registry)
    capability_routing.contribute_all_help(registry)
    for session_type, tab in registry._tabs.items():
        if session_type not in registry._pages:
            registry._pending_pages[session_type] = tab


def _ensure_page(registry: "TabRegistry", session_type: str) -> QWidget | None:
    """Create and assemble the page for *session_type* if not yet done.

    Returns the page widget (or ``None`` if the tab is unknown).
    """
    if session_type in registry._pages:
        return registry._pages[session_type]
    tab = registry._pending_pages.pop(session_type, None) or registry._tabs.get(
        session_type
    )
    if tab is None:
        return None
    return _create_and_assemble_page(registry, session_type, tab)


def _create_and_assemble_page(
    registry: "TabRegistry", session_type: str, tab: "TabContract"
) -> QWidget | None:
    """Create a page widget, add it to the stack, and assemble host pieces."""
    stack = getattr(registry, "_stack", None)
    if stack is None or registry._context is None:
        return None
    try:
        page = tab.create_page(stack, registry._context)
        stack.addWidget(page)
        registry._pages[session_type] = page
    except Exception as e:
        logger.error("Failed to create page for tab '%s': %s", session_type, e)
        return None
    try:
        ui = getattr(registry, "_ui", None)
        if ui is not None:
            tab.assemble_host_page(ui)
    except Exception:
        logger.exception("Tab host-page assembly failed for %s", session_type)
    try:
        ui = getattr(registry, "_ui", None)
        if ui is not None:
            tab.finalize_host_page(ui)
    except Exception:
        logger.exception("Tab host-page finalize failed for %s", session_type)
    capability_routing.contribute_settings_for(registry, session_type)
    capability_routing.contribute_all_help(registry)
    return page


def install_missing_pages(
    registry: "TabRegistry", stack: QStackedWidget
) -> tuple[str, ...]:
    """Register deferred tabs without creating pages (lazy init).

    Pages will be created on-demand when each tab is first shown.
    """
    if registry._context is None:
        raise RuntimeError("TabContext not set; call install_pages first")
    registry._stack = stack
    added: list[str] = []
    for session_type, tab in registry._tabs.items():
        if session_type in registry._pages or session_type in registry._pending_pages:
            continue
        registry._pending_pages[session_type] = tab
        added.append(session_type)
    return tuple(added)


def get_page(registry: "TabRegistry", session_type: str) -> QWidget | None:
    return registry._pages.get(session_type)


def assemble_host_pages(registry: "TabRegistry", ui: Any) -> None:
    """Let registered tabs assemble any legacy host-owned page pieces.

    Skips tabs whose pages haven't been created yet (lazy init — the
    page will be assembled when ``_ensure_page`` creates it).
    """
    registry._ui = ui
    for session_type, tab in registry._tabs.items():
        if session_type not in registry._pages:
            continue
        try:
            tab.assemble_host_page(ui)
        except Exception:
            logger.exception("Tab host-page assembly failed for %s", session_type)
            raise


def finalize_host_pages(registry: "TabRegistry", ui: Any) -> None:
    """Let registered tabs do one-time cosmetic setup on their own host-assembled chrome.

    Only the currently active tab's page is guaranteed to exist (created
    lazily by ``activate()``).  Other tabs are skipped — their
    ``finalize_host_page`` runs when they are first shown.
    """
    active_type = registry._active_session_type
    if active_type is None:
        return
    tab = registry._tabs.get(active_type)
    if tab is None:
        return
    try:
        tab.finalize_host_page(ui)
    except Exception:
        logger.exception("Tab host-page finalize failed for %s", active_type)
        raise


def apply_host_session_mode(
    registry: "TabRegistry",
    session_type: str,
    ui: Any,
    session_title: str | None = None,
) -> bool:
    tab = registry._tabs.get(session_type)
    if tab is None:
        return False
    try:
        return bool(tab.apply_host_session_mode(ui, session_title=session_title))
    except Exception:
        logger.exception("Tab host session-mode hook failed for %s", session_type)
        raise
