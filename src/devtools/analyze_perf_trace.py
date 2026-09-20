#!/usr/bin/env python3
"""Validate + pre-aggregate a Chrome Trace file from ``trace_export``.

Thin validator/pre-agg for Wave B
(``plan-engine-perf-debugger-2026-09-20``, Phase 2) — NOT a viewer.
Perfetto is the viewer; this script answers "is the file well-formed,
which stage costs the frame" from the command line.

Usage:
    python src/devtools/analyze_perf_trace.py trace.json
    python src/devtools/analyze_perf_trace.py trace.json --budget-ms 16.7

Validates the Wave B schema (required keys ``pid``/``tid``/``ts``/``ph``
on EVERY event; ``name`` + numeric ``dur`` on Complete ``X`` events),
then prints per-stage (event name) ``count``/``total``/``p50``/``p95``/
``max`` durations in ms plus event counts, and flags ticks (``tid``
lanes = frames) whose summed span time exceeds ``--budget-ms``
(default 25.0) with the dominant stage.

Percentiles use the nearest-rank method on sorted durations
(``rank = ceil(p/100 * n)``); tick totals are plain sums of span
durations on the lane (an UPPER bound when spans nest — use Perfetto
for exact critical-path analysis).

Exit codes: 0 = valid (even with slow ticks flagged); 1 = usage/file
error; 2 = schema invalid (errors listed on stderr).

Stdlib only (``argparse``, ``json``, ``math``, ``pathlib``) — no Qt
imports in devtools.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

#: Required on EVERY event (mirrors ``trace_export.REQUIRED_KEYS``).
REQUIRED_KEYS = ("pid", "tid", "ts", "ph")

#: Default frame budget flagging slow ticks (ms).
DEFAULT_BUDGET_MS = 25.0


def load_trace(path: str | Path) -> list[dict[str, Any]]:
    """Load a trace file: ``{"traceEvents": [...]}`` or a bare ``[...]``.

    Raises ``ValueError`` with a human message when the file is not a
    trace (bad JSON, wrong top-level shape, non-dict events).
    """
    raw = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if isinstance(data, dict):
        events = data.get("traceEvents", data.get("trace_events"))
        if events is None:
            raise ValueError(
                f"{path}: object trace needs a 'traceEvents' array "
                f"(keys: {sorted(str(k) for k in data)[:5]})"
            )
    elif isinstance(data, list):
        events = data
    else:
        raise ValueError(f"{path}: top level must be an object or array")
    if not isinstance(events, list) or any(
        not isinstance(item, dict) for item in events
    ):
        raise ValueError(f"{path}: traceEvents must be an array of objects")
    return events


def validate_events(events: list[dict[str, Any]]) -> list[str]:
    """Schema errors, one string per offending event; ``[]`` = valid."""
    errors: list[str] = []
    for index, event in enumerate(events):
        missing = [key for key in REQUIRED_KEYS if key not in event]
        if missing:
            errors.append(
                f"event #{index} ({event.get('name', '?')!r}): "
                f"missing keys {missing}"
            )
            continue
        phase = event.get("ph")
        if phase == "X":
            if "name" not in event:
                errors.append(f"event #{index}: X event missing 'name'")
            dur = event.get("dur")
            if not isinstance(dur, (int, float)) or isinstance(dur, bool):
                errors.append(
                    f"event #{index} ({event.get('name', '?')!r}): "
                    f"X event needs numeric 'dur', got {dur!r}"
                )
            ts = event.get("ts")
            if not isinstance(ts, (int, float)) or isinstance(ts, bool):
                errors.append(
                    f"event #{index} ({event.get('name', '?')!r}): "
                    f"needs numeric 'ts', got {ts!r}"
                )
    return errors


def _percentile(sorted_ms: list[float], pct: float) -> float:
    """Nearest-rank percentile over an ascending-sorted sample."""
    if not sorted_ms:
        return 0.0
    rank = max(1, math.ceil(pct / 100.0 * len(sorted_ms)))
    return sorted_ms[min(rank, len(sorted_ms)) - 1]


def stage_stats(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per-stage aggregates over Complete (``X``) events (durations→ms).

    Returns ``{name: {count, total_ms, p50_ms, p95_ms, max_ms}}``.
    Trace ``ts``/``dur`` are microseconds; report converts to ms.
    """
    buckets: dict[str, list[float]] = {}
    for event in events:
        if event.get("ph") != "X":
            continue
        dur = event.get("dur")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool):
            continue
        buckets.setdefault(str(event.get("name", "unknown")), []).append(
            float(dur) / 1000.0
        )
    stats: dict[str, dict[str, Any]] = {}
    for name in sorted(buckets):
        ordered = sorted(buckets[name])
        stats[name] = {
            "count": len(ordered),
            "total_ms": sum(ordered),
            "p50_ms": _percentile(ordered, 50),
            "p95_ms": _percentile(ordered, 95),
            "max_ms": ordered[-1],
        }
    return stats


