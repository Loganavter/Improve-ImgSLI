"""Magnifier settings flyout box aligns to the anchor group's border box at every UiScale factor.

Regression: at 125%/150% UI scale the flyout's box landed 1px off the
magnifier ButtonGroup's painted border box. ``show_aligned()`` centers
the flyout on the group *widget* center, computing
``round(anchor_left + W/2) - round((W - 2m)/2)`` with two independent
roundings (``m = scaled_px(6)``). When ``W`` is odd, the .5 fractional
parts round up or down depending on the parity of the integer parts —
which depends on the parity of ``anchor_left`` vs ``m``, so the box ends
up 1px left or right exactly when ``parity(anchor_left) != parity(m)``
(any scale whose group width comes out odd). The fix snaps x to the
border-box left edge explicitly, like the existing y-gap correction.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit.managers import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.buttons.button_group import ButtonGroup

from tabs.image_compare.ui.magnifier_settings_flyout import MagnifierSettingsFlyout


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _narrow_content() -> QWidget:
    """Content narrower than the group box, so the flyout width is driven
    by the anchor group (container.setFixedWidth), not by content."""
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.addWidget(Button("slot content"))
    return panel


@pytest.mark.parametrize("factor", [1.0, 1.25, 1.5, 2.0])
@pytest.mark.parametrize("anchor_x", [57, 58])
def test_flyout_left_edge_tracks_group_border_box(qapp, factor, anchor_x):
    UiScale.get_instance().set_factor(factor)

    window = QWidget()
    window.resize(900, 500)
    # Odd group width + both anchor-x parities: the pre-fix center-alignment
    # math drifted 1px (left or right) whenever parity(anchor_left) !=
    # parity(scaled_px(6)) — the fix must keep the left edge exact at every
    # scale, anchor position, and parity.
    group = ButtonGroup([Button("") for _ in range(6)], label="лупа")
    group.setFixedWidth(185)
    group.setParent(window)
    group.move(anchor_x, 40)

    flyout = MagnifierSettingsFlyout(window, _narrow_content())
    window.show()
    qapp.processEvents()
    flyout.show_for_group(group)
    qapp.processEvents()

    group_left = group.mapTo(window, QPoint(0, 0)).x()
    expected_left = group_left + scaled_px(6)
    assert flyout.x() == expected_left
    assert flyout.width() == group.width() - 2 * scaled_px(6)

    flyout.hide()
    window.close()