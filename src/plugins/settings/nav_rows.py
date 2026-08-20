"""Shared helper wiring settings pages into NavigationManager.

Every settings page is a stack of visually distinct "rows" (a radio group,
a combo, a checkbox, a slider...), same shape as the workspace toolbars that
already use ``ToolbarRowsSection`` (see the tab layer's own toolbar-row
wiring for that pattern). Row accumulation and wrapping now live in the
toolkit (``sli_ui_toolkit.managers.NavRowBuilder``/``as_nav_row``) — this
module only adds the settings-dialog-specific piece: wiring a page's
``NavRowBuilder`` output to the sidebar's Left/Right hand-off.
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavRowBuilder, WidgetDescriptor, register_navigation


def _ensure_sidebar_nav_section(dialog):
    """Register ``dialog.sidebar`` as an ``IconListNavSection`` once per
    dialog, wiring Right (from the sidebar) to re-enter whichever page is
    currently visible in ``dialog.pages_stack``.

    Idempotent: every settings page calls :func:`register_page_navigation`
    during ``__init__``, and each needs the *same* sidebar section instance
    to hand its own Left off to — so the first call builds it and caches it
    on ``dialog``, every later call reuses it.
    """
    existing = getattr(dialog, "_sidebar_nav_section", None)
    if existing is not None:
        return existing

    from core.navigation import NavigationManager
    from sli_ui_toolkit.managers import IconListNavSection

    def _focus_active_page() -> bool:
        current = dialog.pages_stack.currentWidget()
        if current is None:
            return False
        return NavigationManager.get_instance().focus_section_for_owner(current)

    section = IconListNavSection(dialog.sidebar, on_exit_right=_focus_active_page)
    dialog._sidebar_nav_section = section
    NavigationManager.get_instance().register(dialog.sidebar, section)
    return section


def page_nav_builder(dialog, *, tag: str) -> NavRowBuilder:
    """Return a fresh ``NavRowBuilder`` for one settings page.

    Also makes sure ``dialog``'s sidebar section exists (its Left hand-off
    is wired in at :func:`register_page_navigation`, once this builder's
    rows are final) — same idempotent caching :func:`_ensure_sidebar_nav_section`
    already provides.
    """
    _ensure_sidebar_nav_section(dialog)
    return NavRowBuilder(tag=tag)


def register_page_navigation(dialog, page: QWidget, builder: NavRowBuilder) -> None:
    """Build *builder* into a ``ToolbarRowsSection`` wired to the sidebar's
    Left hand-off, and register it for *page* via
    ``WidgetDescriptor.navigation`` (see ``docs/dev/NAVIGATION.md`` in the
    toolkit for the full contract this follows — arrow-key consumption on
    ``QApplication`` is owned exclusively by ``NavigationManager``, no
    page-local event filter may consume them instead).

    Left at the leftmost control of a row hands off to ``dialog.sidebar``
    (landing on whichever row is already selected there, not literally the
    first) — mirrored by the sidebar's own Right handing back to whichever
    page is currently visible, via ``_ensure_sidebar_nav_section``.
    """
    sidebar_section = _ensure_sidebar_nav_section(dialog)
    section = builder.build(on_exit_left=sidebar_section.focus_first)
    tag_attr = builder.tag.replace("-", "_")
    setattr(dialog, f"_{tag_attr}_nav_section", section)
    page.widget_descriptor = WidgetDescriptor(
        family=f"settings.page.{builder.tag}", navigation=section
    )
    register_navigation(page)
