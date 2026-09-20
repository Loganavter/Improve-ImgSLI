# Audit-Meta: pattern=leaf-collector-tests reason="Wave A span API pins: nesting, exception safety, ring bound, decisions frozen"
"""Wave A span-API pins (plan-engine-perf-debugger-2026-09-20, Phase 1).

relates_to: [src/engine/frame/context.py, docs/dev/TRACING.md]

Covers the additive span surface on ``FrameContext`` — ``FrameSpan``,
``span()``, ``counters``/``bump()``/``count()``, the ``SPAN_RING_MAX``
ring — while pinning the frozen decisions API (``record`` /
``record_invalidation`` / ``reset`` / ``begin_frame`` / ``dump`` /
``snapshot_last_frame``) byte-for-byte in behavior: zero draw-behavior
change, spans never touch the Store or the EventBus (frame-local facts,
not state — dispatch-only mutation, changed-guard emits, fail-open
decode and single-flight all live on unchanged paths this file never
imports).
"""

from __future__ import annotations

import time

import pytest

from engine.frame.context import (
    SPAN_RING_MAX,
    FrameContext,
    FrameSpan,
)


def _fresh() -> FrameContext:
    return FrameContext()


def test_span_records_name_times_and_birth_frame():
    ctx = _fresh()
    ctx.reset()  # frame 1: renderer-equivalent entry
    with ctx.span("ic.prepare"):
        pass
    (span,) = ctx.spans
    assert isinstance(span, FrameSpan)
    assert span.name == "ic.prepare"
    assert span.frame_id == ctx.frame_id == 1
    assert span.t1_ns >= span.t0_ns
    assert span.duration_ns == span.t1_ns - span.t0_ns
    assert span.detail is None
    assert span.resolved_detail is None


def test_span_nesting_shares_birth_frame_and_nests_times():
    ctx = _fresh()
    with ctx.span("outer"):
        with ctx.span("inner"):
            pass
    assert [s.name for s in ctx.spans] == ["inner", "outer"]
    outer, inner = ctx.spans[1], ctx.spans[0]
    assert outer.frame_id == inner.frame_id == ctx.frame_id
    # Inner wall interval nests inside the outer one.
    assert outer.t0_ns <= inner.t0_ns
    assert inner.t1_ns <= outer.t1_ns


def test_span_exception_safety_records_then_reraises():
    ctx = _fresh()

    class Boom(Exception):
        pass

    with pytest.raises(Boom):
        with ctx.span("ic.submit"):
            raise Boom()
    (span,) = ctx.spans
    assert span.name == "ic.submit"
    assert span.t1_ns >= span.t0_ns


def test_detail_factory_is_lazy_and_plain_values_pass_through():
    ctx = _fresh()
    calls: list[int] = []

    def factory():
        calls.append(1)
        return {"tiles": 4}

    with ctx.span("ic.realize", detail=factory):
        assert calls == [], "factory must not run at record time"
    (span,) = ctx.spans
    assert calls == [], "factory must not run at span close either"
    assert span.resolved_detail == {"tiles": 4}
    assert calls == [1]

    with ctx.span("plain", detail="already-materialized"):
        pass
    assert ctx.spans[1].resolved_detail == "already-materialized"


def test_retention_ring_bound_respected_under_burst():
    ctx = _fresh()
    burst = SPAN_RING_MAX + 500
    for i in range(burst):
        with ctx.span(f"stage-{i}"):
            pass
    spans = ctx.spans
    assert len(spans) == SPAN_RING_MAX
    # Oldest-first ring: the first 500 were evicted, the tail survived.
    assert spans[0].name == "stage-500"
    assert spans[-1].name == f"stage-{burst - 1}"


def test_spans_survive_reset_and_group_by_birth_frame():
    ctx = _fresh()
    with ctx.span("frame0-work"):
        pass
    ctx.reset()
    with ctx.span("frame1-work"):
        pass
    assert [s.frame_id for s in ctx.spans] == [0, 1]
    assert [s.name for s in ctx.spans_for_frame(0)] == ["frame0-work"]
    assert [s.name for s in ctx.spans_for_frame(1)] == ["frame1-work"]
    assert ctx.spans_for_frame(999) == []