def slow_ticks(
    events: list[dict[str, Any]], budget_ms: float = DEFAULT_BUDGET_MS
) -> list[dict[str, Any]]:
    """Ticks (``tid`` lanes) whose summed span time exceeds ``budget_ms``.

    Returns slowest-first ``[{tid, total_ms, dominant, dominant_ms}]``
    where ``dominant`` is the stage with the largest summed duration on
    that lane. Sums double-count nested spans (upper bound — see module
    docstring).
    """
    per_lane: dict[Any, dict[str, float]] = {}
    for event in events:
        if event.get("ph") != "X":
            continue
        dur = event.get("dur")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool):
            continue
        lane = per_lane.setdefault(event.get("tid"), {})
        name = str(event.get("name", "unknown"))
        lane[name] = lane.get(name, 0.0) + float(dur) / 1000.0
    slow: list[dict[str, Any]] = []
    for tid, lane in per_lane.items():
        total = sum(lane.values())
        if total <= budget_ms:
            continue
        dominant = max(lane, key=lambda name: lane[name])
        slow.append(
            {
                "tid": tid,
                "total_ms": total,
                "dominant": dominant,
                "dominant_ms": lane[dominant],
            }
        )
    slow.sort(key=lambda row: row["total_ms"], reverse=True)
    return slow


def format_report(
    path: str | Path,
    events: list[dict[str, Any]],
    budget_ms: float = DEFAULT_BUDGET_MS,
) -> str:
    """Human-readable validation + aggregation report (stable format)."""
    counts: dict[str, int] = {}
    for event in events:
        counts[str(event.get("ph", "?"))] = counts.get(str(event.get("ph", "?")), 0) + 1
    lines = [
        f"trace: {path}",
        (
            f"events: {len(events)} "
            f"(X={counts.get('X', 0)} C={counts.get('C', 0)} "
            f"M={counts.get('M', 0)} other={len(events) - counts.get('X', 0) - counts.get('C', 0) - counts.get('M', 0)})"
        ),
        "stages:",
    ]
    stats = stage_stats(events)
    if not stats:
        lines.append("  (none)")
    for name, row in stats.items():
        lines.append(
            f"  {name} count={row['count']} "
            f"total={row['total_ms']:.3f}ms "
            f"p50={row['p50_ms']:.3f}ms "
            f"p95={row['p95_ms']:.3f}ms "
            f"max={row['max_ms']:.3f}ms"
        )
    slow = slow_ticks(events, budget_ms)
    lines.append(f"slow ticks (budget {budget_ms:.1f}ms): {len(slow)}")
    for row in slow:
        lines.append(
            f"  tid={row['tid']} total={row['total_ms']:.3f}ms "
            f"dominant={row['dominant']} ({row['dominant_ms']:.3f}ms)"
        )
    if not slow:
        lines.append("  none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (returns the process exit code; see docstring)."""
    parser = argparse.ArgumentParser(
        description="Validate + pre-aggregate a Chrome Trace file "
        "(Perfetto remains the viewer)."
    )
    parser.add_argument("trace", help="trace.json from trace_export.write_trace")
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=DEFAULT_BUDGET_MS,
        help=f"flag ticks slower than this (ms; default {DEFAULT_BUDGET_MS})",
    )
    args = parser.parse_args(argv)
    try:
        events = load_trace(args.trace)
    except OSError as exc:
        print(f"error: cannot read {args.trace}: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    errors = validate_events(events)
    if errors:
        print(f"error: invalid schema in {args.trace}:", file=sys.stderr)
        for error in errors[:20]:
            print(f"  - {error}", file=sys.stderr)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more", file=sys.stderr)
        return 2
    print(format_report(args.trace, events, args.budget_ms))
    return 0


if __name__ == "__main__":
    sys.exit(main())
