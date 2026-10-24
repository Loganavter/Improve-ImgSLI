"""GUI-thread stall watchdog: decision logic + stack dump shape.

The watchdog exists because a hitch *deferred past its cause* (half a second
after stopping a recording, say) has no probe around the action: the cost is a
queued slot, a debounce flush, a GC pass or a lazy cache build. The tracer shows
a hole in the frame timeline, not a name. ``core/stall_watch`` reports the gap
**and the main thread's Python stack** at the moment the loop is stuck.

These tests pin the parts that can go wrong quietly:

- the report threshold/cooldown logic (one report per episode, no spam during a
  long freeze, nothing below the threshold);
- the stack formatting (frames present vs "blocked in C/C++" when Python is not
  on the stack -- a driver or syscall block, which is a different animal);
- that arming is a no-op without the env flag (zero cost in normal runs).
"""

from __future__ import annotations

import core.stall_watch as sw


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("IMGSLI_STALL_WATCH", raising=False)
    assert sw.enabled() is False
    assert sw.arm() is False


def test_enabled_by_flag(monkeypatch):
    for value in ("1", "true", "yes", "on"):
        monkeypatch.setenv("IMGSLI_STALL_WATCH", value)
        assert sw.enabled() is True
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("IMGSLI_STALL_WATCH", value)
        assert sw.enabled() is False


def test_threshold_defaults_and_override(monkeypatch):
    monkeypatch.delenv("IMGSLI_STALL_THRESHOLD_MS", raising=False)
    assert sw._threshold_ms() == sw.DEFAULT_THRESHOLD_MS
    monkeypatch.setenv("IMGSLI_STALL_THRESHOLD_MS", "900")
    assert sw._threshold_ms() == 900.0
    # never so low that ordinary scheduling jitter reports
    monkeypatch.setenv("IMGSLI_STALL_THRESHOLD_MS", "1")
    assert sw._threshold_ms() >= 50.0
    # garbage falls back to the default rather than crashing the watchdog
    monkeypatch.setenv("IMGSLI_STALL_THRESHOLD_MS", "wat")
    assert sw._threshold_ms() == sw.DEFAULT_THRESHOLD_MS


def test_should_report_one_per_episode(monkeypatch):
    monkeypatch.setattr(sw, "_last_report_at", 0.0, raising=False)
    # below the threshold: silent
    assert sw._should_report(100.0, 250.0, now=10.0) is False
    # a real stall: reported once
    assert sw._should_report(600.0, 250.0, now=10.0) is True
    # immediately after: suppressed by the cooldown (same episode)
    assert sw._should_report(700.0, 250.0, now=10.2) is False
    # a later, separate stall: reported again
    assert sw._should_report(400.0, 250.0, now=12.0) is True


def test_report_includes_frames_when_python_is_on_the_stack():
    text = sw.format_stall_report(520.0, ["  file a.py:1 | foo()", "  file b.py:2 | bar()"])
    assert "blocked 520ms" in text
    assert "a.py:1" in text and "b.py:2" in text
    assert "innermost first" in text


def test_report_says_so_when_blocked_outside_python():
    text = sw.format_stall_report(480.0, [])
    assert "blocked 480ms" in text
    assert "C/C++" in text, (
        "an empty Python stack means the block is in Qt/the driver/a syscall "
        "-- the report must say that instead of looking like a missing dump"
    )


def test_capture_returns_empty_for_unknown_thread():
    assert sw._capture_main_stack(threading_id_that_does_not_exist()) == []


def threading_id_that_does_not_exist() -> int:
    # 0 is never a live thread id in CPython's mapping
    return 0


def test_watchdog_reports_a_real_gui_block(monkeypatch, caplog):
    """End-to-end: a blocked GUI thread produces a report naming the stack.

    This is the property the owner needs -- a hitch *after* an action must be
    attributable, not just visible. The block is a plain ``sleep`` on the GUI
    thread, so the captured stack must point at this test's own frame.
    """
    import logging
    import time

    import pytest

    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # pragma: no cover - Qt missing in a stripped env
        pytest.skip("PySide6 not available")

    caplog.set_level(logging.WARNING, logger="ImproveImgSLI.stall_watch")
    app = QApplication.instance() or QApplication([])

    monkeypatch.setenv("IMGSLI_STALL_WATCH", "1")
    monkeypatch.setenv("IMGSLI_STALL_THRESHOLD_MS", "80")
    sw.disarm()
    sw._armed = False  # allow re-arming in the same process
    assert sw.arm(tick_ms=10) is True
    try:
        # let the beat tick at least once
        started = time.monotonic()
        while time.monotonic() - started < 0.08:
            app.processEvents()
        # block the GUI thread without pumping: this is the "hitch"
        time.sleep(0.4)
        # pump again so any queued log handler runs
        started = time.monotonic()
        while time.monotonic() - started < 0.4:
            app.processEvents()
    finally:
        sw.disarm()

    stalls = [r for r in caplog.records if "gui-loop blocked" in r.getMessage()]
    assert stalls, "the watchdog did not report a 400ms GUI block"
    text = "\n".join(r.getMessage() for r in stalls)
    assert "test_watchdog_reports_a_real_gui_block" in text, (
        "the report must name the blocked Python frame (this test), got:\n" + text
    )
