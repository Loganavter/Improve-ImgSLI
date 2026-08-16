"""Magnifier settings flyout's slider-row gaps scale with UiScale.

Regression: the gaps between the flyout's slider rows were fixed px set at
build time, so after a live interface-scale change the rows kept the old
spacing (and the requested "pads between sliders" simply froze at 100%
values). ``_keep_spacing_scaled`` re-applies the design-space gap on every
``UiScale.scale_changed``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.widgets import Label, Slider

from tabs.image_compare.ui.layout import (
    ImageCompareLayoutBuilder,
    _SLIDER_GAP_DESIGN_PX,
    _keep_spacing_scaled,
)


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def test_keep_spacing_scaled_follows_live_scale(qapp):
    layout = QVBoxLayout()

    _keep_spacing_scaled(layout, _SLIDER_GAP_DESIGN_PX)
    assert layout.spacing() == _SLIDER_GAP_DESIGN_PX

    UiScale.get_instance().set_factor(1.5)
    assert layout.spacing() == scaled_px(_SLIDER_GAP_DESIGN_PX) == 15

    UiScale.get_instance().set_factor(1.0)
    assert layout.spacing() == _SLIDER_GAP_DESIGN_PX


def _fake_ui() -> SimpleNamespace:
    return SimpleNamespace(
        magnifier_settings_panel=QWidget(),
        slider_size=Slider(),
        slider_capture=Slider(),
        slider_speed=Slider(),
        label_magnifier_size=Label("size"),
        label_capture_size=Label("capture"),
        label_movement_speed=Label("speed"),
        combo_interpolation=Slider(),
        label_interpolation=Label("interp"),
    )


def test_slider_column_gap_scales_and_is_applied_to_panel(qapp):
    ui = _fake_ui()
    builder = ImageCompareLayoutBuilder(ui, None)
    builder._slider_panel_layout()

    panel_layout = ui.magnifier_settings_panel.layout()
    column = panel_layout.itemAt(0).layout()

    assert panel_layout.spacing() == 5
    assert column.spacing() == _SLIDER_GAP_DESIGN_PX

    UiScale.get_instance().set_factor(1.5)
    assert column.spacing() == scaled_px(_SLIDER_GAP_DESIGN_PX)