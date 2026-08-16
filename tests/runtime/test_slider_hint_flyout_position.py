"""Slider hint flyout stays in the slider's own window, above the thumb.

Regression: the hint was parented to the slider itself (and, via the host
overlay layer, re-parented to the *main window*). In dialogs -- the Settings
window, export dialog -- that paints the flyout *under* the dialog window:
either clamped onto the slider track (no overlay layer, available rect = the
22px track) or behind the dialog (re-parented to an ancestor window's
overlay layer).

The hint is now parented to the slider's *window* (like the combo dropdown,
a plain child of the dialog window), and the toolkit's
``attach_in_window_widget`` refuses to re-parent it into an overlay host
from a different top-level window.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QHBoxLayout

from ui.widgets.slider_hint import SliderHintFlyout, ValueSlider


def _show_flyout(slider: ValueSlider) -> SliderHintFlyout:
    if slider._hint_controller is None:
        slider._ensure_hint_controller()
    flyout = slider._hint_controller._flyout
    # Mirror the controller's drag/hover path (see SliderHintController): the
    # value-change tracker only follows the anchor the controller considers
    # current.
    slider._hint_controller._current_anchor = slider
    flyout.show_value("1.25", slider)
    return flyout


def _slider_dialog(qtbot, *, width: int = 900) -> tuple[QDialog, ValueSlider]:
    dialog = QDialog()
    dialog.resize(width, 400)
    layout = QHBoxLayout(dialog)
    slider = ValueSlider()
    slider.setRange(3, 8)
    slider.setValue(5)
    layout.addWidget(slider)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitExposed(dialog)
    return dialog, slider


def test_flyout_stays_in_slider_window(qtbot):
    """The hint is a child of the slider's window, not of an ancestor one."""
    dialog, slider = _slider_dialog(qtbot)
    flyout = _show_flyout(slider)
    qtbot.waitExposed(flyout)

    assert not flyout.isWindow(), "the hint is an in-window child, not a popup"
    assert flyout.parentWidget() is dialog, (
        "flyout must be parented to the slider's window (not the slider, not "
        "an ancestor window's overlay) so it paints above the dialog like "
        "the combo dropdown"
    )