def test_counters_bump_count_and_survive_reset():
    ctx = _fresh()
    assert ctx.count("missing") == 0
    assert ctx.bump("wheel-tick") == 1
    assert ctx.bump("wheel-tick") == 2
    assert ctx.count("wheel-tick") == 2
    assert ctx.bump("other", amount=5) == 5
    assert ctx.counters == {"wheel-tick": 2, "other": 5}
    ctx.reset()
    assert ctx.count("wheel-tick") == 2, "counters are cumulative, not per-frame"


def test_decisions_api_unchanged_by_spans():
    ctx = _fresh()
    with ctx.span("ic.prepare"):
        decision = ctx.record("mag_gate", "ran", "zoom>=1", ids=("frame=0",))
    assert len(ctx) == 1
    assert list(ctx) == [decision]
    assert "mag_gate" in ctx.dump()
    with pytest.raises(ValueError):
        ctx.record("mag_gate", "bogus", "reason")
    ctx.reset()
    assert len(ctx) == 0
    assert ctx.dump() == ""
    # reset() clears decisions but keeps the span window and counters.
    assert [s.name for s in ctx.spans] == ["ic.prepare"]
    assert ctx.begin_frame() == ctx.frame_id


def test_snapshot_last_frame_still_decisions_only():
    from engine.frame.context import (
        last_frame_snapshot,
        snapshot_last_frame,
    )

    ctx = _fresh()
    with ctx.span("ic.prepare"):
        pass
    ctx.record("fallback", "skipped", "atomic hit")
    snapshot_last_frame(ctx)
    snapshot = last_frame_snapshot()
    assert snapshot is not None
    assert [d.pass_name for d in snapshot] == ["fallback"]


def test_span_overhead_order_of_magnitude():
    # Budget (see module docstring): two perf_counter_ns + one small
    # frozen-dataclass append per span — no formatting, no logging, no
    # payload work at record time. Real cost is ~10^-7 s/pair; the bound
    # below (10us mean) is ~2 orders of margin so CI scheduling jitter
    # can never flake it — it pins the *scale*, not the machine.
    ctx = _fresh()
    reps = 2000
    for _ in range(100):
        with ctx.span("warmup"):
            pass
    ctx._spans.clear()  # keep the warmup out of the measurement window
    t0 = time.perf_counter_ns()
    for _ in range(reps):
        with ctx.span("probe"):
            pass
    mean_ns = (time.perf_counter_ns() - t0) / reps
    assert mean_ns < 10_000, f"span open/close mean {mean_ns:.0f}ns exceeds 10us budget"
    assert all(s.t1_ns >= s.t0_ns for s in ctx.spans)


def test_decisions_property_snapshot():
    ctx = FrameContext()
    assert ctx.decisions == ()
    ctx.record("prepare_frame", "ran", "ok", ids=("frame=1",))
    snap = ctx.decisions
    assert len(snap) == 1 and snap[0].pass_name == "prepare_frame"
    assert isinstance(snap, tuple)
    ctx.reset()
    assert ctx.decisions == ()
    assert len(snap) == 1  # earlier snapshot unaffected by reset


def test_past_decisions_window_bounded():
    from engine.frame.context import PAST_DECISIONS_MAX

    ctx = FrameContext()
    for n in range(PAST_DECISIONS_MAX + 5):
        ctx.record("fallback", "ran", f"r{n}", ids=(f"frame={n}",))
        ctx.reset()
    past = ctx.past_decisions
    assert len(past) == PAST_DECISIONS_MAX
    assert [fid for fid, _ in past] == list(
        range(5, 5 + PAST_DECISIONS_MAX)
    )
    assert past[0][1][0].reason == "r5"
    assert isinstance(past, tuple)


def test_empty_frames_skip_window():
    ctx = FrameContext()
    ctx.reset()
    ctx.reset()
    assert ctx.past_decisions == ()
    ctx.record("prepare_frame", "skipped", "x", ids=("frame=2",))
    ctx.reset()
    assert [fid for fid, _ in ctx.past_decisions] == [2]
