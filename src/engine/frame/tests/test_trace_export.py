"""Wave B export/analyzer pins (plan-engine-perf-debugger-2026-09-20, Phase 2).

relates_to: [src/engine/frame/trace_export.py, src/devtools/analyze_perf_trace.py]

Pins the Wave B seam waves C/D consume read-only: ``trace_export``
writes valid Chrome Trace JSON (required keys ``pid``/``tid``/``ts``/
``ph`` on EVERY event, ``frame_id`` join + ``wheel-<id>`` passthrough
atoms preserved into ``args``, fail-open details, ``IMGSLI_PERF_TRACE``
gate at the export boundary) and ``analyze_perf_trace`` validates +
pre-aggregates it (per-stage p50/p95/max, slow-tick flags, non-zero
exit on invalid schema).
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from devtools.analyze_perf_trace import (
    format_report,
    load_trace,
    main as analyzer_main,
    slow_ticks,
    stage_stats,
    validate_events,
)
from engine.frame.context import FrameContext
from engine.frame.trace_export import (
    PERF_TRACE_ENV,
    TRACE_DUMP_EVERY_N_FRAMES,
    TRACE_PATH_ENV,
    build_trace,
    default_trace_path,
    maybe_dump_trace,
    perf_trace_enabled,
    spans_to_events,
    write_trace,
)


@pytest.fixture
def trace_on(monkeypatch):
    """Gate on for the duration of one test."""
    monkeypatch.setenv(PERF_TRACE_ENV, "1")
    assert perf_trace_enabled()
    return True


@pytest.fixture
def trace_off(monkeypatch):
    """Gate off for the duration of one test."""
    monkeypatch.delenv(PERF_TRACE_ENV, raising=False)
    assert not perf_trace_enabled()
    return True


def _two_frame_ctx() -> FrameContext:
    """One context with spans born in two frames + counters + join atoms."""
    ctx = FrameContext()
    with ctx.span("ic.prepare", detail={"trace_id": "wheel-abc123", "tiles": 4}):
        with ctx.span("ic.realize", detail=lambda: {"lod": 2}):
            pass
    ctx.bump("wheel-tick")
    ctx.reset()  # frame 1
    with ctx.span("ic.submit", detail="present-proxy"):
        pass
    ctx.bump("wheel-tick")
    return ctx


def _write_two_frame_trace(tmp_path) -> object:
    ctx = _two_frame_ctx()
    path = tmp_path / "trace.json"
    count = write_trace(path, [ctx])
    assert count > 0
    return path


def _load_events(path) -> list:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    assert set(data) == {"traceEvents", "displayTimeUnit"}
    return data["traceEvents"]


# ---------------------------------------------------------------------------
# Export schema
# ---------------------------------------------------------------------------


def test_export_schema_required_keys_on_every_event(tmp_path, trace_on):
    path = _write_two_frame_trace(tmp_path)
    events = _load_events(path)
    assert validate_events(events) == []
    for event in events:
        for key in ("pid", "tid", "ts", "ph"):
            assert key in event, f"{event.get('name')!r} missing {key!r}"
    complete = [e for e in events if e["ph"] == "X"]
    assert {e["name"] for e in complete} == {"ic.prepare", "ic.realize", "ic.submit"}
    for event in complete:
        assert isinstance(event["dur"], (int, float))
        assert event["dur"] >= 0
        assert event["args"]["frame_id"] == event["tid"]


def test_frame_id_join_and_wheel_passthrough_atoms(tmp_path, trace_on):
    path = _write_two_frame_trace(tmp_path)
    events = _load_events(path)
    by_name = {e["name"]: e for e in events if e["ph"] == "X"}
    prepare = by_name["ic.prepare"]
    assert prepare["tid"] == 0
    assert prepare["args"]["frame_id"] == 0
    assert prepare["args"]["trace_id"] == "wheel-abc123"
    assert prepare["args"]["tiles"] == 4
    assert by_name["ic.realize"]["args"]["lod"] == 2
    assert by_name["ic.submit"]["tid"] == 1
    assert by_name["ic.submit"]["args"]["detail"] == "present-proxy"


def test_counter_events_sample_cumulative_totals(tmp_path, trace_on):
    path = _write_two_frame_trace(tmp_path)
    events = _load_events(path)
    counters = [e for e in events if e["ph"] == "C"]
    assert len(counters) == 1
    (event,) = counters
    assert event["name"] == "wheel-tick"
    assert event["args"] == {"wheel-tick": 2}
    assert event["tid"] == 1  # sampled on the lane of the current frame


def test_round_trip_nested_exception_lazy_unserializable(tmp_path, trace_on):
    ctx = FrameContext()
    calls: list[int] = []

    def lazy():
        calls.append(1)
        return {"built": "at-export"}

    class Widget:
        def __repr__(self) -> str:  # noqa: D105 (stable probe repr)
            return "<Widget live-gpu-object>"

    def bad_factory():
        raise RuntimeError("boom")

    with ctx.span("outer", detail=lazy):
        assert calls == [], "factory must not run at record time"
        with pytest.raises(ValueError), ctx.span("inner-fail"):
            raise ValueError("render blew up")
    with ctx.span("opaque", detail=Widget()):
        pass
    with ctx.span("bad-detail", detail=bad_factory):
        pass
    assert calls == [], "factories must not run before export"

    path = tmp_path / "trace.json"
    assert write_trace(path, [ctx]) > 0
    assert calls == [1], "lazy factory materialized exactly once at export"

    events = _load_events(path)
    assert validate_events(events) == []
    by_name = {e["name"]: e for e in events if e["ph"] == "X"}
    assert by_name["outer"]["args"]["built"] == "at-export"
    assert by_name["inner-fail"]["args"]["frame_id"] == 0  # recorded, reraised
    assert by_name["opaque"]["args"]["detail"] == "<Widget live-gpu-object>"
    assert by_name["bad-detail"]["args"]["detail_error"] == "RuntimeError: boom"


def test_nan_detail_stays_strict_json(tmp_path, trace_on):
    ctx = FrameContext()
    with ctx.span("ratio", detail={"hit_ratio": float("nan")}):
        pass
    path = tmp_path / "trace.json"
    write_trace(path, [ctx])
    strict = json.loads(path.read_text(encoding="utf-8"), parse_constant=str)
    (event,) = [e for e in strict["traceEvents"] if e["ph"] == "X"]
    assert event["args"]["hit_ratio"] == "nan"


def test_detail_frame_id_key_never_shadows_join_key(tmp_path, trace_on):
    ctx = FrameContext()
    with ctx.span("sneaky", detail={"frame_id": 999, "ok": True}):
        pass
    path = tmp_path / "trace.json"
    write_trace(path, [ctx])
    (event,) = [e for e in _load_events(path) if e["ph"] == "X"]
    assert event["args"]["frame_id"] == 0
    assert event["args"]["ok"] is True


def test_gate_off_writes_nothing(tmp_path, trace_off, monkeypatch):
    ctx = _two_frame_ctx()
    assert len(ctx.spans) > 0, "spans still collected while gated off"
    path = tmp_path / "trace.json"
    assert write_trace(path, [ctx]) == 0
    assert not path.exists()
    # Explicit off-values all behave the same.
    for off in ("0", "false", "no", "off", ""):
        monkeypatch.setenv(PERF_TRACE_ENV, off)
        assert not perf_trace_enabled()
        assert write_trace(path, [ctx]) == 0
    assert not path.exists()


def test_spans_to_events_is_pure_and_gate_free():
    ctx = _two_frame_ctx()
    events = spans_to_events(ctx.spans, pid=4242)
    # Ring order is close-order (inner closes first), NOT ts order —
    # sorting is build_trace's job (asserted in the metadata test).
    assert [e["name"] for e in events] == ["ic.realize", "ic.prepare", "ic.submit"]
    assert all(e["pid"] == 4242 and e["ph"] == "X" for e in events)


def test_build_trace_metadata_lanes_keep_schema(tmp_path, trace_on):
    events = build_trace([_two_frame_ctx()], pid=7)
    assert validate_events(events) == []
    meta = [e for e in events if e["ph"] == "M"]
    assert meta[0]["name"] == "process_name"
    lanes = {e["tid"]: e["args"]["name"] for e in meta if e["name"] == "thread_name"}
    assert lanes == {0: "frame-0", 1: "frame-1"}
    assert all(e["ts"] == 0 for e in meta)  # invariant filler, viewers ignore


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


def _fixture_events() -> list:
    """Hand-computable fixture: 4 samples of stage 'a' + 1 of 'b' (µs)."""
    return [
        {"name": "a", "ph": "X", "pid": 1, "tid": 0, "ts": 0.0, "dur": 1000.0,
         "args": {"frame_id": 0}},
        {"name": "a", "ph": "X", "pid": 1, "tid": 0, "ts": 2.0, "dur": 2000.0,
         "args": {"frame_id": 0}},
        {"name": "a", "ph": "X", "pid": 1, "tid": 1, "ts": 5.0, "dur": 30000.0,
         "args": {"frame_id": 1}},
        {"name": "a", "ph": "X", "pid": 1, "tid": 1, "ts": 40.0, "dur": 4000.0,
         "args": {"frame_id": 1}},
        {"name": "b", "ph": "X", "pid": 1, "tid": 1, "ts": 45.0, "dur": 500.0,
         "args": {"frame_id": 1}},
        {"name": "wheel-tick", "ph": "C", "pid": 1, "tid": 1, "ts": 46.0,
         "args": {"wheel-tick": 2}},
    ]


def test_analyzer_stats_correctness_on_fixture():
    stats = stage_stats(_fixture_events())
    # stage a durs (ms): [1, 2, 4, 30] — nearest-rank p50=rank2=2.0.
    assert stats["a"]["count"] == 4
    assert stats["a"]["total_ms"] == pytest.approx(37.0)
    assert stats["a"]["p50_ms"] == pytest.approx(2.0)
    assert stats["a"]["p95_ms"] == pytest.approx(30.0)
    assert stats["a"]["max_ms"] == pytest.approx(30.0)
    assert stats["b"] == {
        "count": 1, "total_ms": pytest.approx(0.5),
        "p50_ms": pytest.approx(0.5), "p95_ms": pytest.approx(0.5),
        "max_ms": pytest.approx(0.5),
    }


def test_analyzer_flags_slow_tick_with_dominant_stage():
    slow = slow_ticks(_fixture_events(), budget_ms=25.0)
    assert len(slow) == 1
    (tick,) = slow
    assert tick["tid"] == 1
    assert tick["total_ms"] == pytest.approx(34.5)
    assert tick["dominant"] == "a"
    assert tick["dominant_ms"] == pytest.approx(34.0)
    assert slow_ticks(_fixture_events(), budget_ms=100.0) == []


def test_analyzer_rejects_invalid_schema():
    bad = [
        {"name": "a", "ph": "X", "pid": 1, "tid": 0, "ts": 0.0},  # no dur
        {"name": "b", "pid": 1, "tid": 0, "ts": 1.0, "dur": 2.0},  # no ph
        {"ph": "X", "pid": 1, "tid": 0, "ts": 2.0},  # no name/dur
    ]
    errors = validate_events(bad)
    assert len(errors) == 4  # event #2 fails twice (no name AND no dur)
    assert validate_events(_fixture_events()) == []


def test_analyzer_cli_round_trip_and_exit_codes(tmp_path, trace_on, capsys):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"traceEvents": _fixture_events()}), encoding="utf-8")
    assert analyzer_main([str(good)]) == 0
    out = capsys.readouterr().out
    assert "a count=4" in out
    assert "p95=30.000ms" in out
    assert "dominant=a" in out

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"name": "a", "pid": 1}]), encoding="utf-8")
    assert analyzer_main([str(bad)]) == 2

    missing = tmp_path / "missing.json"
    assert analyzer_main([str(missing)]) == 1

    not_json = tmp_path / "not.json"
    not_json.write_text("{nope", encoding="utf-8")
    assert analyzer_main([str(not_json)]) == 2


def test_analyzer_accepts_bare_array_and_reports_counts(tmp_path):
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps(_fixture_events()), encoding="utf-8")
    events = load_trace(bare)
    report = format_report(bare, events)
    assert "events: 6 (X=5 C=1 M=0 other=0)" in report
    with pytest.raises(ValueError, match="traceEvents"):
        empty_obj = tmp_path / "empty.json"
        empty_obj.write_text(json.dumps({"foo": 1}), encoding="utf-8")
        load_trace(empty_obj)


def test_no_qt_or_gpu_imports_in_new_modules():
    for module_path in (
        "src/engine/frame/trace_export.py",
        "src/devtools/analyze_perf_trace.py",
    ):
        text = open(module_path, encoding="utf-8").read()
        for banned in ("PySide", "PyQt", "qtpy", "OpenGL", "vulkan", "site-packages"):
            assert banned not in text, f"{module_path} mentions {banned}"
        for forbidden in ("import logging", "from logging", "getLogger"):
            assert forbidden not in text, f"{module_path} logs on hot path"


def test_gate_env_name_and_os_level_semantics(monkeypatch):
    assert PERF_TRACE_ENV == "IMGSLI_PERF_TRACE"
    monkeypatch.setenv(PERF_TRACE_ENV, "yes")
    assert perf_trace_enabled()
    monkeypatch.setenv(PERF_TRACE_ENV, " 1 ")
    assert perf_trace_enabled()
    monkeypatch.delenv(PERF_TRACE_ENV, raising=False)
    assert not perf_trace_enabled()
    assert os.environ.get(PERF_TRACE_ENV, "") == ""


def test_default_trace_path_override(monkeypatch, tmp_path):
    custom = tmp_path / "custom.json"
    monkeypatch.setenv(TRACE_PATH_ENV, str(custom))
    assert default_trace_path() == str(custom)
    monkeypatch.delenv(TRACE_PATH_ENV, raising=False)
    default = default_trace_path()
    assert default.startswith(
        os.path.join(tempfile.gettempdir(), "imgsli-perf-trace-")
    )
    assert default.endswith(".json")


def test_maybe_dump_trace_gated_off_writes_nothing(trace_off, tmp_path):
    ctx = FrameContext()
    out = tmp_path / "t.json"
    # Off-schedule ticks bump the counter but write nothing.
    assert maybe_dump_trace(ctx, every=3, path=str(out)) == 0
    assert maybe_dump_trace(ctx, every=3, path=str(out)) == 0
    # On-schedule tick still writes nothing while gated off.
    assert maybe_dump_trace(ctx, every=1, path=str(out)) == 0
    assert not out.exists()
    assert ctx.count("perf_trace_tick") == 3


def test_maybe_dump_trace_writes_every_nth(trace_on, tmp_path):
    ctx = FrameContext()
    with ctx.span("ic.prepare", detail={"trace_id": "wheel-1-1"}):
        pass
    out = tmp_path / "t.json"
    assert maybe_dump_trace(ctx, every=2, path=str(out)) == 0
    assert not out.exists()
    n = maybe_dump_trace(ctx, every=2, path=str(out))
    assert n > 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["traceEvents"]) == n
    assert payload["displayTimeUnit"] == "ms"
    assert ctx.count("perf_trace_tick") == 2
    assert TRACE_DUMP_EVERY_N_FRAMES == 30


def test_maybe_dump_trace_early_after_wheel(trace_on, tmp_path):
    ctx = FrameContext()
    out = tmp_path / "w.json"
    assert maybe_dump_trace(ctx, every=1000, path=str(out)) == 0
    ctx.bump("ic.wheel_tick")
    assert maybe_dump_trace(ctx, every=1000, path=str(out)) == 0
    n = maybe_dump_trace(ctx, every=1000, path=str(out))
    assert n > 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["traceEvents"]) == n


def test_decisions_event_carries_verdicts():
    from engine.frame.trace_export import build_trace

    ctx = FrameContext()
    with ctx.span("ic.prepare"):
        pass
    ctx.record("fallback", "ran", "fallback atomic=False more_pending=False promoted=True", ids=("frame=1",))
    events = build_trace([ctx], pid=999)
    verdicts = [e for e in events if e["name"] == "frame.decisions"]
    assert len(verdicts) == 1
    ev = verdicts[0]
    assert ev["ph"] == "X" and ev["dur"] == 0
    assert ev["pid"] == 999 and ev["tid"] == ctx.frame_id
    for key in ("pid", "tid", "ts", "ph"):
        assert key in ev
    by_pass = {d["pass"]: d for d in ev["args"]["decisions"]}
    assert by_pass["fallback"]["verdict"] == "ran"
    assert "promoted=True" in by_pass["fallback"]["reason"]
    # Zero-duration verdict event must not pollute aggregates.
    assert stage_stats(events)["frame.decisions"]["total_ms"] == 0.0
    assert slow_ticks(events, 25.0) == []
    assert validate_events(events) == []


def test_empty_decisions_emit_nothing():
    from engine.frame.trace_export import build_trace

    ctx = FrameContext()
    events = build_trace([ctx], pid=999)
    assert [e for e in events if e["name"] == "frame.decisions"] == []


def test_decisions_window_exports_burst_frames():
    from engine.frame.trace_export import build_trace

    ctx = FrameContext()
    for n in range(3):
        ctx.record("fallback", "ran", f"promoted={n == 2}", ids=(f"frame={n}",))
        ctx.reset()
    ctx.record("fallback", "skipped", "held", ids=("frame=3",))
    events = build_trace([ctx], pid=7)
    verdicts = [e for e in events if e["name"] == "frame.decisions"]
    assert sorted(e["tid"] for e in verdicts) == [0, 1, 2, 3]
    by_tid = {e["tid"]: e for e in verdicts}
    assert "promoted=True" in by_tid[2]["args"]["decisions"][0]["reason"]
    assert validate_events(events) == []