def test_flyout_sits_above_thumb_without_overlay(qtbot):
    """The flyout panel's bottom clears the thumb top; X stays centered."""
    dialog, slider = _slider_dialog(qtbot)
    flyout = _show_flyout(slider)
    qtbot.waitExposed(flyout)

    thumb_rect = slider.flyoutAnchorRect()
    thumb_top_left = slider.mapTo(dialog, thumb_rect.topLeft())
    thumb_center = thumb_top_left + QPoint(thumb_rect.width() // 2, 0)

    # Panel bottom (outer bottom minus the shadow halo) sits above the thumb
    # top; the outer bottom may reach the thumb top at most.
    panel_bottom = flyout.geometry().bottom() - SliderHintFlyout.SHADOW_RADIUS
    assert panel_bottom < thumb_top_left.y(), (
        f"flyout panel bottom {panel_bottom} is not above the thumb top "
        f"{thumb_top_left.y()} -- it was clamped into the slider track"
    )

    flyout_center_x = flyout.geometry().center().x()
    assert abs(flyout_center_x - thumb_center.x()) <= 2, (
        f"flyout X ({flyout_center_x}) drifted from the thumb center "
        f"({thumb_center.x()})"
    )


def test_flyout_tracks_thumb_after_value_change(qtbot):
    """reposition() re-anchors above the thumb when the value changes."""
    dialog, slider = _slider_dialog(qtbot)
    flyout = _show_flyout(slider)
    qtbot.waitExposed(flyout)

    # Mid-range value: the flyout stays clear of the dialog's right edge, so
    # exact centering on the thumb is meaningful (at the extremes the clamp
    # presses the flyout against the window edge -- expected behaviour).
    slider.setValue(6)
    qtbot.wait(10)

    thumb_rect = slider.flyoutAnchorRect()
    thumb_top_left = slider.mapTo(dialog, thumb_rect.topLeft())
    panel_bottom = flyout.geometry().bottom() - SliderHintFlyout.SHADOW_RADIUS
    assert panel_bottom < thumb_top_left.y()
    flyout_center_x = flyout.geometry().center().x()
    thumb_center_x = thumb_top_left.x() + thumb_rect.width() // 2
    assert abs(flyout_center_x - thumb_center_x) <= 3, (
        f"flyout did not track the thumb after setValue(6): flyout X "
        f"{flyout_center_x} vs thumb X {thumb_center_x} "
        f"(flyout geo={flyout.geometry()} thumb rect={thumb_rect})"
    )


def test_flyout_uses_slider_hint_group(qtbot):
    """The hint keeps its non-exclusive flyout group (dialog panels stay open)."""
    _dialog, slider = _slider_dialog(qtbot)
    flyout = _show_flyout(slider)
    assert flyout.flyout_group == "slider_hint"


def test_track_click_shows_flyout_with_jumped_value(qtbot):
    """Clicking the track must not paint a stale hint frame.

    Regression: the press event filter showed the hint synchronously with
    the OLD value at the OLD thumb position, then the slider's own press
    handling jumped the value and reposition() snapped the hint to the new
    state -- a visible one-frame flicker on every track click. The show is
    now deferred one event-loop tick, by which time setValue() has already
    fired, so the hint appears directly in its final state.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from ui.widgets.slider_hint import _percent_text

    dialog, slider = _slider_dialog(qtbot)
    controller = slider._hint_controller
    assert controller is not None
    flyout = controller._flyout

    # Click far right of the track (thumb sits mid-range at value 5 of 3..8).
    # Press only, no release: the release handler hides the hint when the
    # *real* cursor isn't over the slider (it isn't, in offscreen tests) --
    # in real usage the cursor is over the track after the click, so the
    # hint stays.
    track_pos = QPoint(slider.width() - 2, slider.height() // 2)
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=track_pos)

    # During the press dispatch no stale frame may be painted.
    assert not flyout.isVisible(), (
        "hint must not appear with the pre-jump value/position"
    )
    # Value has already jumped by the time the press returns.
    assert slider.value() == slider.maximum(), slider.value()
    # One tick later the hint shows with the final value.
    qtbot.wait(20)
    assert flyout.isVisible()
    assert flyout._label.text() == _percent_text(slider)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=track_pos)


def test_track_click_hint_is_instant_not_faded(qtbot):
    """The hint must not show as an empty box during a fade.

    Regression: the app-wide default flyout animation is a fade, and the
    fade pipeline hides the flyout's children while compositing a snapshot
    of the (still hidden) flyout -- the freshly-set label can be missing
    from that snapshot, so a track-jump show painted an EMPTY box for the
    whole fade. The hint now shows with ``animation="none"`` (instant,
    children painted live).
    """
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit

    from ui.widgets.slider_hint import _percent_text

    configure_toolkit(
        timings=FlyoutTimingConfig(default_flyout_animation="fade")
    )

    dialog, slider = _slider_dialog(qtbot)
    flyout = slider._hint_controller._flyout

    track_pos = QPoint(slider.width() - 2, slider.height() // 2)
    QTest.mousePress(slider, Qt.MouseButton.LeftButton, pos=track_pos)
    qtbot.wait(20)

    assert flyout.isVisible()
    # Instant show: no snapshot-based fade state, children visible (the
    # fade path would leave them hidden and composite the snapshot).
    assert flyout._fade.cache is None, (
        "hint must not fade via a snapshot -- it would hide the label"
    )
    assert not any(
        child.isHidden()
        for child in flyout.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        )
    )
    assert flyout._label.text() == _percent_text(slider)
    QTest.mouseRelease(slider, Qt.MouseButton.LeftButton, pos=track_pos)