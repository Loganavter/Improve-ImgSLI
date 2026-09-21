"""Tracer fidelity regressions: nested chains, canvas GC reuse, ring accounting.

Dogma source: task-fix-tracer-fidelity-2026-09-20.
"""

from __future__ import annotations

import gc

from core.tracing import instrumentation as instr_mod
from core.tracing.tracer import Tracer


def test_nested_traces_restore_outer_id():
    tracer = Tracer()
    outer = tracer.begin_trace("outer")
    assert tracer.current_trace_id() == outer
    inner = tracer.begin_trace("inner")
    assert tracer.current_trace_id() == inner
    assert tracer.current_trace_id() != outer
    tracer.end_trace()
    assert tracer.current_trace_id() == outer
    tracer.end_trace()
    assert tracer.current_trace_id() is None


def test_unbalanced_end_trace_fails_open():
    tracer = Tracer()
    tracer.end_trace()  # no begin: must not raise, stays None
    assert tracer.current_trace_id() is None
    tracer.begin_trace("a")
    tracer.end_trace()
    tracer.end_trace()  # double end: fail open
    assert tracer.current_trace_id() is None


def test_records_carry_nested_trace_ids():
    tracer = Tracer()
    outer = tracer.begin_trace("outer")
    tracer.record("test.outer", "outer rec")
    inner = tracer.begin_trace("inner")
    tracer.record("test.inner", "inner rec")
    tracer.end_trace()
    tracer.record("test.outer2", "outer again")
    tracer.end_trace()
    recs = tracer.get_records()
    assert [r.trace_id for r in recs] == [outer, inner, outer]


def test_canvas_baseline_evicted_on_gc():
    class FakeCanvas:
        pass

    canvas = FakeCanvas()
    key = id(canvas)
    instr_mod._remember_plan_baseline(canvas, {"a": "1"})
    assert instr_mod._get_plan_baseline(canvas) == {"a": "1"}
    del canvas
    gc.collect()
    assert key not in instr_mod._LAST_PLAN_BY_CANVAS


def test_canvas_baseline_non_weakrefable_bounded():
    class Slotted:
        __slots__ = ("x",)

    instr_mod._LAST_PLAN_BY_CANVAS.clear()
    instr_mod._CANVAS_BASELINE_REFS.clear()
    try:
        objs = [Slotted() for _ in range(instr_mod._PLAN_BASELINE_CAP + 10)]
        for i, obj in enumerate(objs):
            instr_mod._remember_plan_baseline(obj, {"i": str(i)})
        assert len(instr_mod._LAST_PLAN_BY_CANVAS) <= instr_mod._PLAN_BASELINE_CAP
    finally:
        instr_mod._LAST_PLAN_BY_CANVAS.clear()
        instr_mod._CANVAS_BASELINE_REFS.clear()


def test_ring_overflow_accounted_not_silent():
    tracer = Tracer(ring_size=8)
    for i in range(20):
        tracer.record("test.fill", f"rec {i}")
    assert len(tracer.get_records()) == 8
    assert tracer.dropped_records == 12
    # seq keeps counting across eviction
    assert tracer.get_records()[-1].seq == 20


def test_rank_traces_notes_eviction():
    tracer = Tracer(ring_size=64)
    tid_a = tracer.begin_trace("slow")
    tracer.record("test.a", "a1")
    tracer.end_trace()
    tid_b = tracer.begin_trace("fast")
    tracer.record("test.b", "b1")
    tracer.end_trace()
    ranks = tracer.rank_traces()
    assert {e["trace_id"] for e in ranks} == {tid_a, tid_b}
    assert all(e["dropped"] == 0 for e in ranks)
    assert ranks == sorted(ranks, key=lambda e: -e["total_ms"])
    limited = tracer.rank_traces(top=1)
    assert len(limited) == 1


def test_unsubscribe_api():
    tracer = Tracer()
    seen: list = []
    tracer.subscribe(seen.append)
    tracer.record("test.sub", "one")
    assert len(seen) == 1
    assert tracer.unsubscribe(seen.append) is True
    tracer.record("test.sub", "two")
    assert len(seen) == 1
    assert tracer.unsubscribe(seen.append) is False
