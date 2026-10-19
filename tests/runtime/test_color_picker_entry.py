"""ColorPickerDialog ENTRY: the opener's Down must move the keyboard INTO the picker.

Symptom (owner, live 2026-10-19): with the colour button focused and the
non-modal picker open, Down left the ring in the host toolbar. The picker's own
row section was registered and fully walkable once entered
(``test_color_picker_navigation.py``) — that half was never broken. What was
missing is the handoff: ``ToolbarRowsSection`` only enters a *linked*
continuation (``NavigationManager.extension_for(focused, "below")`` →
``extension.focus_first_child()``), so an opener with no link and a dialog with
no ``focus_first_child`` left Down declining on the toolbar's last row.

Falsification (run during this change, recorded): against the pre-change graph
— ``NavigationManager.link(opener, dialog, "below")`` removed and
``ColorPickerDialog.focus_first_child`` absent — all four tests here are red
(``4 failed, 16 passed`` for this file plus ``test_color_picker_navigation.py``):
``QTest.keyClick(opener, Down)`` leaves ``QApplication.focusWidget()`` on the
opener and the dialog's focus widget untouched. The same run keeps every
dialog-row test in ``test_color_picker_navigation.py`` green (16/16), which is
the proof the failure is the entry seam and not the rows.

Real widgets, a real host-window section graph and real ``QTest`` presses
throughout, so the app-wide ``NavigationManager`` filter decides — the same
idiom ``test_scroll_value_button_keyboard_flyout.py`` uses for the
anchor→pill handoff. No bespoke key filter exists on either side.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.managers import NavigationManager, declare_navigation_rows
from ui.widgets.color import ColorPickerDialog, ColorSwatch, RecentColorsStore


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def store(tmp_path):
    return RecentColorsStore(
        QSettings(os.path.join(str(tmp_path), "cfg.ini"), QSettings.Format.IniFormat)
    )


@pytest.fixture
def picker_host(qtbot):
    """A one-row 'toolbar' window hosting the real opener (``ColorSwatch``).

    The row container is the host's registered navigation row, exactly the
    graph a tab toolbar uses: Down from the swatch reaches the row's boundary
    and must then follow the linked extension into the picker.
    """

    host = QWidget()
    host.resize(420, 240)
    layout = QVBoxLayout(host)
    layout.addStretch(1)
    row = QWidget(host)
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 0, 0, 0)
    swatch = ColorSwatch(QColor("#FF8800"), parent=row)
    row_layout.addWidget(swatch)
    layout.addWidget(row)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    declare_navigation_rows(host, [row], tag="picker-entry-test")
    try:
        yield host, row, swatch
    finally:
        NavigationManager.get_instance().unregister(host)


def _kbd_focus(widget: QWidget) -> None:
    """Grant keyboard (arrow-style) focus: modality comes from the last input
    device, not the FocusReason (toolkit guide §7)."""
    widget.clearFocus()
    QTest.keyClick(widget, Qt.Key.Key_F1)
    widget.setFocus(Qt.FocusReason.OtherFocusReason)


def _open_picker(qapp, swatch: ColorSwatch) -> ColorPickerDialog:
    """Open the picker with the real product gesture (Enter on the swatch)."""
    QTest.keyClick(swatch, Qt.Key.Key_Return)
    qapp.processEvents()
    dialog = swatch._dialog
    assert dialog is not None and dialog.isVisible(), "Enter must open the picker"
    return dialog


def _host_takes_the_keyboard_back(qapp, host: QWidget, swatch: ColorSwatch) -> None:
    """Put the keyboard back in the host, where the live repro left it.

    Showing a non-modal dialog may activate it; the reported state is the host
    still holding the keyboard with the colour button focused, so the handoff
    is exercised from there (and the manager dispatches on the ACTIVE window's
    focus widget).
    """
    host.activateWindow()
    _kbd_focus(swatch)
    qapp.processEvents()
    assert QApplication.focusWidget() is swatch


def test_picker_is_linked_below_its_opener(qapp, picker_host, store):
    """The seam itself: opener → dialog registered on the ``"below"`` side.

    Falsification: without the ``link`` in the dialog the lookup is ``None``
    and every test below stays in the toolbar.
    """
    host, _row, swatch = picker_host
    _kbd_focus(swatch)
    dialog = _open_picker(qapp, swatch)
    try:
        manager = NavigationManager.get_instance()
        assert manager.extension_for(swatch, "below") is dialog, (
            "the opener must resolve the picker as its below-side extension"
        )
        assert manager.flyout_side(dialog) == "below", (
            "a dialog below its opener is entered with Down"
        )
        assert hasattr(dialog, "focus_first_child"), (
            "the sections enter an extension through focus_first_child() "
            "(a linked dialog without it is skipped)"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_down_from_the_opener_enters_the_picker(qapp, picker_host, store):
    """Down on the opener lands on the picker's first row, first control."""
    host, _row, swatch = picker_host
    _kbd_focus(swatch)
    dialog = _open_picker(qapp, swatch)
    try:
        _host_takes_the_keyboard_back(qapp, host, swatch)

        QTest.keyClick(swatch, Qt.Key.Key_Down)
        qapp.processEvents()

        assert QApplication.focusWidget() is not swatch, (
            "Down must not stay in the opener's toolbar row"
        )
        assert dialog.focusWidget() is dialog._sv, (
            "Down must enter the picker at the first row's first control "
            f"(got {type(dialog.focusWidget()).__name__})"
        )
        assert dialog.focusWidget() is not dialog, (
            "entry must not rest on the dialog frame"
        )
        assert dialog._picker_container.isAncestorOf(dialog.focusWidget())
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_entered_picker_owns_the_keyboard(qapp, picker_host, store):
    """After the handoff the picker's own row walk continues — proof the keys
    moved, not just the painted ring."""
    host, _row, swatch = picker_host
    _kbd_focus(swatch)
    dialog = _open_picker(qapp, swatch)
    try:
        _host_takes_the_keyboard_back(qapp, host, swatch)
        QTest.keyClick(swatch, Qt.Key.Key_Down)
        qapp.processEvents()
        assert dialog.focusWidget() is dialog._sv
        assert QApplication.focusWidget() is dialog._sv, (
            "the active window must be the picker, otherwise arrows keep "
            "walking the toolbar behind it"
        )

        QTest.keyClick(dialog._sv, Qt.Key.Key_Down)
        qapp.processEvents()
        assert dialog._fields_container.isAncestorOf(dialog.focusWidget()), (
            "the next Down must walk the picker's own rows, not the host's"
        )
    finally:
        NavigationManager.get_instance().unregister(dialog)
        dialog.deleteLater()


