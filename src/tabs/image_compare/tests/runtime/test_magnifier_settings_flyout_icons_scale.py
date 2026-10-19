"""Magnifier settings flyout's slider-row icons rescale with UiScale.

Regression: the flyout's icons were plain QLabels with one-shot pixmaps
generated at build time (``scaled_px(18)``), so after a live UI-scale
change (125%, 150%, ...) they stayed at the old size while the rest of
the panel resized. Toolkit widgets subscribe to ``UiScale.scale_changed``
themselves; the app-side ``ScaledIconLabel`` does the same for these
icons.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.managers import UiScale, scaled_px

from core.evidence.journal import record_evidence, reset_journal, verdict
from tabs.image_compare.icons import Icon
from tabs.image_compare.ui.layout import ScaledIconLabel
from tests.helpers.drain_until_stable import drain_until_stable


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    reset_journal()
    yield
    UiScale.get_instance().set_factor(1.0)


def test_icon_label_renders_at_current_scale(qapp: QApplication):
    UiScale.get_instance().set_factor(1.5)
    label = ScaledIconLabel(Icon.MAGNIFIER, 18)

    expected = scaled_px(18)
    assert label.width() == expected
    assert label.height() == expected
    pixmap = label.pixmap()
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.width() == expected


def test_icon_label_rerenders_on_scale_change(qapp: QApplication):
    """A live factor change re-renders the icon pixmap at the new size.

    Falsification: red at the pre-``a7b4e5c0`` base (``1bf913a7``) —
    ``label.width()`` was asserted synchronously after ``set_factor(1.5)`` and
    still held the 1.0 size (18 != 27) because the rescale rides the coalesced
    metrics channel (a zero-timer). Green at the current integration head. The
    evidence record is derived from the observed label and pixmap widths, so a
    regression emits ``violated`` with the measured numbers and fails the probe.
    """
    label = ScaledIconLabel(Icon.CAPTURE_SIZE, 18)
    assert label.width() == scaled_px(18)

    # The rescale is delivered through the coalesced metrics channel (a
    # zero-timer), so a bare set_factor() is not enough — drain before reading.
    UiScale.get_instance().set_factor(1.5)
    drain_until_stable(qapp, lambda: (label.width(), label.pixmap().width()))
    assert label.width() == scaled_px(18)
    assert label.pixmap().width() == scaled_px(18)

    expected = scaled_px(18)
    observed_width = label.width()
    observed_pixmap = label.pixmap().width()
    record_evidence("spec.ui.scale_parity",
                    kind="spec",
                    verdict=("ok"
                             if (observed_width, observed_pixmap) == (expected, expected)
                             else "violated"),
                    signal=(f"factor={UiScale.get_instance().factor()} "
                            f"label_width={observed_width} pixmap_width={observed_pixmap} "
                            f"expected={expected}"),
                    reason="owned derived geometry re-derived after a live scale change",
                    ids=("layout:ScaledIconLabel",),
                    area="image_compare.layout")
    record = verdict(None, "spec.ui.scale_parity")
    assert record is not None, "scale-parity probe emitted no evidence"
    assert record.verdict == "ok", record.signal

    UiScale.get_instance().set_factor(1.0)
    drain_until_stable(qapp, lambda: (label.width(), label.pixmap().width()))
    assert label.width() == scaled_px(18)
    assert label.pixmap().width() == scaled_px(18)