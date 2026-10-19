"""Key-state stepper for a 2-D value surface (the colour picker's SV square).

Widget-agnostic by design: it owns a 16 ms ``PreciseTimer`` and the set of
*held* canonical arrow keys, and emits ``tick(dx, dy, dt)`` in axis units.
The consumer maps those deltas onto its own value space (and clamps); the
WASD -> arrow mapping stays in the consumer, so this module knows nothing
about colour.

Why a held-key set instead of one step per key event: Qt's auto-repeat
delivers one key per event, never the combination, so two held keys can
only ever produce alternating axis ticks — never a diagonal — and the
motion stutters at the OS repeat rate. Here ``press`` only records state
and the timer samples the whole set, so ``W+D`` is a normalized diagonal
and a hold is continuous (60 Hz), independent of the repeat rate.

Speed model (matching the magnifier's interactive movement contract):

- ``step`` is one base step in consumer units (the SV square's ``0.01``).
  A tick moves ``step * dt / interval`` per axis at 1x.
- a diagonal divides both directions by the vector length, so its per-axis
  delta is ``step / sqrt(2)`` and its total distance equals an axis tick —
  never double speed on the diagonal.
- the multiplier ramps linearly from 1x to ``ACCEL_MAX_MULTIPLIER`` (4x)
  over ``ACCEL_RAMP_SECONDS`` (0.8 s) of *held movement*, then resets when
  the last key is released. The first tick is exactly 1x (the ramp counts
  elapsed ticks, so "hold" never changes a tap's step size).
- a tap — press+release before the first timer tick, which is what
  ``QTest.keyClick`` does — still moves exactly one base step, otherwise a
  single key press would move nothing.

Consumers must call ``clear()`` on focus-out, edit-mode exit and hide:
``clear()`` drops the pressed set, stops the timer and resets the ramp, so
a key released after the widget lost focus cannot leave it moving forever.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal


class KeyHoldStepper(QObject):
    """Sample held arrow keys on a timer and emit per-tick axis deltas.

    ``tick(dx, dy, dt)``: ``dx``/``dy`` are signed deltas in consumer units
    (right/up positive; a tap emits one base ``step`` and a nominal ``dt``),
    ``dt`` is the elapsed seconds of the tick (timer-paced) or one nominal
    interval for the immediate tap step.
    """

    tick = Signal(float, float, float)

    #: Timer cadence. 16 ms is one frame at 60 Hz: fast enough to read as
    #: continuous movement without queueing ticks behind a slow repaint.
    INTERVAL_MS = 16

    #: Hold acceleration: 1x at the first tick, ``ACCEL_MAX_MULTIPLIER``
    #: after this much held movement.
    ACCEL_RAMP_SECONDS = 0.8
    ACCEL_MAX_MULTIPLIER = 4.0

    #: Backstop for clock jumps (a suspended process delivers a huge dt):
    #: never teleport further than this many seconds' worth in one tick.
    MAX_DT_SECONDS = 0.05

    #: Canonical arrow key -> (dx, dy) direction. Up is +y, right is +x.
    _DIRECTIONS = {
        Qt.Key.Key_Left: (-1.0, 0.0),
        Qt.Key.Key_Right: (1.0, 0.0),
        Qt.Key.Key_Up: (0.0, 1.0),
        Qt.Key.Key_Down: (0.0, -1.0),
    }

    def __init__(self, step: float, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._step = float(step)
        self._pressed: set[int] = set()
        # Keys pressed but not yet moved by a timer tick: a release before
        # their first tick still owes them one base step (the tap case).
        self._pending_taps: set[int] = set()
        self._hold_seconds = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(self.INTERVAL_MS)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._on_timeout)
        self._clock = QElapsedTimer()

    @property
    def step(self) -> float:
        return self._step

    @property
    def interval_seconds(self) -> float:
        return self.INTERVAL_MS / 1000.0

    @property
    def active(self) -> bool:
        """True while at least one direction key is held."""
        return bool(self._pressed)

    @property
    def pressed_keys(self) -> frozenset[int]:
        """The held canonical keys (read-only view, for tests/diagnostics)."""
        return frozenset(self._pressed)

    def press(self, canonical_key: int) -> None:
        """Register a held key; a repeated ``press`` (auto-repeat) is a no-op."""
        if canonical_key not in self._DIRECTIONS or canonical_key in self._pressed:
            return
        self._pressed.add(canonical_key)
        self._pending_taps.add(canonical_key)
        if not self._timer.isActive():
            self._hold_seconds = 0.0
            self._clock.start()
            self._timer.start()

    def release(self, canonical_key: int) -> None:
        """Drop a held key; a tap (no tick yet) applies one base step."""
        if canonical_key not in self._pressed:
            return
        self._pressed.discard(canonical_key)
        tapped = canonical_key in self._pending_taps
        self._pending_taps.discard(canonical_key)
        if not self._pressed:
            self._timer.stop()
            self._hold_seconds = 0.0
        if tapped:
            dx, dy = self._DIRECTIONS[canonical_key]
            self.tick.emit(dx * self._step, dy * self._step, self.interval_seconds)

    def clear(self) -> None:
        """Stop and forget every held key (focus-out / edit exit / hide)."""
        self._pressed.clear()
        self._pending_taps.clear()
        self._hold_seconds = 0.0
        self._timer.stop()

    def advance(self, dt_seconds: float) -> None:
        """Emit one tick for ``dt_seconds`` of held movement.

        This is the only movement path — the timer calls it with its elapsed
        time, and tests call it with an exact ``dt`` so the step size is
        deterministic instead of racing a 16 ms timer.
        """
        if not self._pressed:
            return
        dt = min(max(float(dt_seconds), 0.0), self.MAX_DT_SECONDS)
        if dt <= 0.0:
            return

        dx_dir = sum(self._DIRECTIONS[key][0] for key in self._pressed)
        dy_dir = sum(self._DIRECTIONS[key][1] for key in self._pressed)
        if dx_dir == 0.0 and dy_dir == 0.0:
            # Opposite keys cancel (Left+Right): the hold is real but the
            # direction is zero — no tick, and no ramp progress either.
            return

        # Ramp from the movement already held, so the FIRST tick is exactly
        # 1x and a diagonal's base step is testable/unambiguous.
        ramp = min(1.0, self._hold_seconds / self.ACCEL_RAMP_SECONDS)
        multiplier = 1.0 + ramp * (self.ACCEL_MAX_MULTIPLIER - 1.0)
        self._hold_seconds += dt

        length = math.hypot(dx_dir, dy_dir)
        if length > 1.0:
            dx_dir /= length
            dy_dir /= length

        amount = self._step * (dt / self.interval_seconds) * multiplier
        self._pending_taps.clear()
        self.tick.emit(dx_dir * amount, dy_dir * amount, dt)

    def _on_timeout(self) -> None:
        self.advance(self._clock.restart() / 1000.0)