def test_escape_from_the_entered_picker_returns_to_the_opener(
    qapp, picker_host, store
):
    """Esc closes and the keyboard comes back to the exact opener."""
    host, _row, swatch = picker_host
    _kbd_focus(swatch)
    dialog = _open_picker(qapp, swatch)
    manager = NavigationManager.get_instance()
    try:
        _host_takes_the_keyboard_back(qapp, host, swatch)
        QTest.keyClick(swatch, Qt.Key.Key_Down)
        qapp.processEvents()
        assert dialog.focusWidget() is dialog._sv
        assert QApplication.focusWidget() is dialog._sv, (
            "precondition: the handoff moved the keyboard dispatch into the "
            "picker, not just its window-local focus record"
        )

        # The real routing path: Esc from the focused control (not injected on
        # the dialog), so native propagation through the dialog's reject path
        # is what closes it.
        QTest.keyClick(dialog._sv, Qt.Key.Key_Escape)
        qapp.processEvents()

        assert not dialog.isVisible(), "Esc must close the picker"
        assert swatch._dialog is None
        assert host.focusWidget() is swatch, "focus must return to the opener"
        assert manager.extension_for(swatch, "below") is None, (
            "a closed picker must not stay enterable"
        )
    finally:
        manager.unregister(dialog)
        dialog.deleteLater()
