"""
Render a trace.jsonl into a span tree, grouped by trace_id.

Usage:
    python -m core.tracing.print_tree                                  # all traces
    python -m core.tracing.print_tree mpress-7e17450b                  # single trace_id
    python -m core.tracing.print_tree --top 5                          # 5 slowest traces
    python -m core.tracing.print_tree --file /path/to/trace.jsonl mpress-*
    python -m core.tracing.print_tree --min-ms 20                      # only spans > 20ms

The output is LLM-friendly indented text with durations, suitable for
pasting into a chat as context for debugging questions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Iterable


def _default_path() -> str:
    xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(xdg, "ImproveImgSLI", "trace.jsonl")


def load_records(path: str) -> list[dict]:
    out: list[dict] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def group_by_trace(records: Iterable[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        tid = r.get("trace_id") or "<no-trace>"
        groups[tid].append(r)
    for tid in groups:
        groups[tid].sort(key=lambda r: r.get("seq", 0))
    return groups


def _match_pattern(trace_id: str, pattern: str) -> bool:
    if pattern == trace_id:
        return True
    if pattern.endswith("*") and trace_id.startswith(pattern[:-1]):
        return True
    return False


def _is_end_record(rec: dict) -> bool:
    kind = rec.get("kind", "")
    return kind.endswith(".end") or kind == "dispatch.end" or kind == "render.apply_end"


def _begin_kind_for_end(end_kind: str) -> str:
    if end_kind == "dispatch.end":
        return "dispatch.begin"
    if end_kind == "render.apply_end":
        return "render.apply_plan"
    if end_kind == "eventbus.end":
        return "eventbus.emit"
    if end_kind.startswith("input.") and end_kind.endswith(".end"):
        return end_kind[: -len(".end")]
    return ""


def _pair_durations(records: list[dict]) -> dict[int, float]:
    durations: dict[int, float] = {}
    for rec in records:
        if not _is_end_record(rec):
            continue
        dur = rec.get("payload", {}).get("duration_ms")
        seq_begin = rec.get("payload", {}).get("span_id")
        if dur is None or not seq_begin:
            continue
        durations[seq_begin] = dur
    return durations


def render_trace(records: list[dict], trace_id: str, min_ms: float = 0.0) -> str:
    durations_by_span = {}
    for rec in records:
        sp = rec.get("payload", {}).get("span_id")
        dur = rec.get("payload", {}).get("duration_ms")
        if sp and dur is not None:
            durations_by_span[sp] = dur

    lines: list[str] = []
    header = f"=== trace_id={trace_id}  ({len(records)} records) ==="
    lines.append(header)

    for rec in records:
        if _is_end_record(rec):
            continue
        depth = rec.get("depth", 0)
        kind = rec.get("kind", "?")
        summary = rec.get("summary", "")
        sp = rec.get("payload", {}).get("span_id")
        dur = durations_by_span.get(sp) if sp else None
        if dur is not None and dur < min_ms:
            continue
        indent = "  " * depth
        dur_s = f"[{dur:7.2f}ms] " if dur is not None else "[       -  ] "
        caller = rec.get("caller", "")
        line = f"{indent}{dur_s}{kind:22s} {summary}"
        lines.append(line)

        diff = rec.get("payload", {}).get("diff")
        if diff:
            for scope, changes in diff.items():
                if not changes:
                    continue
                lines.append(f"{indent}    diff.{scope}: {json.dumps(changes, default=str, ensure_ascii=False)[:200]}")

        changed = rec.get("payload", {}).get("changed")
        if changed and changed != {"<first>": True}:
            keys = ", ".join(list(changed.keys())[:8])
            lines.append(f"{indent}    plan changed: {keys}")

        if caller:
            lines.append(f"{indent}    @ {caller}")

    return "\n".join(lines)


def trace_total_ms(records: list[dict]) -> float:
    """Approximate total duration of a trace from first ts to last ts."""
    if not records:
        return 0.0
    first = records[0].get("ts", 0.0)
    last = records[-1].get("ts", 0.0)
    return (last - first) * 1000.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("trace_id", nargs="?", help="trace_id or pattern (mpress-*)")
    p.add_argument("--file", default=_default_path(), help="path to trace.jsonl")
    p.add_argument("--top", type=int, default=0, help="show N slowest traces")
    p.add_argument("--min-ms", type=float, default=0.0,
                   help="hide spans shorter than this duration")
    p.add_argument("--list", action="store_true", help="list trace_ids with total time")
    args = p.parse_args(argv)

    if not os.path.exists(args.file):
        print(f"trace file not found: {args.file}", file=sys.stderr)
        return 1

    records = load_records(args.file)
    groups = group_by_trace(records)

    if args.list:
        items = [(tid, trace_total_ms(recs), len(recs)) for tid, recs in groups.items()]
        items.sort(key=lambda x: -x[1])
        for tid, total, n in items:
            print(f"{total:8.2f}ms  {n:4d} recs  {tid}")
        return 0

    if args.top:
        items = [(tid, trace_total_ms(recs)) for tid, recs in groups.items()]
        items.sort(key=lambda x: -x[1])
        items = items[: args.top]
        for tid, _ in items:
            print(render_trace(groups[tid], tid, min_ms=args.min_ms))
            print()
        return 0

    if args.trace_id:
        matches = [tid for tid in groups if _match_pattern(tid, args.trace_id)]
        if not matches:
            print(f"no traces match: {args.trace_id}", file=sys.stderr)
            return 1
        for tid in matches:
            print(render_trace(groups[tid], tid, min_ms=args.min_ms))
            print()
        return 0

    for tid, recs in groups.items():
        print(render_trace(recs, tid, min_ms=args.min_ms))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
