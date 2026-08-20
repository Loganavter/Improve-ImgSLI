"""Shared helper wiring settings pages into NavigationManager.

Every settings page is a stack of visually distinct "rows" (a radio group,
a combo, a checkbox, a slider...), same shape as the workspace toolbars that
already use ``ToolbarRowsSection`` (see the tab layer's own toolbar-row
wiring for that pattern). A row needs to be an actual ``QWidget`` —
``ToolbarRowsSection._focusable``
looks at a row's *descendants*, never the row widget itself — so a
standalone control (a lone ``CheckBox``, a ``QHBoxLayout`` built with no
parent widget) has to be wrapped before it can serve as one.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLayout, QVBoxLayout, QWidget


def as_nav_row(item: QWidget | QLayout) -> QWidget:
    """Wrap *item* (a widget or an unparented layout) in a thin row widget.

    A bare widget becomes the sole child of a zero-margin ``QVBoxLayout``;
    a bare layout is adopted directly by a new ``QWidget`` — either way the
    result is a container ``ToolbarRowsSection`` can treat as one row.
    """
    if isinstance(item, QWidget):
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(item)
        return row
    row = QWidget()
    row.setLayout(item)
    return row


def _ensure_sidebar_nav_section(dialog):
    """Register ``dialog.sidebar`` as an ``IconListNavSection`` once per
    dialog, wiring Right (from the sidebar) to re-enter whichever page is
    currently visible in ``dialog.pages_stack``.

    Idempotent: every settings page calls :func:`register_page_nav_rows`
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


def register_page_nav_rows(dialog, page: QWidget, rows: list[QWidget], *, tag: str) -> None:
    """Register *rows* (in visual top-to-bottom order) as one
    ``ToolbarRowsSection`` for *page*, so Up/Down/Left/Right arrow-key
    navigation works the same way it already does on the main window's
    workspace toolbars (see ``core/navigation.py``'s ``NavigationManager``
    contract: it owns arrow-key consumption on ``QApplication`` exclusively
    — no page-local event filter may consume them instead).

    Left at the leftmost control of a row hands off to ``dialog.sidebar``
    (landing on whichever row is already selected there, not literally the
    first) — mirrored by the sidebar's own Right handing back to whichever
    page is currently visible, via ``_ensure_sidebar_nav_section``.
    """
    from core.navigation import NavigationManager
    from sli_ui_toolkit.managers import ToolbarRowsSection

    sidebar_section = _ensure_sidebar_nav_section(dialog)

    section = ToolbarRowsSection(
        lambda: list(rows),
        tag=tag,
        on_exit_left=sidebar_section.focus_first,
    )
    setattr(dialog, f"_{tag.replace('-', '_')}_nav_section", section)
    NavigationManager.get_instance().register(page, section)
