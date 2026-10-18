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
settings form rows, the export tab bar, the *active* export tab's field rows
(a vertical form: one row per field, so ``↑``/``↓`` step field by field and
the set changes with the tab), the export button, the transport toolbar, the
timeline scroll area — registered when the dialog is shown and dropped when
it closes.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import NavigationManager, ToolbarRowsSection
from sli_ui_toolkit.ui.managers.nav_graph import focus_reason

_ARROWS = (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Left, Qt.Key.Key_Right)
# Activation keys for the export tab bar (Enter/Space): Enter also gets the
# numeric-pad flavour. The export bar follows the workspace-strip idiom: ←/→
# move a keyboard cursor WITHOUT switching the page (see ``VideoEditorTabBar``
# in dialog/tab_cursor.py), and these keys activate the cursor's tab.
_TAB_ACTIVATE_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space)


class TabBarKeyClaim(QObject):
    """Claim the export bar's activation keys at the ``ShortcutOverride`` stage.

    The dialog-level Space play shortcut is resolved by Qt *before* the
    app-wide ``NavigationManager`` filter sees the ``KeyPress`` (the manager
    only receives Focus/KeyPress/MousePress, not ShortcutOverride), so the
    section's ``extra_keys`` alone cannot stop the shortcut from firing on the
    focused bar. A widget that handles a key bound to a shortcut must accept
    the override — the tab bar does handle these keys (Enter/Space confirm the
    current page), so it claims them here; the real ``KeyPress`` is then
    delivered normally and the nav section consumes it.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: ANN001
        if (
            event.type() == QEvent.Type.ShortcutOverride
            and event.key() in _TAB_ACTIVATE_KEYS
        ):
            event.accept()
            return True
        return False


def claim_tab_bar_keys(tab_bar) -> None:
    """Install the ShortcutOverride claim on *tab_bar* (idempotent)."""
    if getattr(tab_bar, "_video_editor_key_claim", None) is None:
        claim = TabBarKeyClaim()
        tab_bar._video_editor_key_claim = claim  # type: ignore[attr-defined]
        tab_bar.installEventFilter(claim)


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

    @property
    def extra_keys(self) -> frozenset[int]:
        # Left/Right from the base row section (move within a row) plus the
        # tab-bar activation keys: the export bar has no focusable child of
        # its own, so the section must opt into Enter/Space to consume them
        # before the dialog-level Space play shortcut can fire (see
        # ``navigate``); for every other row the keys are declined and the
        # press falls through to native handling, unchanged.
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right, *_TAB_ACTIVATE_KEYS})

    def _move_cursor(self, step: int) -> bool:
        """Move the export bar's keyboard cursor (no page change). Consumed at
        the edge too, so ``←``/``→`` never fall through to a native handler."""
        return self._dialog.tabs.tab_bar.move_cursor(step)

    def navigate(self, key: int, widget: QWidget) -> bool:  # noqa: ANN001
        bar = self._dialog.tabs.tab_bar
        if widget is bar:
            if key in _TAB_ACTIVATE_KEYS:
                # Enter/Space activate the cursor's tab (the workspace-strip
                # idiom). Consume so nothing leaks to the window.
                return bar.activate_cursor()
            if key == Qt.Key.Key_Left:
                return self._move_cursor(-1)
            if key == Qt.Key.Key_Right:
                return self._move_cursor(+1)
            # Up/Down leave the bar — the inherited row walk.
            return super().navigate(key, widget)
        if key in _ARROWS and not super().owns(widget):
            # Focus rests on the bare dialog itself (a line edit's Enter
            # cleared it into the window): re-enter the body on any arrow —
            # the modal edge would otherwise consume the press dead.
            return self.focus_first(reason=focus_reason())
        if super().navigate(key, widget):
            return True
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # The export bar is a row with no StrongFocus child, so the
            # inherited walk (``_focusable`` finds nothing in it) cannot land
            # focus on it. Focus the bar itself when it is the neighbour in
            # the pressed direction.
            rows = self._rows()
            row = self._row_of(widget)
            if row is not None:
                index = rows.index(row)
                target = index + (1 if key == Qt.Key.Key_Down else -1)
                if 0 <= target < len(rows) and rows[target] is bar:
                    bar.setFocus(focus_reason())
                    return True
        return False


def _nav_rows(dialog) -> list[QWidget]:
    """The dialog's nav rows in visual top→bottom order.

    Dynamic: the export tab bar is one row, and the *active* export tab's
    field rows follow it (the pages are vertical forms — see the per-tab
    ``create_*_tab`` builders in ``sections.py``). Changing the tab therefore
    changes the traversable rows.
    """
    rows = [dialog.res_row, dialog.fps_row, dialog.preview_row, dialog.tabs.tab_bar]
    tab_rows = getattr(dialog, "export_tab_rows", None) or []
    index = dialog.tabs.currentIndex()
    if 0 <= index < len(tab_rows):
        rows.extend(tab_rows[index])
    rows.extend([dialog.export_row, dialog.toolbar_frame, dialog.scroll_area])
    return rows


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
