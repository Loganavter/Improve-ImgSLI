"""Bounded drain-until-stable helper (W5 deflake).

Replaces single-drain exact-equality geometry asserts that flake due to
deferred layout timers. Polls getter until consecutive snapshots equal or timeout.
"""
from __future__ import annotations

from typing import Callable, Any

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
    """
    if qapp is None:
        qapp = QApplication.instance()
    assert qapp is not None
    assert getter is not None
    import time

    deadline = time.monotonic() + timeout_ms / 1000.0
    last = getter()
    stable = 0
    while time.monotonic() < deadline:
        # process pending events
        qapp.processEvents()
        # also handle singleShot timers: need small sleep? processEvents already does
        cur = getter()
        if cur == last:
            stable += 1
            if stable >= stable_frames:
                return cur
        else:
            stable = 0
            last = cur
        # avoid busy spin
        time.sleep(poll_ms / 1000.0)
    raise AssertionError(f"drain_until_stable timeout: last={last!r} cur={cur!r}")
