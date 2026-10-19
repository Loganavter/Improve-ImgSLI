"""ColorPickerDialog keyboard navigation (sv-button-ux).

- ``Enter`` on a colour-carrying control opens the picker (``ColorSwatch`` —
  the in-scope widget that owns a ``QColor``; no ``ScrollValueButton``
  consumer carries one, see DONE.md);
- the picker registers a row section (``declare_navigation_rows``) over its
  four interactive rows — picker (SV/hue/alpha), value fields, recent-colour
  chips and action buttons, in visual top→bottom order;
- ``Enter``/``Space`` activate a chip, ``Enter`` activates the action button;
- ``Esc`` closes the picker and returns focus to the opener.

Falsification (recorded in DONE.md): without the ``declare_navigation_rows``
call the picker has no section — ``focus_section_for_owner`` returns False and
``test_picker_arrows_traverse_rows_in_visual_order`` is red.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QRect, QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager
from tests.helpers.drain_until_stable import drain_until_stable
from ui.widgets.color import ColorPickerDialog, ColorSwatch, RecentColorsStore


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def settings(tmp_path):
    return QSettings(os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat)


@pytest.fixture
def store(settings):
    return RecentColorsStore(settings)


@pytest.fixture
def host(qtbot):
    """A top-level window so the picker's Qt.Dialog parent is realistic."""

    widget = QWidget()
    widget.resize(320, 200)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    yield widget


def _kbd_focus(widget: QWidget) -> None:
    """Grant keyboard (arrow-style) focus: modality comes from the last input
    device, not the FocusReason (guide §7)."""
    widget.clearFocus()
    QTest.keyClick(widget, Qt.Key.Key_F1)
    widget.setFocus(Qt.FocusReason.OtherFocusReason)


def _show(dialog: ColorPickerDialog, qapp) -> None:
    dialog.show()
    drain_until_stable(
        qapp,
        lambda: (dialog.width(), dialog.height(), dialog._hex_edit.x()),
        timeout_ms=800,
        poll_ms=10,
        stable_frames=2,
    )


def _make_dialog(qapp, store, host, colors=("#FF8800", "#224466")):
    for code in reversed(list(colors)):
        store.add(code)
    dialog = ColorPickerDialog(QColor("#101010"), host, recents_store=store)
    _show(dialog, qapp)
    return dialog


def _section(dialog):
    """The navigation section the picker registered (live registry)."""
    manager = NavigationManager.get_instance()
    for owner, spec in list(manager._sections):
        if owner is dialog:
            return spec
    raise AssertionError("the picker registered no navigation section")


def _declared_rows(dialog) -> list[QWidget]:
    """The four band containers the picker must declare, visual top→bottom.

    The value-fields band has no container by default (it is a bare
    ``QHBoxLayout``); a section cannot own a bare layout, so the fix wraps it
    in ``_fields_container``. Failing here pre-fix is the red signal that the
    fields band was unreachable.
    """
    fields = getattr(dialog, "_fields_container", None)
    assert fields is not None, (
        "the value-fields band must be its own widget to be a declared "
        "navigation row (a bare QHBoxLayout cannot be owned by a section)"
    )
    return [
        dialog._picker_container,
        fields,
        dialog._recents_row,
        dialog._actions_container,
    ]


def _global_center(widget: QWidget):
    return widget.mapToGlobal(widget.rect().center())


def _global_rect(widget: QWidget):
    return QRect(widget.mapToGlobal(widget.rect().topLeft()), widget.size())


def test_enter_on_color_swatch_opens_picker(host, qapp):
    """ColorSwatch is the colour-carrying control: Enter opens the picker."""
    layout = QVBoxLayout(host)
    swatch = ColorSwatch(QColor("#FF8800"), parent=host)
    layout.addWidget(swatch)
    qapp.processEvents()

    _kbd_focus(swatch)
    assert swatch.hasFocus()

    QTest.keyClick(swatch, Qt.Key.Key_Return)
    qapp.processEvents()

    dialog = swatch._dialog
    assert dialog is not None and dialog.isVisible(), "Enter must open the picker"
    dialog.reject()


def test_escape_closes_picker_and_returns_focus_to_opener(host, qapp):
    layout = QVBoxLayout(host)
    swatch = ColorSwatch(QColor("#FF8800"), parent=host)
    other = ColorSwatch(QColor("#224466"), parent=host)
    layout.addWidget(swatch)
    layout.addWidget(other)
    qapp.processEvents()

    _kbd_focus(swatch)
    QTest.keyClick(swatch, Qt.Key.Key_Return)
    qapp.processEvents()
    dialog = swatch._dialog
    assert dialog is not None and dialog.isVisible()

    # Move the host window's focus widget off the opener first, so the
    # post-Esc assertion is a real observation (offscreen never re-activates
    # the parent, so focusWidget() -- not hasFocus() -- is the observable).
    other.setFocus(Qt.FocusReason.OtherFocusReason)
    assert host.focusWidget() is other

    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    qapp.processEvents()

    assert not dialog.isVisible(), "Esc must close the picker"
    assert swatch._dialog is None
    assert host.focusWidget() is swatch, "focus must return to the opener"


