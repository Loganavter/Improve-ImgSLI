"""SV square: held-key diagonal movement, continuity, and the ring gutter.

Falsification story (what is red on the pre-change fixed-step code):

- ``test_simultaneous_keys_move_one_normalized_diagonal`` — the old handler
  moved inside ``keyPressEvent``: W then D applied a FULL ``EDIT_STEP`` to
  each axis (a diagonal of length ``step*sqrt(2)``, i.e. double speed), and
  there was no tick to sample at all. The test pins one tick whose per-axis
  delta is ``step/sqrt(2)`` and whose length is one axis step.
- ``test_hold_produces_continuous_accelerating_ticks`` — the old code had no
  timer: one press = one step, so a hold produced exactly one delta,
  monotonic-growth and the 4x ramp assertions fail.
- ``test_focus_out_and_leaving_edit_mode_clear_the_hold`` — there was no
  held-key state to leak; this is a regression guard for the new state model
  (without ``clear()`` on focus-out/edit-exit the timer would keep moving a
  widget that no longer has the key).
- ``test_content_rect_reserves_a_scaled_ring_gutter`` — the old square had
  no ``content_rect`` (gradient spanned the whole widget), so the gutter and
  the scale assertion cannot hold.

The tap test is a guard in the opposite direction: the new held-key model
must not swallow a plain ``QTest.keyClick`` (press+release before the first
tick), which is the only way a single tap is delivered.
"""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QFocusEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

import ui.widgets.color.picker_dialog as picker_module
from sli_ui_toolkit.managers import UiScale, scaled_px
from ui.widgets.color.picker_dialog import _SV_RING_GUTTER_DP, _SVSquare
from ui.widgets.color.sv_movement import KeyHoldStepper


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _factor_one():
    """UiScale is a process-wide singleton; leave the factor at 1.0."""
    UiScale.get_instance().set_factor(1.0)
    yield
    UiScale.get_instance().set_factor(1.0)


def _square(qapp) -> _SVSquare:
    sv = _SVSquare()
    sv.resize(220, 170)
    sv.show()
    qapp.processEvents()
    return sv


def _enter_edit(sv: _SVSquare, qapp) -> None:
    QTest.keyClick(sv, Qt.Key.Key_Return)
    qapp.processEvents()
    assert sv.is_editing()


def _ticks(stepper: KeyHoldStepper) -> list[tuple[float, float, float]]:
    seen: list[tuple[float, float, float]] = []
    stepper.tick.connect(lambda dx, dy, dt: seen.append((dx, dy, dt)))
    return seen


# ---------------------------------------------------------------------------
# Stepper math (held-key set + timer contract)
# ---------------------------------------------------------------------------


def test_simultaneous_keys_move_one_normalized_diagonal(qapp):
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Up)
    stepper.press(Qt.Key.Key_Right)
    try:
        stepper.advance(stepper.interval_seconds)
        assert len(seen) == 1, "two held keys must share ONE tick (a diagonal)"
        dx, dy, dt = seen[0]
        assert dt == pytest.approx(stepper.interval_seconds)
        # The first tick is exactly 1x: per-axis delta is step/sqrt(2), and
        # the diagonal's length equals one axis step (no double speed).
        assert dx == pytest.approx(stepper.step / math.sqrt(2))
        assert dy == pytest.approx(stepper.step / math.sqrt(2))
        assert math.hypot(dx, dy) == pytest.approx(stepper.step)
    finally:
        stepper.clear()


def test_a_single_axis_tick_moves_the_full_base_step(qapp):
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Up)
    try:
        stepper.advance(stepper.interval_seconds)
        # ``pytest.approx`` refuses NESTED structures (newer pytest raises
        # TypeError instead of silently comparing tuples element-wise), so the
        # single tick is unpacked and compared axis by axis.
        assert len(seen) == 1
        tick_dx, tick_dy, tick_dt = seen[0]
        assert (tick_dx, tick_dy) == pytest.approx((0.0, 0.01))
        assert tick_dt == pytest.approx(stepper.interval_seconds)
    finally:
        stepper.clear()


