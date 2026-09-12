"""OverlayLayer.anchor_rect must map into host-local coordinates correctly.

Regression: ``anchor_rect`` used ``anchor_widget.mapTo(self._host)``. When the
anchor lives in a top-level child window whose QObject parent is the host
(the Settings dialog is parented to the main window), Qt's ``mapTo`` treats
the host as sitting at (0, 0) and returns the anchor's *global* position
instead of host-local coordinates. In-window flyouts anchored to such a
dialog (e.g. the slider value hint in the Settings window) then land far off
the anchor and get clamped into the host's bottom-right corner.

``mapToGlobal() - mapToGlobal()`` is correct for any host (top-level or not).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QHBoxLayout, QWidget

from shared_toolkit.ui.overlay_layer import OverlayLayer, get_overlay_layer
from sli_ui_toolkit.config import configure_toolkit, reset_toolkit_config
from ui.widgets.slider_hint import SliderHintFlyout, ValueSlider


@pytest.fixture
def _with_overlay_resolver():
    """Mirror the app: configure_toolkit wires the overlay resolver.

    Without it BaseFlyout never re-parents to the host overlay layer, which
    is exactly the setup this regression is about.
    """
    configure_toolkit(overlay_resolver=get_overlay_layer)
    try:
        yield
    finally:
        reset_toolkit_config()


def _slider_in_child_dialog(qtbot):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(1000, 700)
    host.move(200, 150)
    host.overlay_layer = OverlayLayer(host)
    host.show()
    qtbot.waitExposed(host)

    dialog = QDialog(host)
    dialog.resize(600, 300)
    layout = QHBoxLayout(dialog)
    slider = ValueSlider()
    slider.setRange(3, 8)
    slider.setValue(5)
    layout.addWidget(slider)
    qtbot.addWidget(dialog)
    dialog.move(350, 250)
    dialog.show()
    qtbot.waitExposed(dialog)
    return host, dialog, slider


def test_anchor_rect_is_host_local_for_top_level_child(qtbot):
    """Global-difference mapping, not mapTo(host) from a child top-level."""
    host, _dialog, slider = _slider_in_child_dialog(qtbot)

    expected = slider.mapToGlobal(QPoint(0, 0)) - host.mapToGlobal(QPoint(0, 0))
    actual = host.overlay_layer.anchor_rect(slider)

    assert actual.topLeft() == expected, (
        f"anchor_rect {actual.topLeft()} is not the host-local slider "
        f"position {expected} -- mapTo(host) from a child top-level returns "
        "global coordinates (host treated as (0, 0))"
    )
    assert actual.size() == slider.size()


def test_slider_flyout_over_thumb_in_child_dialog(qtbot, _with_overlay_resolver):
    """The hint stays above the thumb even in the Settings setup.

    The overlay resolver walks past the dialog into the main window, but
    attach_in_window_widget must refuse to re-parent the flyout into an
    overlay host from a *different* window -- the hint stays a child of the
    dialog and paints above it.
    """
    host, _dialog, slider = _slider_in_child_dialog(qtbot)
    if slider._hint_controller is None:
        slider._ensure_hint_controller()
    flyout = slider._hint_controller._flyout
    assert not flyout.isWindow()
    assert flyout.parentWidget() is _dialog, (
        "the flyout must stay in the dialog window, not be re-parented into "
        "the main window's overlay layer"
    )

    flyout.show_value("1.25", slider)
    qtbot.waitExposed(flyout)

    # The flyout is a child of the dialog, so geometry is in dialog
    # coordinates; compare against the thumb's dialog-local position.
    thumb_rect = slider.flyoutAnchorRect()
    thumb_top_left = slider.mapTo(_dialog, thumb_rect.topLeft())
    panel_bottom = flyout.geometry().bottom() - SliderHintFlyout.SHADOW_RADIUS
    assert panel_bottom < thumb_top_left.y(), (
        f"flyout panel bottom {panel_bottom} is not above the thumb top "
        f"{thumb_top_left.y()} -- it landed off the anchor, likely clamped "
        "into the host's corner"
    )
    flyout_center_x = flyout.geometry().center().x()
    thumb_center_x = thumb_top_left.x() + thumb_rect.width() // 2
    assert abs(flyout_center_x - thumb_center_x) <= 3, (
        f"flyout X {flyout_center_x} drifted from the thumb X {thumb_center_x}"
    )
