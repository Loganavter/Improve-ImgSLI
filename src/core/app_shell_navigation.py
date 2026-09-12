"""Centralized app-shell navigation registration.

Registers the three fixed navigation sections (title bar, tab strip, session
picker) in the documented top-to-bottom order **once**, instead of spreading
three ``NavigationManager.register()`` calls across ``startup.py`` with
copy-pasted ordering comments at each site.

The ordering rationale (from ``plan_navigation_descriptor_unification.md``
§2.3 / §5):

1. **Title bar** — topmost; ``_neighbor(owner, -1)`` from the tab strip
   finds it when navigating Up.
2. **Tab strip** — below title bar; Down from title bar lands here; Up
   from session picker lands here.
3. **Session picker** — bottom; ``register LAST`` because ``_neighbor()``
   relies on registration order for vertical section traversal.

This module is the single source of truth for that order.  Future changes
to the app-shell hierarchy (e.g. adding a status bar) go here, not as
another comment-gated ``register()`` call in ``startup.py``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget

logger = logging.getLogger("ImproveImgSLI")


def register_app_shell_navigation(window: "QWidget") -> None:
    """Register title bar, tab strip, and session picker in order.

    Safe to call once; ``NavigationManager.register`` deduplicates.

    :param window: The main ``MainWindow`` instance (must have
        ``._custom_title_bar``, ``.ui.workspace_tabs``, and the session
        picker page already created by ``setupUi()``).
    """
    from sli_ui_toolkit.managers import NavigationManager

    nav_manager = NavigationManager.get_instance()

    # 1. CSD title bar — must be first (topmost) so that
    #    _neighbor(owner, -1) from the tab strip finds it.
    title_bar = getattr(window, "_custom_title_bar", None)
    if title_bar is not None:
        from ui.main_window.title_bar_navigation import TitleBarNavigationSection

        nav_manager.register(title_bar, TitleBarNavigationSection(title_bar))
        logger.debug("[nav-titlebar] registered title bar section")

    # 2. Workspace tab strip — second in visual hierarchy.
    tab_strip = getattr(window.ui, "workspace_tabs", None) if hasattr(window, "ui") else None
    if tab_strip is not None:
        from core.navigation_sections import TabStripSection

        nav_manager.register(tab_strip, TabStripSection(tab_strip))
        logger.debug("[nav-tabstrip] registered tab strip section")

    # 3. Session picker — register LAST (bottom of visual hierarchy).
    #    Must be after title_bar and tab_strip to preserve the top-to-bottom
    #    section ordering that _neighbor() relies on.
    from core.store import INITIAL_WORKSPACE_SESSION_TYPE
    from tabs.registry import TabRegistry

    _picker_page = TabRegistry().get_page(INITIAL_WORKSPACE_SESSION_TYPE)
    if _picker_page is not None:
        from core.navigation_sections import SessionPickerSection

        nav_manager.register(_picker_page, SessionPickerSection(_picker_page))
        logger.debug("[nav-picker] registered session picker section")
