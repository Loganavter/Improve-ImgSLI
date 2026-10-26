"""Throttled focus logging for hover/focus-driven toolbar buttons.

Why this module exists (owner report 2026-10-26): the magnifier button's event
filter logged every FocusIn/FocusOut and the terminal filled with thousands of
identical lines ~1 ms apart:

    [DEBUG] (transient_magnifier.py:378) [magnifier-visibility] btn_magnifier
    event=9 reason=FocusReason.MouseFocusReason

Focus bursts at kHz are normal for these widgets — a closing window hands focus
back and forth, a popup can re-focus its anchor each frame — so a per-event line
is never useful. One line per (tag, kind, reason) is enough to name the state;
the throttle re-arms after a quiet gap so a *later* burst is still visible.
"""

from __future__ import annotations

import time

#: Same (tag, kind, reason) stays silent for this long. Long enough that a
#: focus loop is one line, short enough that a second, unrelated burst in a
#: session still appears.
FOCUS_LOG_MIN_INTERVAL_S = 3.0

_STATE: dict[str, tuple[tuple, float]] = {}


def log_focus_event(logger, event, tag: str) -> None:
    """Log a focus event at DEBUG, throttled per ``tag`` and event identity."""
    try:
        reason = getattr(event, "reason", lambda: None)()
    except Exception:
        reason = None
    try:
        kind = event.type()
    except Exception:
        return
    sig = (tag, kind, reason)
    now = time.monotonic()
    prev_sig, prev_ts = _STATE.get(tag, (None, 0.0))
    if sig == prev_sig and (now - prev_ts) < FOCUS_LOG_MIN_INTERVAL_S:
        return
    _STATE[tag] = (sig, now)
    logger.debug("%s event=%s reason=%s", tag, kind, reason)
