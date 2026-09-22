"""ValueSliderRow: always-visible right-hand value label, no left pad.

The label reads the slider's live value in the same format the hover hint
flyout used to; the row disables the hint flyout entirely (the persistent
label replaces it), and a fixed-width right pad keeps the slider's
geometry stable as the value text changes. There is no left pad — the
track starts flush at the row's left edge.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QDialog, QHBoxLayout

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import Slider

from tests.helpers.drain_until_stable import drain_until_stable
from ui.widgets.slider_hint import ValueSlider, ValueSliderRow, _percent_text


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _make_dialog(slider) -> QDialog:
    dialog = QDialog()
    dialog.resize(500, 120)
    layout = QHBoxLayout(dialog)
    slider.setRange(1, 100)
    slider.setValue(50)
    layout.addWidget(ValueSliderRow(slider), 1)
    dialog.show()
    return dialog


def _settle_row(dialog) -> ValueSliderRow:
    """Bounded settle wait replacing bare ``qtbot.waitExposed`` no-ops.

    Offscreen ``waitExposed`` returns immediately without guaranteeing
    layout/polish; under ``-n 8`` load the label geometry may still be
    (0, 0) on first assert. Poll until visibility + label/pad/slider
    geometry stabilize for 2 frames instead.
    """
    row = dialog.findChild(ValueSliderRow)
    assert row is not None
    drain_until_stable(
        None,
        lambda: (
            row.isVisible(),
            row._label.isHidden(),
            row._label.width(),
            row._label.height(),
            row._right_pad.width(),
            row._slider.width(),
            row._slider.height(),
        ),
        timeout_ms=1000,
        poll_ms=10,
        stable_frames=2,
    )
    return row


def test_label_tracks_slider_value(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)
    assert row._label.text() == _percent_text(slider)

    slider.setValue(75)
    assert row._label.text() == _percent_text(slider)
    assert row._label.text() != "50,0%"


def test_row_disables_hint_flyout(qtbot):
    """The row replaces the hover hint flyout with its own readout: the
    slider must not create a hint controller at all."""
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    assert not row._label.isHidden(), "the label is always visible"
    assert slider._hint_controller is None, (
        "the row disables the hint flyout; no controller should be created"
    )


def test_hint_enabled_flag_can_be_restored(qtbot):
    slider = ValueSlider()
    slider.set_hint_enabled(False)
    assert not slider._hint_enabled

    slider.set_hint_enabled(True)
    dialog = QDialog()
    dialog.resize(300, 80)
    dialog.layout() or None
    from PySide6.QtWidgets import QHBoxLayout

    layout = QHBoxLayout(dialog)
    slider.setRange(1, 100)
    layout.addWidget(slider, 1)
    qtbot.addWidget(dialog)
    dialog.show()
    drain_until_stable(
        None,
        lambda: (slider.isVisible(), slider.width(), slider.height()),
        timeout_ms=1000,
        poll_ms=10,
        stable_frames=2,
    )
    assert slider._hint_controller is not None


def test_slider_geometry_stable_across_value_changes(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    before = slider.geometry()
    assert before.width() > 0, "slider must have settled geometry before the check"

    slider.setValue(1)
    slider.setValue(100)
    assert slider.geometry() == before, (
        "changing the value text must not reflow the row -- the fixed-width "
        "right pad absorbs it"
    )


def test_label_sits_right_of_track_without_left_pad(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    assert not hasattr(row, "_left_pad"), "the left pad was removed"
    assert row._right_pad.minimumWidth() > 0
    assert row._right_pad.geometry().left() > slider.geometry().right()
    # No left pad: the slider starts at the row's own left edge (row-local
    # pos; row geometry is offset by the dialog's layout margins).
    assert slider.pos().x() == 0


def test_pad_width_fits_widest_value_text(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    fm = QFontMetrics(row._label.font())
    # The default percent formatter's widest sample over the 1..100 range.
    assert row._right_pad.minimumWidth() >= fm.horizontalAdvance("100,0%")


def test_pad_width_follows_live_scale(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    base = row._right_pad.minimumWidth()

    UiScale.get_instance().set_factor(1.5)
    assert row._right_pad.minimumWidth() > base

    UiScale.get_instance().set_factor(1.0)
    assert row._right_pad.minimumWidth() == base


def test_plain_slider_row_keeps_label_visible(qtbot):
    """A row over a bare toolkit Slider (no hint controller) must still show
    the value readout."""
    slider = Slider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    row = _settle_row(dialog)

    assert not row._label.isHidden()
    assert row._label.text() == _percent_text(slider)
