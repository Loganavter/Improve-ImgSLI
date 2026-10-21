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
from sli_ui_toolkit.widgets import Slider, Text

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_compare.ui.layout import (
    ImageCompareLayoutBuilder,
    _SLIDER_GAP_DESIGN_PX,
    _keep_spacing_scaled,
)
from tests.helpers.drain_until_stable import drain_until_stable


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    reset_journal()
    yield
    UiScale.get_instance().set_factor(1.0)


def test_keep_spacing_scaled_follows_live_scale(qapp):
    """The helper re-applies the design gap when the live factor changes.

    Falsification: red at the pre-``a7b4e5c0`` base (``1bf913a7``) — the helper
    gained a required ``owner`` argument (``TypeError: missing 1 required
    positional argument: 'owner'``) and the re-apply rides the coalesced metrics
    channel (a zero-timer), so a bare ``set_factor`` read the old 10 while 1.5
    asked for 15. Green at the current integration head; the assertion still
    fails with the measured numbers if the invariant regresses.
    """
    layout = QVBoxLayout()
    owner = QWidget()

    _keep_spacing_scaled(layout, _SLIDER_GAP_DESIGN_PX, owner)
    assert layout.spacing() == _SLIDER_GAP_DESIGN_PX

    # The re-apply rides the coalesced metrics channel (a zero-timer), so a
    # bare set_factor() is not enough — drain before reading.
    UiScale.get_instance().set_factor(1.5)
    drain_until_stable(qapp, layout.spacing)
    assert layout.spacing() == scaled_px(_SLIDER_GAP_DESIGN_PX) == 15

    UiScale.get_instance().set_factor(1.0)
    drain_until_stable(qapp, layout.spacing)
    assert layout.spacing() == _SLIDER_GAP_DESIGN_PX


def _fake_ui() -> SimpleNamespace:
    return SimpleNamespace(
        magnifier_settings_panel=QWidget(),
        slider_size=Slider(),
        slider_capture=Slider(),
        slider_speed=Slider(),
        label_magnifier_size=Text("size", mode="plain"),
        label_capture_size=Text("capture", mode="plain"),
        label_movement_speed=Text("speed", mode="plain"),
        combo_interpolation=Slider(),
        label_interpolation=Text("interp", mode="plain"),
    )


def test_slider_column_gap_scales_and_is_applied_to_panel(qapp):
    """The built slider column follows a live factor change, and proves it.

    Falsification: red at the pre-``a7b4e5c0`` base (``1bf913a7``) —
    ``column.spacing()`` was read synchronously right after ``set_factor(1.5)``
    and still held the design gap (10 != 15) because the coalesced metrics
    flush had not landed; and the helper call raised ``TypeError`` for the
    missing ``owner``. Green at the current integration head. The evidence
    record below is derived from the observed spacing (``violated`` on a
    regression), so the probe fails with the measured numbers, not a guessed
    verdict.
    """
    ui = _fake_ui()
    builder = ImageCompareLayoutBuilder(ui, None)
    builder._slider_panel_layout()

    panel_layout = ui.magnifier_settings_panel.layout()
    column = panel_layout.itemAt(0).layout()

    assert panel_layout.spacing() == 5
    assert column.spacing() == _SLIDER_GAP_DESIGN_PX

    UiScale.get_instance().set_factor(1.5)
    drain_until_stable(qapp, column.spacing)
    assert column.spacing() == scaled_px(_SLIDER_GAP_DESIGN_PX)

    expected = scaled_px(_SLIDER_GAP_DESIGN_PX)
    observed = column.spacing()
    record_evidence("spec.ui.scale_parity",
                    kind="spec",
                    verdict="ok" if observed == expected else "violated",
                    signal=(f"factor={UiScale.get_instance().factor()} "
                            f"column_spacing={observed} expected={expected}"),
                    reason="owned derived geometry re-derived after a live scale change",
                    ids=("layout:_keep_spacing_scaled",),
                    area="image_compare.layout")
    record = verdict(None, "spec.ui.scale_parity")
    assert record is not None, "scale-parity probe emitted no evidence"
    assert record.verdict == "ok", record.signal
