"""GUI-thread stall watchdog with a stack dump (diagnosis only).

Why: a hitch that appears *after* an action (e.g. half a second after stopping
a recording) is invisible to timing probes wrapped around the action itself --
the cost is deferred work (a queued slot, a debounce flush, a GC pass, a lazy
cache build). The frame/perf tracer shows a *hole*, not a cause.

This watchdog names the cause: the GUI thread bumps a beat every ``tick_ms``;
a daemon thread checks the beat and, when the loop has not moved for
``threshold_ms``, captures the **main thread's Python stack** via
``sys._current_frames()`` and logs the top frames. That turns "it hangs for
half a second" into "it was blocked here".

Armed only with ``IMGSLI_STALL_WATCH=1`` (near-zero cost otherwise: the module
imports are stdlib, and :func:`arm` returns early). Safe to call before or
after the QApplication exists as long as a running Qt event loop is present --
the beat is a ``QTimer`` on the GUI thread.

Read-only by construction: it never touches widgets, never raises into the app
(every hook is guarded), and the stack capture is a read of frames that are
already paused.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import traceback

logger = logging.getLogger("ImproveImgSLI.stall_watch")

#: GUI-thread beat interval.
DEFAULT_TICK_MS = 33
#: A gap at/over this is reported (also the existing gallery watchdog's order of
#: magnitude: 150 ms is already visible, 500 ms reads as "it hung").
DEFAULT_THRESHOLD_MS = 250
#: Frames printed from the blocked stack, outermost-last.
STACK_FRAMES = 14

_state_lock = threading.Lock()
_armed = False
_beat = time.monotonic()
_last_report_at = 0.0
_watchdog: threading.Thread | None = None
_timer_ref = None
_stop = threading.Event()


def enabled() -> bool:
    return os.environ.get("IMGSLI_STALL_WATCH", "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def _threshold_ms() -> float:
    raw = os.environ.get("IMGSLI_STALL_THRESHOLD_MS", "").strip()
    try:
        return max(50.0, float(raw)) if raw else float(DEFAULT_THRESHOLD_MS)
    except ValueError:
        return float(DEFAULT_THRESHOLD_MS)


def format_stall_report(elapsed_ms: float, stack_frames: list[str]) -> str:
    """Log payload: the gap plus the blocked stack (already formatted frames)."""
    head = f"[stall] gui-loop blocked {elapsed_ms:.0f}ms; main-thread stack (innermost first):"
    if not stack_frames:
        return head + "\n  <no Python frames: blocked in C/C++ (Qt, driver, syscall)>"
    return head + "\n" + "\n".join(stack_frames)


def _capture_main_stack(main_thread_id: int) -> list[str]:
    """Read the main thread's frames; never blocks, never mutates."""
    try:
        frame = sys._current_frames().get(main_thread_id)
    except Exception:
        return []
    if frame is None:
        return []
    try:
        lines = traceback.format_stack(frame, limit=STACK_FRAMES)
    except Exception:
        return []
    out: list[str] = []
    for line in lines:
        compact = "  " + " | ".join(part.strip() for part in line.strip().splitlines())
        out.append(compact[:300])
    return out


def _should_report(elapsed_ms: float, threshold_ms: float, now: float) -> bool:
    """One report per stall episode, plus a cooldown so a long freeze is not spam."""
    global _last_report_at
    if elapsed_ms < threshold_ms:
        return False
    if now - _last_report_at < max(1.0, threshold_ms / 1000.0):
        return False
    _last_report_at = now
    return True


def _watch(threshold_ms: float, main_thread_id: int) -> None:
    while not _stop.wait(0.1):
        try:
            elapsed_ms = (time.monotonic() - _beat) * 1000.0
            if _should_report(elapsed_ms, threshold_ms, time.monotonic()):
                logger.warning(
                    "%s", format_stall_report(elapsed_ms, _capture_main_stack(main_thread_id))
                )
        except Exception:
            continue


def arm(*, tick_ms: int = DEFAULT_TICK_MS) -> bool:
    """Start the GUI-thread beat + watchdog. No-op unless the env flag is set."""
    global _armed, _beat, _watchdog, _last_report_at
    if not enabled():
        return False
    if _armed:
        return True
    # Re-arming after disarm() (tests, teardown) must not inherit the old stop
    # event or the previous cooldown stamp: the watchdog would exit silently.
    _stop.clear()
    _last_report_at = 0.0
    _beat = time.monotonic()
    main_thread_id = threading.get_ident()
    try:
        from PySide6.QtCore import QTimer
    except Exception:
        return False
    try:
        timer = QTimer()
        timer.setInterval(max(5, int(tick_ms)))

        def _tick() -> None:
            global _beat
            _beat = time.monotonic()

        timer.timeout.connect(_tick)
        timer.start()
        # Keep a module-level reference: a garbage-collected QTimer stops.
        global _timer_ref
        _timer_ref = timer
    except Exception:
        return False
    threshold_ms = _threshold_ms()
    _watchdog = threading.Thread(
        target=_watch,
        args=(threshold_ms, main_thread_id),
        name="stall-watch",
        daemon=True,
    )
    _watchdog.start()
    _armed = True
    logger.warning(
        "[stall] watchdog armed (tick=%dms, report>%.0fms); %s",
        tick_ms,
        threshold_ms,
        "stack dump on stall",
    )
    return True


def disarm() -> None:
    """Stop the watchdog (tests / teardown)."""
    global _armed, _watchdog, _timer_ref
    _stop.set()
    with _state_lock:
        if _watchdog is not None:
            _watchdog.join(timeout=1.0)
        _watchdog = None
        timer = _timer_ref
        _timer_ref = None
        if timer is not None:
            try:
                timer.stop()
            except Exception:
                pass
        _armed = False
