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

from tabs.image_compare.icons import Icon
from tabs.image_compare.ui.layout import ScaledIconLabel


@pytest.fixture(autouse=True)
def _reset_ui_scale():
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
    label = ScaledIconLabel(Icon.CAPTURE_SIZE, 18)
    assert label.width() == scaled_px(18)

    UiScale.get_instance().set_factor(1.5)
    assert label.width() == scaled_px(18)
    assert label.pixmap().width() == scaled_px(18)

    UiScale.get_instance().set_factor(1.0)
    assert label.width() == scaled_px(18)
    assert label.pixmap().width() == scaled_px(18)