def test_hold_produces_continuous_accelerating_ticks(qapp):
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Up)
    try:
        for _ in range(80):  # 80 * 16 ms = 1.28 s of held movement
            stepper.advance(0.016)
        deltas = [dy for _dx, dy, _dt in seen]
        assert len(deltas) == 80, "a hold must tick every interval, not once"
        assert all(delta > 0.0 for delta in deltas)
        assert deltas == sorted(deltas), "the ramp must never slow the hold down"
        assert deltas[-1] >= 3.5 * deltas[0], (
            "after ~0.8 s the multiplier must be near its 4x ceiling"
        )
    finally:
        stepper.clear()


def test_release_stops_the_stepper_and_freezes_the_value(qapp):
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Right)
    stepper.advance(stepper.interval_seconds)
    assert stepper.active is True

    stepper.release(Qt.Key.Key_Right)
    assert stepper.active is False
    assert stepper.pressed_keys == frozenset()

    tick_count = len(seen)
    stepper.advance(stepper.interval_seconds)
    assert len(seen) == tick_count, "no keys held -> no further ticks"


def test_tap_moves_exactly_one_base_step(qapp):
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Right)
    stepper.release(Qt.Key.Key_Right)
    assert stepper.active is False
    assert len(seen) == 1, "a tap must still move (one base step)"
    dx, dy, _dt = seen[0]
    assert dx == pytest.approx(0.01)
    assert dy == pytest.approx(0.0)


def test_auto_repeat_presses_do_not_double_the_step(qapp):
    """A duplicated press (what Qt auto-repeat sends) must be a no-op."""
    stepper = KeyHoldStepper(step=0.01)
    seen = _ticks(stepper)
    stepper.press(Qt.Key.Key_Right)
    stepper.press(Qt.Key.Key_Right)
    stepper.advance(stepper.interval_seconds)
    stepper.release(Qt.Key.Key_Right)
    assert len(seen) == 1, "the repeat press must not add a second base step"


# ---------------------------------------------------------------------------
# Square integration (real widget, synthetic key events)
# ---------------------------------------------------------------------------


def test_square_moves_diagonally_on_simultaneous_keys(qapp):
    sv = _square(qapp)
    try:
        sv.set_sv(0.5, 0.5)
        _enter_edit(sv, qapp)
        QTest.keyPress(sv, Qt.Key.Key_W)
        QTest.keyPress(sv, Qt.Key.Key_D)
        try:
            sv._stepper.advance(sv._stepper.interval_seconds)
            qapp.processEvents()
            expected = sv.EDIT_STEP / math.sqrt(2)
            assert sv._sat == pytest.approx(0.5 + expected)
            assert sv._val == pytest.approx(0.5 + expected)
            # Total movement equals one axis step (no diagonal double-speed).
            assert math.hypot(sv._sat - 0.5, sv._val - 0.5) == pytest.approx(
                sv.EDIT_STEP
            )
        finally:
            QTest.keyRelease(sv, Qt.Key.Key_W)
            QTest.keyRelease(sv, Qt.Key.Key_D)
    finally:
        sv.deleteLater()


def test_square_hold_moves_continuously_and_stops_on_release(qapp):
    sv = _square(qapp)
    try:
        sv.set_sv(0.2, 0.2)
        _enter_edit(sv, qapp)

        QTest.keyPress(sv, Qt.Key.Key_Right)
        try:
            QTest.qWait(90)  # several 16 ms ticks on the real timer
            qapp.processEvents()
            assert sv._stepper.active is True
            held_sat = sv._sat
            assert held_sat > 0.2, "a held key must move continuously"
        finally:
            QTest.keyRelease(sv, Qt.Key.Key_Right)

        assert sv._stepper.active is False
        assert sv._stepper._timer.isActive() is False, "the timer must stop"
        frozen_sat = sv._sat
        QTest.qWait(90)
        qapp.processEvents()
        assert sv._sat == frozen_sat, "no ticks may fire after the release"
    finally:
        sv.deleteLater()


def test_square_tap_still_moves_one_base_step(qapp):
    sv = _square(qapp)
    try:
        sv.set_sv(0.5, 0.5)
        _enter_edit(sv, qapp)
        QTest.keyClick(sv, Qt.Key.Key_D)
        qapp.processEvents()
        assert sv._sat == pytest.approx(0.5 + sv.EDIT_STEP)
        assert sv._val == pytest.approx(0.5)
        assert sv._stepper.active is False
    finally:
        sv.deleteLater()


