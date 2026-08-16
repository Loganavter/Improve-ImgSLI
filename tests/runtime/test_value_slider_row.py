"""ValueSliderRow: persistent right-hand value label + equal fixed pads.

The label reads the slider's live value in the same format as the hover
hint flyout, hides for the duration the flyout is active (it would
duplicate the flyout's readout above the thumb), and never shifts the
slider's geometry when it toggles: the fixed-width pads flanking the track
stay in the layout regardless of label visibility, so the track's position
and size are stable.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QDialog, QHBoxLayout

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import Slider

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


def _show_hint(slider: ValueSlider) -> None:
    controller = slider._hint_controller
    controller._pending_anchor = slider
    controller._show()


def _hide_hint(slider: ValueSlider) -> None:
    slider._hint_controller._hide()


def test_label_tracks_slider_value(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)

    row = dialog.findChild(ValueSliderRow)
    assert row is not None
    assert row._label.text() == _percent_text(slider)

    slider.setValue(75)
    assert row._label.text() == _percent_text(slider)
    assert row._label.text() != "50,0%"


def test_label_hides_while_hint_flyout_active(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    _show_hint(slider)
    assert slider._hint_controller._flyout.isVisible()
    assert not row._label.isVisible(), (
        "the persistent label must drop while the hint flyout reads the value"
    )

    _hide_hint(slider)
    assert row._label.isVisible()
    assert row._label.text() == _percent_text(slider)


def test_slider_geometry_stable_while_label_hidden(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    before = slider.geometry()
    assert before.width() > 0, "slider must have settled geometry before the check"

    _show_hint(slider)
    assert not row._label.isVisible()
    assert slider.geometry() == before, (
        "hiding the label must not reflow the row -- the pads absorb it"
    )

    _hide_hint(slider)
    assert slider.geometry() == before


def test_pads_flank_track_with_equal_width(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    left, right = row._left_pad, row._right_pad
    assert left.minimumWidth() > 0
    assert left.minimumWidth() == right.minimumWidth()

    assert left.geometry().right() < slider.geometry().left()
    assert right.geometry().left() > slider.geometry().right()


def test_pad_width_fits_widest_value_text(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    fm = QFontMetrics(row._label.font())
    # The default percent formatter's widest sample over the 1..100 range.
    assert row._right_pad.minimumWidth() >= fm.horizontalAdvance("100,0%")


def test_pad_widths_follow_live_scale(qtbot):
    slider = ValueSlider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    base = row._left_pad.minimumWidth()

    UiScale.get_instance().set_factor(1.5)
    assert row._left_pad.minimumWidth() == row._right_pad.minimumWidth()
    assert row._left_pad.minimumWidth() > base

    UiScale.get_instance().set_factor(1.0)
    assert row._left_pad.minimumWidth() == base


def test_plain_slider_row_keeps_label_visible(qtbot):
    """A row over a bare toolkit Slider (no hint controller) must still show
    the value readout and never try to hide it."""
    slider = Slider()
    dialog = _make_dialog(slider)
    qtbot.addWidget(dialog)
    qtbot.waitExposed(dialog)
    row = dialog.findChild(ValueSliderRow)

    assert not row._label.isHidden()
    assert row._label.text() == _percent_text(slider)
