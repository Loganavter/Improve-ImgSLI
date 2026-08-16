"""Interpolation flyout row metrics are fed to the toolkit as design values.

Regression: the interp flyout's rows grew ~factor^2 at high UI scale. The
combo's live metrics (``getItemHeight``/``getItemFont``) are already
scale-resolved, but ``SimpleOptionsFlyout.set_row_height``/``set_row_font``
take design values and scale them once — the factor had to be divided back
out, or a 150% UI scale produced 2.25x rows.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale, ui_font
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import (
    SimpleOptionsFlyout,
)

from tabs.image_compare.ui.transient_interpolation import _design_item_metrics


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def test_live_combo_metrics_convert_to_design_values():
    UiScale.get_instance().set_factor(1.5)

    # Live metrics as the combo reports them at 1.5x (34px design row,
    # 11pt design font -> 51px / 16.5pt); ui_font() resolves the scaled
    # size the way the combo's own getItemFont does.
    height, font = _design_item_metrics(51, ui_font(point_size=11), 1.5)

    assert height == 34
    assert font.pointSizeF() == pytest.approx(11.0, abs=0.5)


def test_pixel_size_fonts_convert_proportionally():
    UiScale.get_instance().set_factor(2.0)

    scaled = ui_font(pixel_size=12)  # 24px at 2.0 — a live scaled font
    height, font = _design_item_metrics(68, scaled, 2.0)

    assert height == 34
    assert font.pixelSize() == 12


def test_design_metrics_roundtrip_stays_single_scaled(qapp):
    """Design values through the flyout APIs end up scaled exactly once."""
    UiScale.get_instance().set_factor(1.5)
    host = QWidget()
    host.resize(400, 300)
    host.show()

    flyout = SimpleOptionsFlyout(parent_widget=host)
    height, font = _design_item_metrics(51, ui_font(point_size=11), 1.5)
    flyout.set_row_height(height)
    flyout.set_row_font(font)
    flyout.populate(["Nearest", "Bilinear"], current_index=0)

    assert flyout.rows()[0].height() == pytest.approx(51, abs=1)
    assert flyout.rows()[0].label.font().pointSizeF() == pytest.approx(16.5, abs=0.5)
    flyout.hide()