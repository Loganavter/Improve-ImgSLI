# Audit-Meta: pattern=leaf-collector reason="P3 render-core consolidation: throttled [ic-loupe] record helper, stdlib-only leaf, no timers/threads"
"""``[ic-loupe]`` trace helper: FrameContext records + throttled log lines.

Phase P3 of plan-render-core-consolidation-2026-09-13. The 8 M1 silent
decisions (mag-gate excluded — P1A already records it — plus the 3
``scene_update`` early returns, the magnifier texture choice, the slot
dedup, the coord dedup and the dropped non-resident slices) record here as
``loupe.*`` FrameContext decisions instead of staying silent.

Throttle recipes (copied, not shared — each site keeps its own state like
the existing per-module ``_last_*_sig`` globals):
- ``sig`` — per-frame path, ``draw_plan.py`` recipe: the log line fires
  once per distinct decision signature, not once per frame.
- ``time`` — mouse flow, ``schedule.py`` recipe: at most one line per
  ``interval_s`` (coords dedup runs on every mouse move).
- ``once`` — dead/legacy paths, ``live_handles.note_skipped_once`` recipe:
  one line per key ever (raster quads without gpu params).

Records are the per-frame truth: while the flag is on, every hit appends
one ``FrameDecision`` (cheap frozen dataclass) and only the *log line* is
throttled. Flag off → total no-op: no record, no log, identical behavior.
"""

from __future__ import annotations

import time

from tabs.image_compare.debug import ic_loupe_debug, ic_loupe_debug_enabled

__all__ = [
    "LOUPE_MOUSE_LOG_INTERVAL_S",
    "THROTTLE_ONCE",
    "THROTTLE_SIG",
    "THROTTLE_TIME",
    "frame_context_from_widget",
    "reset_loupe_trace_state",
    "trace_loupe",
]

THROTTLE_SIG = "sig"
THROTTLE_TIME = "time"
THROTTLE_ONCE = "once"

#: Mouse-flow log cadence for ``throttle="time"`` (schedule.py armed-log
#: recipe is 0.5s; coords dedup is hotter — mouse-move driven — so 2s).
LOUPE_MOUSE_LOG_INTERVAL_S = 2.0

_MISSING = object()

# Per-key throttle state. Module globals like every other throttle site
# (draw_plan._last_gap_draw_plan_sig, fallback._last_renderer_fallback_sig):
# keyed so all 8 points share one mechanism without sharing one sig.
_last_sig: dict = {}
_last_time: dict = {}
_seen_once: set = set()


def frame_context_from_widget(widget):
    """Best-effort live FrameContext via ``widget._rhi_renderer``.

    Lets render-adjacent writers (magnifier pass, overlay setters,
    scene rebuild) record without renderer rewiring: the P1A context is
    born on ``RhiCanvasRenderer`` and reused per frame, so reading it
    through the widget is purely additive. ``None`` for fakes/widgets
    without a renderer — callers then log-only (or stay silent).
    """
    renderer = getattr(widget, "_rhi_renderer", None)
    return getattr(renderer, "frame_context", None)


def reset_loupe_trace_state() -> None:
    """Clear all throttle state (tests only — production throttles live on)."""
    _last_sig.clear()
    _last_time.clear()
    _seen_once.clear()


def trace_loupe(
    frame_context,
    pass_name: str,
    verdict: str,
    reason: str,
    ids: tuple = (),
    *,
    throttle: str = THROTTLE_SIG,
    sig=None,
    key=None,
    interval_s: float = LOUPE_MOUSE_LOG_INTERVAL_S,
):
    """Record one loupe decision + emit its throttled ``[ic-loupe]`` line.

    Returns the ``FrameDecision`` (or ``None`` when the flag is off / no
    context). ``sig`` defaults to ``(pass_name, verdict, reason)``;
    ``key`` defaults to ``pass_name`` — pass an explicit key when one
    pass_name has independent throttle streams (e.g. per quad index).
    """
    if not ic_loupe_debug_enabled():
        return None
    decision = None
    if frame_context is not None:
        decision = frame_context.record(pass_name, verdict, reason, ids)
    emit = False
    stream = key if key is not None else pass_name
    if throttle == THROTTLE_ONCE:
        if stream not in _seen_once:
            _seen_once.add(stream)
            emit = True
    elif throttle == THROTTLE_TIME:
        now = time.monotonic()
        last = _last_time.get(stream, _MISSING)
        if last is _MISSING or (now - last) >= float(interval_s):
            _last_time[stream] = now
            emit = True
    else:
        observed = sig if sig is not None else (pass_name, verdict, reason)
        if _last_sig.get(stream, _MISSING) != observed:
            _last_sig[stream] = observed
            emit = True
    if emit:
        ic_loupe_debug("%s verdict=%s reason=%s", pass_name, verdict, reason)
    return decision
