"""Bounded drain-until-stable helper (W5 deflake).

Replaces single-drain exact-equality geometry asserts that flake due to
deferred layout timers. Polls getter until consecutive snapshots equal or timeout.
"""
from __future__ import annotations

import time
from typing import Callable, Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


def drain_until_stable(
    qapp: QApplication | None = None,
    getter: Callable[[], Any] | None = None,
    *,
    timeout_ms: int = 1000,
    poll_ms: int = 10,
    stable_frames: int = 2,
) -> Any:
    """Process events until getter() returns stable value for stable_frames polls.

    Returns last stable value or raises AssertionError on timeout.

    Each poll spins a real event-loop turn (not just ``processEvents``):
    coalesced channels like ``UiMetrics.changed`` fire through a zero-timer,
    and deferred layout timers need the loop — a ``processEvents``-only drain
    can return while those slots still haven't run (observed full-suite:
    the zero-timer flush lands several turns late under the event backlog).
    """
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None
    assert getter is not None

    deadline = time.monotonic() + timeout_ms / 1000.0
    last = getter()
    stable = 0
    while time.monotonic() < deadline:
        qapp.processEvents()
        loop = QEventLoop()
        QTimer.singleShot(poll_ms, loop.quit)
        loop.exec()
        cur = getter()
        if cur == last:
            stable += 1
            if stable >= stable_frames:
                return cur
        else:
            stable = 0
            last = cur
    raise AssertionError(f"drain_until_stable timeout: last={last!r} cur={cur!r}")
