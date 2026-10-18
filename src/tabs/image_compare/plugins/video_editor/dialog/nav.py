# Audit-Meta: pattern=qdialog-wiring reason="video editor dialog keyboard navigation — one modal section over the dialog rows"
"""Keyboard navigation for the video editor dialog.

The dialog is a top-level window (``Qt.WindowType.Window``; non-modal at the
Qt level — the main window behind stays deliberately usable), but while it is
open the keyboard must stay inside it. It therefore registers ONE modal
section over its rows: the NavigationManager treats a visible modal section
as the ceiling, so arrows, the row section's ``extra_keys`` (``←``/``→``) and
Tab/Backtab are routed into the dialog, and a declined arrow at an edge is
consumed instead of handing focus to the section registered behind it (the
workspace tab, in production).

Rows are the dialog's real containers in visual top→bottom order — the
settings form rows, the export button, the transport toolbar, the timeline
scroll area — registered when the dialog is shown and dropped when it closes.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

_ARROWS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right)


class VideoEditorNavSection(ToolbarRowsSection):
    """The dialog's rows as a toolkit row section, plus the modal wrap.

    Everything key-related is the inherited toolkit section's: it focuses a
    row's ``StrongFocus`` children (so the ring lands on the control, never
    on its container), steps ``←``/→ within a row, and crosses ``↑``/``↓``
    between rows. Row-edge behaviour is inherited too — ``ToolbarRowsSection``
    yields at the outer edges so the manager can consume there; wrapping the
ring inside the dialog (Quick Look's ``↑``→last / ``↓``→first) was
    considered and rejected: with seven rows a wrap is a disorienting jump,
    and the modal ceiling already guarantees the edge key is consumed.

    ``modal`` additionally makes the dialog the manager's ceiling while it is
    visible (read via ``getattr(spec, "modal", False)`` — must stay a
    **property**, never a method): no key or focus may leave for the window
    behind, and a foreign widget stealing focus inside the dialog window is
    pulled back.
    """

    def __init__(self, dialog) -> None:
        super().__init__(lambda: _nav_rows(dialog), tag="video-editor")
        self._dialog = dialog

    @property
    def modal(self) -> bool:
        return True

    def navigate(self, key: int, widget: QWidget) -> bool:  # noqa: ANN001
        if key in _ARROWS and not super().owns(widget):
            # Focus rests on the bare dialog itself (a line edit's Enter
            # cleared it into the window): re-enter the body on any arrow —
            # the modal edge would otherwise consume the press dead.
            return self.focus_first(reason=focus_reason())
        return super().navigate(key, widget)


def _nav_rows(dialog) -> list[QWidget]:
    """The dialog's nav rows in visual top→bottom order."""
    return [
        dialog.res_row,
        dialog.fps_row,
        dialog.preview_row,
        dialog.tabs,
        dialog.export_row,
        dialog.toolbar_frame,
        dialog.scroll_area,
    ]


def register_navigation(dialog) -> None:
    """Register the dialog's nav section (idempotent — the manager dedupes by owner)."""
    try:
        section = getattr(dialog, "_nav_section", None)
        if section is None:
            section = VideoEditorNavSection(dialog)
            dialog._nav_section = section  # type: ignore[attr-defined]
        NavigationManager.get_instance().register(dialog, section)
    except Exception:
        # Navigation is an enhancement — never let it break the dialog.
        pass


def unregister_navigation(dialog) -> None:
    """Drop the dialog's nav section (idempotent)."""
    try:
        NavigationManager.get_instance().unregister(dialog)
    except Exception:
        pass
