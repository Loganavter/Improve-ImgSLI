"""Chrome Trace Event exporter for frame spans (Wave B).

Plan: ``plan-engine-perf-debugger-2026-09-20``, Phase 2 (export). Consumes
the Wave A span API on ``FrameContext`` (see ``context.py``) read-only and
serializes it to `Chrome Trace Event`_ JSON openable in Perfetto UI — no
bespoke viewer lives in this repo; Perfetto IS the viewer.

Gate (``IMGSLI_PERF_TRACE``): the gate lives AT THIS EXPORT BOUNDARY.
:func:`write_trace` checks :func:`perf_trace_enabled` (permissive
``shared.debug_flags.env_flag`` semantics: any non-empty value except
``0/false/no/off``) and, when off, writes NOTHING and returns ``0`` —
spans stay collected in the context ring (simply overwritten there) but
are never serialized. Callers (render paths, waves C/D) must NOT
re-implement the check; calling :func:`write_trace` unconditionally is
correct. :func:`perf_trace_enabled` is exposed only for callers that
want to skip building the ``frames`` list itself.

Steady-state cost: zero when the gate is off (this module is not even
called on the hot path); at export, one ``resolved_detail``
materialization per span plus one ``json.dump``. No logging, no timers,
no Qt/GPU imports — stdlib only (``json``, ``os``, ``time``).

Event schema (the Wave B seam — waves C/D consume read-only):

- One span → one Complete event (``ph="X"``):
  ``{"name", "ph": "X", "pid", "tid", "ts", "dur", "args"}``.
- One counter → one Counter event (``ph="C"``) per sampled frame:
  ``{"name", "ph": "C", "pid", "tid", "ts", "args": {name: value}}``.
- Metadata (``ph="M"``): one ``process_name`` event plus one
  ``thread_name`` event per distinct lane.
- One frame's verdicts → one zero-duration ``frame.decisions`` event
  (``ph="X"``) per sampled context with a non-empty decision list:
  ``args.decisions`` is ``[{pass, verdict, reason}]`` (dur 0, so
  stage aggregates and slow-tick accounting are unaffected).

REQUIRED KEYS ``pid``/``tid``/``ts``/``ph`` are present on EVERY event
(metadata events carry ``ts: 0`` — viewers ignore ``ts`` on ``M``
events — purely so the invariant holds literally for validators).

Field mapping:

- ``name`` ← span name (stage, e.g. ``"ic.prepare"``).
- ``tid`` ← span ``frame_id`` (birth frame). One Perfetto lane per
  frame; thread-name metadata labels it ``"frame-N"``. Multi-context
  exports merge lanes by frame id BY DESIGN (both canvas tabs'
  same-tick spans co-visible on one lane).
- ``pid`` ← ``os.getpid()`` (single-process trace; ``t0_ns`` readings
  are process-monotonic — never compare across processes).
- ``ts``/``dur`` ← ``t0_ns``/``t1_ns`` converted ns → µs
  (``round(ns / 1000.0, 3)``); ``dur`` clamped at ``>= 0``.
- ``args`` ← ``{"frame_id": <birth frame>}`` merged with the span's
  ``resolved_detail``. Join keys are preserved by construction: the
  ``frame_id`` atom is always present, and ``wheel-<id>`` passthrough
  atoms (a ``"trace_id": "wheel-…"`` entry placed in ``detail`` by the
  interaction hook) flow through untouched as ordinary args entries.
  The exporter-set ``frame_id`` wins if a detail dict also carries a
  ``"frame_id"`` key.

Detail contract (fail-OPEN — export never crashes on payload):

- Factories that raise → ``args["detail_error"]`` records
  ``"<Type>: <message>"`` and the span is still emitted.
- Non-dict details (str/int/list/…) → ``args["detail"]``.
- Values that are not JSON-serializable (Qt/GPU objects must NEVER
  reach here — detail factories MUST return plain data) are replaced
  by their ``repr()`` instead of raising; dict keys are coerced with
  ``str()``.

File shape: ``{"traceEvents": [...], "displayTimeUnit": "ms"}`` with
metadata events first, then the rest sorted by ``ts``.

.. _Chrome Trace Event:
   https://docs.google.com/document/d/1CvAClvFfyA5R-PhYUmn5OOQtYMH4h6I0nSsKchNAySU
"""

