"""Hover-tooltip lifecycle for RatingListItem.

Functions take the owning ``RatingListItem`` as their first argument (see
docs/dev/CODE_PATTERNS.md's "thin owner + use_cases/ module" pattern).
"""

from PySide6.QtGui import QCursor

from sli_ui_toolkit.ui.widgets.atomic.tooltips import PathTooltip


def enter_event(widget) -> None:
    if widget.full_path:
        widget.tooltip_timer.start()


def leave_event(widget) -> None:
    widget.tooltip_timer.stop()
    PathTooltip.get_instance().hide_tooltip()


def show_tooltip(widget) -> None:
    if widget.full_path:
        PathTooltip.get_instance().show_tooltip(QCursor.pos(), widget.full_path)
