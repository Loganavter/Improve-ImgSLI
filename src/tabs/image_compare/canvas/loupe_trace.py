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
  once per distinct decision signature, not once per frame. Callers that
  pass an explicit per-item ``sig`` for one shared event (e.g. one dropped
  tile each of N non-resident loupe slices, same reason) aggregate further:
  only the first item's line carries the event — same ``(pass_name,
  verdict, reason)`` with a new item sig stays silent. Records are
  unaffected (every hit still appends its per-frame ``FrameDecision``
  with per-item ``ids``), and any genuine reason change emits again, so
  aggregation can never silence a new event, only repeat tiles of one
  already logged.
- ``time`` — mouse flow, ``schedule.py`` recipe: at most one line per
  ``interval_s`` (coords dedup runs on every mouse move).
- ``once`` — dead/legacy paths, ``live_handles.note_skipped_once`` recipe:
  one line per key ever (raster quads without gpu params).

Emitted lines carry the caller's ``ids`` (``ids=(...)`` suffix) whenever
non-empty, so the one surviving line of an aggregated multi-tile drop
still identifies a tile — per-tile ``sig`` values never reach the log
text, which is what used to emit N byte-identical lines for one event.

Records are the per-frame truth: while the flag is on, every hit appends
one ``FrameDecision`` (cheap frozen dataclass) and only the *log line* is
throttled. Flag off → total no-op: no record, no log, identical behavior.
"""

from __future__ import annotations

import time

from tabs.image_compare.debug import (
    ic_invalidate_debug,
    ic_invalidate_debug_enabled,
    ic_loupe_debug,
    ic_loupe_debug_enabled,
)

__all__ = [
    "LOUPE_MOUSE_LOG_INTERVAL_S",
    "THROTTLE_ONCE",
    "THROTTLE_SIG",
    "THROTTLE_TIME",
    "frame_context_from_widget",
    "reset_loupe_trace_state",
    "trace_invalidation",
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
# Last *emitted* (pass_name, verdict, reason) per throttle stream. The
# per-item explicit ``sig`` (e.g. per dropped tile) advances ``_last_sig``
# on every tile, but the log line only fires when the shared event triple
# changes — otherwise N tiles of one drop event collapse into the first
# tile's single line. Default-sig callers are unaffected: their observed
# sig IS the triple, so a change in one is a change in the other.
_last_emitted_base: dict = {}


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
    _last_emitted_base.clear()


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
    An explicit per-item ``sig`` with an unchanged ``(pass_name, verdict,
    reason)`` triple aggregates: the record is still appended, but the
    log line fires only for the first item of the event (with its
    ``ids``), not once per item.
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
            base = (pass_name, verdict, reason)
            if _last_emitted_base.get(stream, _MISSING) != base:
                _last_emitted_base[stream] = base
                emit = True
            # else: same drop event, further tile (explicit per-item sig):
            # aggregate silently — the per-tile record above already holds
            # the identity, and the first tile's line carries it to the log.
    if emit:
        if ids:
            ic_loupe_debug(
                "%s verdict=%s reason=%s ids=%r",
                pass_name,
                verdict,
                reason,
                tuple(ids),
            )
        else:
            ic_loupe_debug("%s verdict=%s reason=%s", pass_name, verdict, reason)
    return decision


def trace_invalidation(
    frame_context,
    source: str,
    reason: str,
    ids: tuple = (),
    *,
    verdict: str = "ran",
    throttle: str = THROTTLE_SIG,
    sig=None,
    key=None,
    interval_s: float = LOUPE_MOUSE_LOG_INTERVAL_S,
):
    """P4 attributed-invalidation bus: record who armed/requested a frame.

    Same recipe as :func:`trace_loupe` but for timer arms, singleShot
    deferrals and external invalidation requests instead of render
    decisions. Gated on ``IMGSLI_IC_INVALIDATE_DEBUG`` (flag off → total
    no-op: no record, no log — steady production pays one env check).
    Flag on → every call appends one ``invalidate.<source>`` FrameDecision
    (per-frame truth, unthrottled) while only the ``[ic-invalidate]`` log
    line is throttled (hot sites: keep-warm ticks, fps-timer dedup-acks).

    ``verdict`` is ``"ran"`` for arms/fires, ``"skipped"`` for dedup-acks,
    stops and idle stand-downs. Returns the ``FrameDecision`` (or ``None``
    when the flag is off / no context — the throttled log still fires so
    attribution survives without a renderer, e.g. label-path presenters).
    """
    if not ic_invalidate_debug_enabled():
        return None
    from engine.frame.context import (
        INVALIDATE_PREFIX,
        VERDICT_RAN,
    )

    decision = None
    if frame_context is not None:
        decision = frame_context.record_invalidation(
            source, reason, ids, verdict=verdict or VERDICT_RAN
        )
    pass_name = f"{INVALIDATE_PREFIX}{source}"
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
        ic_invalidate_debug(
            "%s verdict=%s reason=%s", pass_name, verdict, reason
        )
    return decision