from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Iterable, Mapping

__all__ = [
    "PERF_TRACE_ENV",
    "TRACE_DUMP_EVERY_N_FRAMES",
    "TRACE_PATH_ENV",
    "build_trace",
    "default_trace_path",
    "maybe_dump_trace",
    "perf_trace_enabled",
    "spans_to_events",
    "write_trace",
]

#: Env var gating trace serialization (checked at the export boundary).
PERF_TRACE_ENV = "IMGSLI_PERF_TRACE"

#: Optional override for the dump location used by :func:`maybe_dump_trace`.
TRACE_PATH_ENV = "IMGSLI_PERF_TRACE_PATH"

#: Dump the ring every N rendered frames (steady-state cost: one counter
#: bump per frame; one ``json.dump`` of at most ``SPAN_RING_MAX`` spans
#: every Nth frame — debug-gated path only, never production).
TRACE_DUMP_EVERY_N_FRAMES = 30

#: Off-values mirror ``shared.debug_flags.env_flag`` (permissive flag).
_OFF_VALUES = ("", "0", "false", "no", "off")

#: Required on EVERY event (validators rely on this literally).
REQUIRED_KEYS = ("pid", "tid", "ts", "ph")


def perf_trace_enabled() -> bool:
    """True unless ``IMGSLI_PERF_TRACE`` is unset/empty/``0/false/no/off``.

    Same truth table as ``shared.debug_flags.env_flag`` (re-implemented
    with stdlib ``os`` so this module stays importable without the
    shared package on ``sys.path`` — e.g. standalone analyzer tests).
    """
    return os.environ.get(PERF_TRACE_ENV, "").strip().lower() not in _OFF_VALUES


def _ns_to_us(value: Any) -> float:
    """``perf_counter_ns`` reading → fractional microseconds for ``ts``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(number / 1000.0, 3)


def _json_safe(value: Any) -> Any:
    """Recursively replace non-JSON-serializable values with ``repr()``.

    Plain scalars pass through; dict keys are coerced with ``str()``;
    tuples become lists (JSON has no tuples). Anything ``json`` cannot
    represent (arbitrary objects, sets, …) becomes its ``repr`` string —
    fail-open, never raises.
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        # Non-finite floats are valid Python but invalid strict JSON
        # (Perfetto rejects NaN tokens) — keep them as repr strings.
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    try:
        # Strict probe: allow_nan=False keeps NaN/Infinity (which
        # Perfetto's JSON parser would reject) out of the trace — they
        # become 'nan'/'inf' repr strings instead.
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError):
        return repr(value)
    return value


def _detail_to_args(span: Any, frame_id: int) -> dict[str, Any]:
    """Build event ``args``: ``frame_id`` join key + coerced detail.

    Never raises: factory exceptions become ``detail_error``; exotic
    payloads become ``repr()`` strings via :func:`_json_safe`.
    """
    args: dict[str, Any] = {"frame_id": frame_id}
    try:
        resolved = span.resolved_detail
    except AttributeError:
        # Duck-typed span-like without the Wave A property — use the
        # raw payload (never call it: without the property protocol a
        # callable here is data, not a factory). NOTE: do NOT probe
        # with hasattr() — on real FrameSpans that would invoke the
        # property getter and run lazy factories an extra time,
        # defeating the record-time laziness budget.
        resolved = getattr(span, "detail", None)
        if callable(resolved):
            resolved = repr(resolved)
    except Exception as exc:  # factory blew up — record, don't crash
        args["detail_error"] = f"{type(exc).__name__}: {exc}"
        return args
    if resolved is None:
        return args
    safe = _json_safe(resolved)
    if isinstance(safe, dict):
        for key, value in safe.items():
            if key == "frame_id":
                continue  # exporter-set join key wins (see module docstring)
            args[key] = value
        return args
    args["detail"] = safe
    return args


