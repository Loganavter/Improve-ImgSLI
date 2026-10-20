"""Dialog row navigation: one section over a dialog's declared controls.

Split from :mod:`shared_toolkit.ui.decorate_dialog` (file-size policy: CSD
decoration and row navigation are orthogonal concerns). The public entry point
is :func:`register_dialog_auto_navigation`, re-exported by ``decorate_dialog``
next to ``register_dialog_title_bar_navigation``.

``rows`` is read live: a sequence of visual rows (top→bottom), each row either
a single control or a sequence of controls (left→right). Down/Up cross rows
(landing on the control horizontally closest to the one that had focus),
Left/Right step inside the current row — during a text field they stay the
field's until the caret reaches the edge — and at a row edge they are consumed
so focus never wraps into a neighbouring row (Up/Down own that axis).
Return/Enter are deliberately not claimed: the focused toolkit control
activates itself.

Ownership is exact (the listed controls, their descendants, and the dialog
itself so an arrow pressed while the bare dialog holds focus bootstraps into
the first row). Declared rows must never swallow the title-bar section's
widgets — the bar registers its own section above this one.

``modal`` is a live read of ``QDialog.isModal()``: a dialog opened with
``exec()`` becomes the manager's modal ceiling, while the same class shown
non-modally (``open_non_modal_message``) keeps the host navigable.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

__all__ = ["DialogRowsNavigationSection", "register_dialog_auto_navigation"]

ROWS_NAV_SECTION_ATTR = "_rows_nav_section"


class DialogRowsNavigationSection:
    """Section over a dialog's declared controls, in visual order."""

    def __init__(self, dialog: QWidget, rows, *, tag: str = "dialog-rows") -> None:
        self._dialog = dialog
        self._rows_provider = rows if callable(rows) else (lambda: rows)
        self._tag = tag

    @property
    def modal(self) -> bool:
        try:
            return bool(self._dialog.isModal())
        except (AttributeError, RuntimeError):
            # Onboarding-style overlay: a QWidget, not a QDialog — it covers
            # its own startup stack, not the whole application.
            return False

    @property
    def extra_keys(self) -> frozenset[int]:
        return frozenset({Qt.Key.Key_Left, Qt.Key.Key_Right})

    # -- rows -------------------------------------------------------------

    def _declared(self) -> list[tuple[QWidget, ...]]:
        """Every declared widget, including NoFocus click-only controls."""
        out: list[tuple[QWidget, ...]] = []
        for row in self._rows_provider():
            widgets = (row,) if isinstance(row, QWidget) else tuple(row)
            live = tuple(w for w in widgets if _widget_is_live(w, focusable=False))
            if live:
                out.append(live)
        return out

    def _rows(self) -> list[list[QWidget]]:
        """Rows the walk may land on: visible, enabled and focus-capable."""
        return [
            [w for w in row if _widget_is_live(w)]
            for row in self._declared()
        ]

    @staticmethod
    def _locate(rows: list[list[QWidget]], widget: QWidget):
        for index, row in enumerate(rows):
            if widget in row or any(w.isAncestorOf(widget) for w in row):
                return index, row
        return None

    def owns(self, widget: QWidget) -> bool:
        try:
            if widget is self._dialog:
                return True
        except RuntimeError:
            return False
        # Claim descendants too: a composite control (the report TextView owns
        # its scroll viewport's TextCanvas) is ONE stop, not a second control
        # outside the row. Nothing here lists the title bar, so the bar's own
        # section keeps its widgets.
        for row in self._declared():
            for control in row:
                try:
                    if widget is control or control.isAncestorOf(widget):
                        return True
                except RuntimeError:
                    continue
        return False

    # -- navigation -------------------------------------------------------

    def navigate(self, key: int, widget: QWidget) -> bool:
        reason = _navigation_focus_reason()
        rows = self._rows()
        if not rows:
            return False

        located = self._locate(rows, widget)
        if located is None:
            # Bootstrap from the bare dialog: Down enters at the top, Up at
            # the bottom. Left/Right are not row-axis keys — they stay native
            # (never a Down→Right / Up→Left remap, see the arrow contract).
            if key == Qt.Key.Key_Down:
                return self.focus_first(reason=reason)
            if key == Qt.Key.Key_Up:
                return self.focus_last(reason=reason)
            return False

        index, row = located
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            target = index + (1 if key == Qt.Key.Key_Down else -1)
            if not 0 <= target < len(rows):
                # Yield at the dialog's edge so the manager can hand off to
                # the title-bar section registered above (Down from the bar
                # re-enters here through its own fallback).
                return False
            return self._focus_near(rows[target], widget, reason)

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if _widget_handles_key(key, widget):
                # Caret move inside a field — but at the edge (no selection)
                # the row must be able to take the key, or focus is trapped.
                if not _caret_at_boundary(key, widget):
                    return True
            if widget not in row:
                return False
            column = row.index(widget) + (1 if key == Qt.Key.Key_Right else -1)
            if 0 <= column < len(row):
                row[column].setFocus(reason)
                return True
            # Row edge: consume, like the toolkit row section — Up/Down own
            # the row axis, Left/Right must not wrap into an adjacent row.
            return True

        return False

    def focus_first(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        return self._focus_in(rows[0], ref_x, reason)

    def focus_last(self, ref_x: float | None = None, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False
        return self._focus_in(rows[-1], ref_x, reason)

    def focus_nearest(self, pos, *, reason: Qt.FocusReason) -> bool:
        rows = self._rows()
        if not rows:
            return False

        def _row_y(row: list[QWidget]) -> float:
            return _widget_center(row[0]).y()

        row = min(rows, key=lambda candidate: abs(_row_y(candidate) - pos.y()))
        return self._focus_in(row, pos.x(), reason)

    @staticmethod
    def _focus_near(
        row: list[QWidget], reference: QWidget, reason: Qt.FocusReason
    ) -> bool:
        return DialogRowsNavigationSection._focus_in(
            row, _widget_center(reference).x(), reason
        )

    @staticmethod
    def _focus_in(
        row: list[QWidget], ref_x: float | None, reason: Qt.FocusReason
    ) -> bool:
        if not row:
            return False
        if ref_x is None:
            target = row[0]
        else:
            target = min(
                row, key=lambda w: abs(_widget_center(w).x() - ref_x)
            )
        target.setFocus(reason)
        return True


def register_dialog_auto_navigation(
    dialog: QWidget, rows, *, tag: str = "dialog-rows"
) -> DialogRowsNavigationSection | None:
    """Own a dialog's controls as one keyboard-navigation section (idempotent).

    Call after ``decorate_dialog`` and AFTER
    ``register_dialog_title_bar_navigation`` so the title bar stays the
    topmost section: Down from the bar enters this section's first row, Up
    from the first row yields back to the bar.

    ``rows`` is a sequence of visual rows (top→bottom); each row is one
    control or a sequence of controls (left→right), or a callable returning
    that sequence (live re-read, for a dialog that rebuilds its controls).
    ``None`` entries and hidden/disabled controls are skipped at walk time, so
    optional buttons (Cancel, "…and don't ask again") need no branching at the
    call site. Returns the registered section.
    """
    section = getattr(dialog, ROWS_NAV_SECTION_ATTR, None)
    if section is None:
        section = DialogRowsNavigationSection(dialog, rows, tag=tag)
        dialog._rows_nav_section = section  # type: ignore[attr-defined]  # dynamic attr
    else:
        section._rows_provider = rows if callable(rows) else (lambda: rows)
    try:
        from sli_ui_toolkit.managers import NavigationManager

        NavigationManager.get_instance().register(dialog, section)
    except Exception:
        return section
    return section


def _widget_is_live(widget: QWidget, *, focusable: bool = True) -> bool:
    try:
        if not widget.isVisible() or not widget.isEnabled():
            return False
        return not focusable or widget.focusPolicy() != Qt.FocusPolicy.NoFocus
    except (RuntimeError, TypeError):
        return False


def _widget_center(widget: QWidget):
    return widget.mapToGlobal(widget.rect().center())


def _navigation_focus_reason() -> Qt.FocusReason:
    from sli_ui_toolkit.managers import NavigationManager

    return NavigationManager.get_instance().current_focus_reason()


def _widget_handles_key(key: int, widget: QWidget) -> bool:
    """First refusal for value controls (text caret, sliders, spinners).

    Same trial dispatch the toolkit row sections use: NavigationManager always
    consumes arrows for a widget a section owns, so the control's own
    ``keyPressEvent`` would otherwise never see Left/Right. Only the toolkit's
    generic arbitration is reused here — no second keyboard mechanism.
    """
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection

    return ToolbarRowsSection._widget_handles(key, widget)


def _caret_at_boundary(key: int, widget: QWidget) -> bool:
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection

    return ToolbarRowsSection._caret_at_boundary(key, widget)
