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


def register_page_nav_rows(dialog, page: QWidget, rows: list[QWidget], *, tag: str) -> None:
    """Register *rows* (in visual top-to-bottom order) as one
    ``ToolbarRowsSection`` for *page*, so Up/Down/Left/Right arrow-key
    navigation works the same way it already does on the main window's
    workspace toolbars (see ``core/navigation.py``'s ``NavigationManager``
    contract: it owns arrow-key consumption on ``QApplication`` exclusively
    — no page-local event filter may consume them instead).
    """
    from core.navigation import NavigationManager
    from sli_ui_toolkit.managers import ToolbarRowsSection

    section = ToolbarRowsSection(lambda: list(rows), tag=tag)
    setattr(dialog, f"_{tag.replace('-', '_')}_nav_section", section)
    NavigationManager.get_instance().register(page, section)