def spans_to_events(spans: Iterable[Any], pid: int) -> list[dict[str, Any]]:
    """One Chrome Complete event (``ph="X"``) per span (pure, no IO)."""
    events: list[dict[str, Any]] = []
    for span in spans:
        try:
            frame_id = int(span.frame_id)
        except (TypeError, ValueError, AttributeError):
            frame_id = 0
        t0_us = _ns_to_us(getattr(span, "t0_ns", 0))
        t1_us = _ns_to_us(getattr(span, "t1_ns", 0))
        events.append(
            {
                "name": str(getattr(span, "name", "unknown")),
                "ph": "X",
                "pid": pid,
                "tid": frame_id,
                "ts": t0_us,
                "dur": round(max(0.0, t1_us - t0_us), 3),
                "args": _detail_to_args(span, frame_id),
            }
        )
    return events


def _counter_events(
    contexts: Iterable[Any], pid: int, sample_ts_us: float
) -> list[dict[str, Any]]:
    """One Counter event (``ph="C"``) per counter per sampled frame.

    Counters are cumulative per context BY DESIGN (per-frame attribution
    comes from spans); each event samples the running total at export
    time on the lane of the context's current frame.
    """
    events: list[dict[str, Any]] = []
    for ctx in contexts:
        try:
            frame_id = int(ctx.frame_id)
        except (TypeError, ValueError, AttributeError):
            frame_id = 0
        counters = getattr(ctx, "counters", None)
        items = counters.items() if hasattr(counters, "items") else []
        for name, value in items:
            try:
                total = int(value)
            except (TypeError, ValueError):
                total = 0
            key = str(name)
            events.append(
                {
                    "name": key,
                    "ph": "C",
                    "pid": pid,
                    "tid": frame_id,
                    "ts": sample_ts_us,
                    "args": {key: total},
                }
            )
    return events


def _decision_events(
    contexts: Iterable[Any], pid: int, sample_ts_us: float
) -> list[dict[str, Any]]:
    """One zero-duration event per context carrying its frame verdicts.

    Spans say how LONG each stage took; decisions say what each pass
    DECIDED (fallback promoted/held + why, ran/skipped, more_pending,
    cascade_pending). Without these a timeline cannot distinguish "tier
    promoted with a dirty cascade" from "mixed grid under more_pending"
    — the exact question behind the first-zoom tile seam (2026-09-20).
    Empty decision lists emit nothing. ``ids`` atoms are repr'd (they
    may reference engine objects — never interpreted here).
    """
    events: list[dict[str, Any]] = []
    for ctx in contexts:
        try:
            frame_id = int(ctx.frame_id)
        except (TypeError, ValueError, AttributeError):
            frame_id = 0
        windows: list[tuple[int, Any]] = [(frame_id, getattr(ctx, "decisions", ()))]
        for past_id, past_ds in getattr(ctx, "past_decisions", ()):
            try:
                windows.append((int(past_id), past_ds))
            except (TypeError, ValueError):
                continue
        for window_id, window_ds in windows:
            verdicts = []
            for decision in window_ds or ():
                verdicts.append(
                    {
                        "pass": str(getattr(decision, "pass_name", "?")),
                        "verdict": str(getattr(decision, "verdict", "?")),
                        "reason": str(getattr(decision, "reason", "")),
                    }
                )
            if verdicts:
                events.append(
                    {
                        "name": "frame.decisions",
                        "ph": "X",
                        "pid": pid,
                        "tid": window_id,
                        "ts": sample_ts_us,
                        "dur": 0,
                        "args": {"frame_id": window_id, "decisions": verdicts},
                    }
                )
    return events