def test_focus_out_and_leaving_edit_mode_clear_the_hold(qapp):
    sv = _square(qapp)
    try:
        _enter_edit(sv, qapp)

        QTest.keyPress(sv, Qt.Key.Key_W)
        assert sv._stepper.active is True

        # Focus-out is the path where the eventual keyRelease goes elsewhere.
        QApplication.sendEvent(sv, QFocusEvent(QEvent.Type.FocusOut))
        assert sv._stepper.active is False
        assert sv._stepper.pressed_keys == frozenset()
        assert sv._stepper._timer.isActive() is False
        assert sv.is_editing() is False
        QTest.keyRelease(sv, Qt.Key.Key_W)  # the "stolen" release must be safe

        # Leaving edit mode (Enter commits) also drops the held set.
        _enter_edit(sv, qapp)
        QTest.keyPress(sv, Qt.Key.Key_D)
        assert sv._stepper.active is True
        QTest.keyClick(sv, Qt.Key.Key_Return)
        qapp.processEvents()
        assert sv.is_editing() is False
        assert sv._stepper.active is False
        assert sv._stepper.pressed_keys == frozenset()
    finally:
        sv.deleteLater()


# ---------------------------------------------------------------------------
# Focus-ring gutter
# ---------------------------------------------------------------------------


def test_content_rect_reserves_a_scaled_ring_gutter(qapp, monkeypatch):
    sv = _square(qapp)
    try:
        gutter = sv._ring_gutter_px
        outer = QRectF(sv.rect())
        content = sv.content_rect()

        assert gutter >= 2, "the ring gutter must be at least 2 design px"
        assert gutter == pytest.approx(scaled_px(_SV_RING_GUTTER_DP))
        assert content.left() - outer.left() == pytest.approx(gutter)
        assert content.top() - outer.top() == pytest.approx(gutter)
        assert outer.right() - content.right() == pytest.approx(gutter)
        assert outer.bottom() - content.bottom() == pytest.approx(gutter)

        # The ring is painted on the OUTER widget boundary (shared helper),
        # so the gradient/border start beyond the ring's stroke: the gutter
        # is the visible gap, not the ring overlapping the field.
        ring_calls: list[object] = []
        real_ring = picker_module.paint_focus_ring

        def _spy(widget, painter, theme_manager=None, *, corner_radius=None):
            ring_calls.append(widget)
            return real_ring(
                widget, painter, theme_manager, corner_radius=corner_radius
            )

        monkeypatch.setattr(picker_module, "paint_focus_ring", _spy)
        # Deterministic offscreen focus: the paint gate is
        # ``_keyboard_focus and hasFocus()`` (the modality itself is pinned by
        # test_color_picker_navigation.py).
        monkeypatch.setattr(sv, "hasFocus", lambda: True)
        sv._keyboard_focus = True
        sv.grab()
        assert ring_calls == [sv], "the ring must be drawn for the whole widget"
        thickness = max(1.0, 2.0 * UiScale.get_instance().factor())
        assert gutter > thickness, (
            "the gradient must start beyond the ring stroke (visible gutter)"
        )

        # Live UI-scale change: the gutter is re-derived at USE time.
        UiScale.get_instance().set_factor(1.5)
        sv.apply_metrics()
        content_at_1_5 = sv.content_rect()
        assert sv._ring_gutter_px == pytest.approx(scaled_px(_SV_RING_GUTTER_DP))
        assert sv._ring_gutter_px > gutter
        assert content_at_1_5.left() - outer.left() == pytest.approx(
            sv._ring_gutter_px
        )
        assert content_at_1_5.top() - outer.top() == pytest.approx(
            sv._ring_gutter_px
        )
    finally:
        sv.deleteLater()


def test_gradient_and_hit_testing_share_the_content_rect(qapp):
    """The click at the field's edge maps to 0/1 inside ``content_rect``."""
    sv = _square(qapp)
    try:
        sv.set_sv(0.5, 0.5)
        content = sv.content_rect()
        sv._set_from_pos(content.topLeft())
        assert sv._sat == pytest.approx(0.0)
        assert sv._val == pytest.approx(1.0)
        sv._set_from_pos(content.bottomRight())
        assert sv._sat == pytest.approx(1.0)
        assert sv._val == pytest.approx(0.0)
    finally:
        sv.deleteLater()