def test_picker_chip_is_keyboard_reachable_and_activates(qapp, store, host):
    dialog = _make_dialog(qapp, store, host)
    try:
        chip = dialog._recents_row._chip_widgets[0]
        assert chip.focusPolicy() == Qt.FocusPolicy.StrongFocus, (
            "a NoFocus chip is invisible to the picker's row section"
        )
        chip.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()

        QTest.keyClick(chip, Qt.Key.Key_Return)
        assert dialog.color() == QColor(chip._color), (
            "Enter on a chip applies that colour without accepting"
        )
        assert dialog.result() != dialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()


def test_picker_arrows_traverse_rows_in_visual_order(qapp, store, host):
    dialog = _make_dialog(qapp, store, host)
    try:
        manager = NavigationManager.get_instance()
        assert manager.focus_section_for_owner(dialog) is True, (
            "the picker must register its row section"
        )
        # Row order top→bottom: picker (SV/hue/alpha), value fields,
        # recent-colour chips, action buttons. Entry lands on the first
        # focusable of the topmost row — the hue slider (the SV square is
        # deliberately NoFocus).
        assert QApplication.focusWidget() is dialog._hue_slider

        # The sliders own Left/Right for value adjustment (the toolkit's
        # ``_widget_handles`` trial-dispatch); Down is the row walk.
        QTest.keyClick(dialog._hue_slider, Qt.Key.Key_Down)
        assert QApplication.focusWidget() in (
            dialog._hex_edit,
            dialog._format_btn,
            dialog._r_spin,
            dialog._g_spin,
            dialog._b_spin,
            dialog._a_spin,
        ), "Down leaves the picker row for the value-fields row"

        first_chip = dialog._recents_row._chip_widgets[0]
        first_chip.setFocus(Qt.FocusReason.OtherFocusReason)
        QTest.keyClick(first_chip, Qt.Key.Key_Right)
        assert QApplication.focusWidget() is dialog._recents_row._chip_widgets[1], (
            "Left/Right move within the chips row"
        )

        QTest.keyClick(dialog._recents_row._chip_widgets[1], Qt.Key.Key_Down)
        assert QApplication.focusWidget() in (
            dialog._cancel_btn,
            dialog._ok_btn,
        ), "Down leaves the chips row for the actions row"

        QTest.keyClick(dialog._cancel_btn, Qt.Key.Key_Up)
        assert QApplication.focusWidget() in dialog._recents_row._chip_widgets, (
            "Up returns to the chips row"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_picker_action_button_activates_on_enter(qapp, store, host):
    dialog = _make_dialog(qapp, store, host)
    try:
        dialog._ok_btn.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        QTest.keyClick(dialog._ok_btn, Qt.Key.Key_Return)
        qapp.processEvents()
        assert dialog.result() == dialog.DialogCode.Accepted
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


# ---------------------------------------------------------------------------
# Declared-row contract + visual-order walk
# (plan-nav-coverage-2026-10-19 — the live walk stayed on the bare dialog)
# ---------------------------------------------------------------------------


def test_picker_declares_four_rows_and_owns_only_them(qapp, store, host):
    """The picker's section is a declared-row section over four containers.

    Ownership must be *exact*: the zero-config ``AutoNavigationSection``
    claimed every descendant (its ``owns`` falls back to ``owner.isAncestorOf``
    and its rows are y-clustered), which made the previous wave's "every
    control is owned" assertion vacuously true while the live walk moved
    nowhere. A focusable control dropped straight into the dialog, outside
    every declared row, must therefore NOT be owned.
    """
    from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection

    dialog = _make_dialog(qapp, store, host)
    try:
        spec = _section(dialog)
        assert isinstance(spec, ToolbarRowsSection), (
            "the picker must use a declared-row section, not the y-clustering "
            f"auto section (got {type(spec).__name__})"
        )

        stray = QWidget(dialog)
        stray.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        stray.show()
        qapp.processEvents()
        assert not spec.owns(stray), (
            "a focusable control outside every declared row must not be owned "
            "— the auto section's ancestor-fallback claimed it (vacuous "
            "ownership)"
        )
        stray.deleteLater()

        rows = _declared_rows(dialog)
        assert spec._rows() == [row for row in rows if row.isVisible()], (
            "the declared rows must be exactly the four band containers, in "
            "visual top→bottom order"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_picker_every_control_is_owned_through_a_declared_row(qapp, store, host):
    """Every interactive control lives inside one of the four declared rows.

    Stronger than "some section owns it": a control is only reachable if a
    *declared row* is its ancestor (``_row_of`` walks the row containers).
    """
    dialog = _make_dialog(qapp, store, host)
    try:
        spec = _section(dialog)
        rows = _declared_rows(dialog)
        orphans: list[tuple[str, str]] = []
        outside_rows: list[tuple[str, str]] = []
        for widget in dialog.findChildren(QWidget):
            if widget is dialog or widget.focusPolicy() == Qt.FocusPolicy.NoFocus:
                continue
            if not (widget.isVisible() and widget.isEnabled()):
                continue
            if not spec.owns(widget):
                orphans.append((type(widget).__name__, widget.objectName()))
            if not any(row is widget or row.isAncestorOf(widget) for row in rows):
                outside_rows.append((type(widget).__name__, widget.objectName()))
        assert not orphans, f"unowned interactive controls: {orphans}"
        assert not outside_rows, (
            f"interactive controls outside the four declared rows: {outside_rows}"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_picker_down_walk_visits_rows_in_visual_y_order(qapp, store, host):
    """Down from the bare dialog reaches every row, top→bottom, and settles.

    This is the live symptom: focus rested on the dialog itself and Down did
    nothing. Entry is the manager's owner-bootstrap (``focused is owner`` →
    ``focus_first``); every subsequent hop must stay owned and move down the
    declared rows, never resting back on the dialog.
    """
    dialog = _make_dialog(qapp, store, host)
    try:
        spec = _section(dialog)
        rows = _declared_rows(dialog)
        visible_rows = [row for row in rows if row.isVisible()]

        dialog.clearFocus()
        dialog.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        assert QApplication.focusWidget() is dialog

        visited: list[tuple[QWidget, QWidget]] = []
        current: QWidget = dialog
        for _ in range(16):
            QTest.keyClick(current, Qt.Key.Key_Down)
            qapp.processEvents()
            nxt = QApplication.focusWidget()
            assert nxt is not dialog, (
                "Down must not leave focus on the bare dialog (the live dead-end)"
            )
            assert spec.owns(nxt), (
                f"Down landed on an unowned control {type(nxt).__name__}"
            )
            row = next(r for r in visible_rows if r is nxt or r.isAncestorOf(nxt))
            visited.append((row, nxt))
            if nxt is current:
                break
            current = nxt

        sequence = [
            (type(widget).__name__, _global_rect(widget).getRect())
            for _row, widget in visited
        ]
        print(f"\nPICKER DOWN SEQUENCE (class, (x, y, w, h)): {sequence}")

        # Rows are entered in visual top→bottom order, and all are reached.
        encountered: list[QWidget] = []
        for row, _widget in visited:
            if not encountered or encountered[-1] is not row:
                encountered.append(row)
        assert encountered == visible_rows, (
            f"Down must visit rows top→bottom: got "
            f"{[type(r).__name__ for r in encountered]}"
        )
        # …and the control's global y never decreases on the way down.
        ys = [_global_center(widget).y() for _row, widget in visited]
        assert ys == sorted(ys), f"Down walked against y order: {ys}"
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_picker_up_walk_returns_up_the_rows(qapp, store, host):
    dialog = _make_dialog(qapp, store, host)
    try:
        spec = _section(dialog)
        _declared_rows(dialog)

        dialog._ok_btn.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        start_y = _global_center(dialog._ok_btn).y()

        visited = []
        current = dialog._ok_btn
        for _ in range(4):
            QTest.keyClick(current, Qt.Key.Key_Up)
            qapp.processEvents()
            nxt = QApplication.focusWidget()
            assert spec.owns(nxt), f"Up landed on an unowned control {type(nxt).__name__}"
            visited.append(nxt)
            if nxt is current:
                break
            current = nxt

        sequence = [
            (type(w).__name__, _global_rect(w).getRect()) for w in visited
        ]
        print(f"\nPICKER UP SEQUENCE (class, (x, y, w, h)): {sequence}")
        ys = [start_y] + [_global_center(w).y() for w in visited]
        assert ys == sorted(ys, reverse=True), f"Up walked against y order: {ys}"
        # The picker row (top) is reachable upward from the actions row.
        assert any(
            dialog._picker_container.isAncestorOf(w) for w in visited
        ), "Up from the actions row must reach the picker row"
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_picker_recents_row_moves_left_right_within_one_visual_row(qapp, store, host):
    dialog = _make_dialog(qapp, store, host)
    try:
        chips = dialog._recents_row._chip_widgets
        assert len(chips) >= 2, "need at least two recents for a row move"
        chip0, chip1 = chips[0], chips[1]
        assert _global_center(chip0).y() == _global_center(chip1).y(), (
            "the first two chips must sit on the same visual line"
        )

        chip0.setFocus(Qt.FocusReason.OtherFocusReason)
        qapp.processEvents()
        QTest.keyClick(chip0, Qt.Key.Key_Right)
        qapp.processEvents()
        assert QApplication.focusWidget() is chip1, (
            "Right must step to the next chip in the same row"
        )
        assert _global_center(chip1).y() == _global_center(chip0).y(), (
            "Right must not change the visual row"
        )

        QTest.keyClick(chip1, Qt.Key.Key_Left)
        qapp.processEvents()
        assert QApplication.focusWidget() is chip0, (
            "Left must step back to the previous chip in the same row"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()

