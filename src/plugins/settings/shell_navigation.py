"""Keyboard navigation for the Settings dialog shell (search + action bar).

Each settings *page* registers its own row section (``nav_rows.py``) and the
sidebar list registers an ``IconListNavSection``.  Two shell regions were
owned by no section, so arrows pressed on them did nothing and the controls
had no keyboard entry:

* the **search field** — in the sidebar header host, above the sidebar list;
* the **action bar** (OK / Cancel) — below the content pages.

The shell registers one small row section per region.  Registration order is
the order ``NavigationManager`` walks sections along (its neighbour hand-off
on an Up/Down edge), so the search section is registered before the pages and
the action bar after them: Up from the first sidebar row lands on the search
field, Down from the last page row lands on OK/Cancel.

The dialog's CSD title bar (the Help-menu trigger) is owned by a
``TitleBarNavigationSection`` author: the toolkit ``CustomTitleBar`` keeps its
own Left/Right focus handling; this section only adds the Up/Down hand-off.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection


def register_title_bar_navigation(dialog) -> None:
    """Own the CSD title bar (idempotent)."""
    title_bar = getattr(dialog, "_csd_title_bar", None)
    if title_bar is None or getattr(dialog, "_title_bar_nav_section", None) is not None:
        return
    from ui.main_window.title_bar_navigation import TitleBarNavigationSection

    section = TitleBarNavigationSection(title_bar)
    dialog._title_bar_nav_section = section
    NavigationManager.get_instance().register(title_bar, section)


def register_search_navigation(dialog) -> None:
    """Own the search field (idempotent). Registered before the pages."""
    host = getattr(dialog, "search_header_host", None)
    if host is None or getattr(dialog, "_search_nav_section", None) is not None:
        return
    section = ToolbarRowsSection(lambda: [host], tag="settings-search")
    dialog._search_nav_section = section
    NavigationManager.get_instance().register(host, section)


def register_action_bar_navigation(dialog) -> None:
    """Own the OK/Cancel action bar (idempotent). Registered after the pages."""
    bar = getattr(dialog, "action_bar", None)
    if bar is None or getattr(dialog, "_action_bar_nav_section", None) is not None:
        return
    section = ToolbarRowsSection(lambda: [bar], tag="settings-actions")
    dialog._action_bar_nav_section = section
    NavigationManager.get_instance().register(bar, section)
