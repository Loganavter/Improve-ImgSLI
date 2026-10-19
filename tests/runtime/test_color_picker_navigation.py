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
from PySide6.QtCore import QSettings, Qt
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