def build_trace(frames: Iterable[Any], pid: int | None = None) -> list[dict[str, Any]]:
    """Build the full event list for ``frames`` (pure, gate NOT checked).

    ``frames`` is an iterable of ``FrameContext`` (each = one sampled
    frame/tick); every context contributes its ring spans plus one
    Counter event per counter. Use :func:`write_trace` for the gated
    file-writing path; use this directly in tests or when the caller
    already checked :func:`perf_trace_enabled`.
    """
    contexts = list(frames)
    own_pid = os.getpid() if pid is None else pid
    spans: list[Any] = []
    for ctx in contexts:
        spans.extend(ctx.spans)
    sample_ts_us = _ns_to_us(time.perf_counter_ns())
    tids = sorted({int(s.frame_id) for s in spans if hasattr(s, "frame_id")})
    events: list[dict[str, Any]] = [
        {
            "name": "process_name",
            "ph": "M",
            "pid": own_pid,
            "tid": 0,
            "ts": 0,
            "args": {"name": "Improve-ImgSLI"},
        }
    ]
    for tid in tids:
        events.append(
            {
                "name": "thread_name",
                "ph": "M",
                "pid": own_pid,
                "tid": tid,
                "ts": 0,
                "args": {"name": f"frame-{tid}"},
            }
        )
    rest = spans_to_events(spans, own_pid)
    rest.extend(_counter_events(contexts, own_pid, sample_ts_us))
    rest.extend(_decision_events(contexts, own_pid, sample_ts_us))
    rest.sort(key=lambda event: event["ts"])
    events.extend(rest)
    return events


def write_trace(path: Any, frames: Iterable[Any]) -> int:
    """Serialize ``frames`` to Chrome Trace JSON at ``path`` (gated).

    Returns the event count written. When ``IMGSLI_PERF_TRACE`` is off,
    writes NOTHING (no file created/truncated) and returns ``0`` — the
    gate lives here, at the export boundary, so callers simply call
    this unconditionally. File IO errors propagate (caller-visible);
    payload problems never do (fail-open per :func:`_detail_to_args`).
    """
    if not perf_trace_enabled():
        return 0
    events = build_trace(frames)
    payload = {"traceEvents": events, "displayTimeUnit": "ms"}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.write("\n")
    return len(events)


def default_trace_path() -> str:
    """Where :func:`maybe_dump_trace` writes (override via env).

    Default is pid-suffixed in ``/tmp`` so concurrent app instances never
    clobber each other; set ``IMGSLI_PERF_TRACE_PATH`` for a fixed path.
    """
    override = os.environ.get(TRACE_PATH_ENV)
    if override:
        return override
    return f"/tmp/imgsli-perf-trace-{os.getpid()}.json"


def maybe_dump_trace(
    frame_context: Any,
    every: int = TRACE_DUMP_EVERY_N_FRAMES,
    path: str | None = None,
) -> int:
    """Serialize the context ring periodically + shortly after wheel input.

    Call unconditionally at the end of every render: bumps the context's
    ``perf_trace_tick`` counter and delegates to :func:`write_trace`
    (which checks the ``IMGSLI_PERF_TRACE`` gate — off means no file,
    return 0) when either the N-frame schedule hits OR a wheel tick
    arrived since the last dump and at least 3 frames have passed (so
    short open-zoom-close sessions still leave a file: the ring holds
    the burst frames). Returns the event count written (0 off-schedule
    or gated off). Open the result in Perfetto UI.
    """
    tick = frame_context.bump("perf_trace_tick")
    wheel = frame_context.count("ic.wheel_tick") + frame_context.count(
        "mc.wheel_tick"
    )
    last_tick = frame_context.counters.get("perf_trace_dump_tick", 0)
    last_wheel = frame_context.counters.get("perf_trace_dump_wheel", 0)
    if tick - last_tick >= every or (
        wheel > last_wheel and tick - last_tick >= 3
    ):
        frame_context.counters["perf_trace_dump_tick"] = tick
        frame_context.counters["perf_trace_dump_wheel"] = wheel
        return write_trace(path or default_trace_path(), [frame_context])
    return 0
