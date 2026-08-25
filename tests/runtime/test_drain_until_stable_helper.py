"""Drain-until-stable helper correctness (W5 deflake-by-construction).

Inv: helper must return stable geometry without flake; single-drain exact check
would falsely fail if layout settles on second drain.
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from tests.helpers.drain_until_stable import drain_until_stable


def test_drain_until_stable_waits_for_deferred_layout(qapp):
    w = QWidget()
    w.resize(100, 100)
    w.show()
    qapp.processEvents()
    # Simulate deferred relayout: geometry changes after one singleShot
    snapshots = {"calls": 0}

    def getter():
        # First two calls differ, then stable
        snapshots["calls"] += 1
        if snapshots["calls"] < 3:
            return (100, 100, snapshots["calls"])
        return (200, 200, 3)

    # Should not timeout, should wait until stable
    res = drain_until_stable(qapp, getter, timeout_ms=500, poll_ms=5, stable_frames=2)
    assert res == (200, 200, 3)
    w.deleteLater()


def test_drain_until_stable_catches_second_frame_reflow(qapp):
    """Repro second-frame class: single drain would assert equal but reflow happens on next."""
    w = QWidget()
    w.resize(200, 200)
    w.show()

    # Schedule a deferred resize via singleShot(0)
    def deferred():
        w.resize(300, 300)

    QTimer.singleShot(0, deferred)

    # Single drain (one processEvents) would still see old size at least once
    # Helper must wait until stable 300
    def getter():
        return (w.width(), w.height())

    res = drain_until_stable(qapp, getter, timeout_ms=500, poll_ms=5, stable_frames=2)
    assert res == (300, 300)
    w.deleteLater()


def test_drain_until_stable_timeout_raises(qapp):
    counter = {"n": 0}

    def flapping():
        counter["n"] += 1
        return counter["n"]  # never stable

    import pytest

    with pytest.raises(AssertionError, match="timeout"):
        drain_until_stable(qapp, flapping, timeout_ms=50, poll_ms=5, stable_frames=2)
