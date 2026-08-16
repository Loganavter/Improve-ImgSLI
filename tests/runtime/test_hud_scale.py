"""ZoomIndicator/InfoHUD must scale with the UI scale.

Regression: the corner HUDs kept fixed-px insets (_MARGIN, layout spacing,
label margins), so at UI scale > 1.0 the chips sat flush against the canvas
corner; InfoHUD also never re-laid itself out when the host labels resized
on a font/scale change (ZoomIndicator already re-positions via
font_changed, InfoHUD did not).
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import Label


@pytest.fixture(autouse=True)
def _reset_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _bottom_gap(hud, target: QWidget) -> int:
    """Distance from the HUD's bottom edge to the target's bottom edge."""
    hud._position()
    return target.geometry().bottom() - hud.geometry().bottom()


def _left_gap(hud, target: QWidget) -> int:
    hud._position()
    return hud.geometry().left() - target.geometry().left()


def test_zoom_indicator_label_font_scales(qtbot):
    from ui.widgets.glass_hud import ZoomIndicator

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(800, 600)
    parent.show()
    qtbot.waitExposed(parent)
    target = QWidget(parent)
    target.setGeometry(10, 20, 600, 400)
    target.show()
    hud = ZoomIndicator(parent, target_widget=target)

    UiScale.get_instance().set_factor(1.0)
    hud.update_zoom(1.5)
    qtbot.wait(30)  # let the deferred _position() passes finish
    pt_1x = hud._label.font().pointSizeF()
    w_1x = hud.width()

    UiScale.get_instance().set_factor(2.0)
    hud.update_zoom(1.5)
    qtbot.wait(30)
    pt_2x = hud._label.font().pointSizeF()
    w_2x = hud.width()

    assert pt_2x == pytest.approx(2.0 * pt_1x), (
        f"zoom label font did not scale: {pt_1x} -> {pt_2x}"
    )
    assert w_2x > w_1x, "zoom indicator chip did not grow with the scale"


def test_zoom_indicator_corner_inset_scales(qtbot):
    from ui.widgets.glass_hud import ZoomIndicator

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(800, 600)
    parent.show()
    qtbot.waitExposed(parent)
    target = QWidget(parent)
    target.setGeometry(10, 20, 600, 400)
    target.show()
    hud = ZoomIndicator(parent, target_widget=target)

    UiScale.get_instance().set_factor(1.0)
    hud.update_zoom(1.5)
    gap_1x = _top_gap(hud, target)

    UiScale.get_instance().set_factor(2.0)
    hud.update_zoom(1.5)
    gap_2x = _top_gap(hud, target)

    assert gap_2x == pytest.approx(2.0 * gap_1x), (
        f"zoom indicator top inset did not scale: {gap_1x} -> {gap_2x}"
    )
    _settle(qtbot)


def test_info_hud_corner_inset_scales(qtbot):
    from ui.widgets.glass_hud import InfoHUD

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(800, 600)
    parent.show()
    qtbot.waitExposed(parent)
    target = QWidget(parent)
    target.setGeometry(10, 20, 600, 400)
    target.show()
    hud = InfoHUD(parent, corner="left")
    hud.add_label(Label("1920x1080", pixel_size=16))
    hud.show_on(target)
    qtbot.wait(10)

    UiScale.get_instance().set_factor(1.0)
    left_1x = _left_gap(hud, target)
    UiScale.get_instance().set_factor(2.0)
    left_2x = _left_gap(hud, target)

    assert left_2x == pytest.approx(2.0 * left_1x), (
        f"info hud left inset did not scale: {left_1x} -> {left_2x}"
    )
    _settle(qtbot)


def test_info_hud_repositions_on_font_change(qtbot):
    """font_changed must trigger a re-layout of the info chip (like ZoomIndicator)."""
    from sli_ui_toolkit.managers import UiFont

    from ui.widgets.glass_hud import InfoHUD

    parent = QWidget()
    qtbot.addWidget(parent)
    parent.resize(800, 600)
    parent.show()
    qtbot.waitExposed(parent)
    target = QWidget(parent)
    target.setGeometry(10, 20, 600, 400)
    target.show()
    hud = InfoHUD(parent, corner="left")
    hud.add_label(Label("1920x1080", pixel_size=16))
    hud.show_on(target)
    qtbot.wait(10)
    assert hud.isVisible()

    calls = []
    original = hud._position

    def _tracking_position():
        calls.append(1)
        return original()

    hud._position = _tracking_position
    UiFont.get_instance().font_changed.emit()
    qtbot.wait(10)

    assert calls, "InfoHUD must re-layout itself when the UI font changes"
    _settle(qtbot)


def _top_gap(hud, target: QWidget) -> int:
    hud._position()
    return hud.geometry().top() - target.geometry().top()


def _settle(qtbot):
    """Drain the deferred _position() singleShots before the test ends.

    ZoomIndicator schedules extra _position() passes on first show; if they
    fire after the widget is destroyed they raise RuntimeError in a Qt slot.
    """
    for _ in range(6):
        qtbot.wait(5)