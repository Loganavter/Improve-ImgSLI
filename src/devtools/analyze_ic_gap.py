#!/usr/bin/env python3
"""
Analyze IMGSLI_IC_GAP_DEBUG / IMGSLI_IC_PREVIEW_DEBUG logs for empty middle strip.

Usage:
  python src/devtools/analyze_ic_gap.py --log ~/.local/share/ImproveImgSLI/log.txt --trace ~/.local/share/ImproveImgSLI/trace.jsonl
  python src/devtools/analyze_ic_gap.py --log /tmp/run.log --json /tmp/gap_timeline.json
  grep -E "ic-gap|gap_detected|fallback decision" log.txt | python src/devtools/analyze_ic_gap.py --stdin

Detects signature:
  gap with narrow bbox (<0.01) or covered<0.999 + more_pending=False (BUG) vs expected progressive.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Regexes for key log lines
PATTERNS = {
    "pick_gap": re.compile(r"\[ic-gap\] pick->gap .*gap_id=(?P<gid>\S+)"),
    "gap_bbox_dist": re.compile(r"\[ic-gap\] gap bbox_dist.*entries=(?P<entries>\d+).*min=(?P<min_w>[0-9.]+).*narrow.*bbox_cov=(?P<cov>[0-9.]+)"),
    "gap_detected": re.compile(r"gap_detected .*covered1=(?P<c1>[0-9.]+).*covered2=(?P<c2>[0-9.]+).*bbox=(?P<bbox>[0-9.]+).*more_pending=(?P<more>True|False)"),
    "fallback_decision": re.compile(r"fallback decision.*atomic=(?P<atomic>True|False).*more_pending=(?P<more>True|False).*current_entries=(?P<cur>\d+)"),
    "fallback_result": re.compile(r"fallback result.*resolved=(?P<res>\d+).*current=(?P<cur>\d+).*more_pending=(?P<more>True|False).*promoted=(?P<prom>True|False)"),
    "geometry_input": re.compile(r"\[ic-gap\] geometry input.*size1=(?P<s1>\S+).*size2=(?P<s2>\S+)"),
    "resolve_lod": re.compile(r"\[ic-gap\] gap resolve_lod.*shared_level=(?P<shared>\d+).*keys=(?P<keys>.*)"),
    "narrow_bbox": re.compile(r"narrow bbox"),
}

SEVERE_THRESH_BBOX_W = 0.01
SEVERE_THRESH_COVERED = 0.999


def parse_log(path: Path | None, stdin: bool = False) -> list[dict]:
    lines = []
    if stdin:
        raw = sys.stdin.read().splitlines()
    else:
        if path is None or not path.exists():
            print(f"log not found: {path}", file=sys.stderr)
            return []
        raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for idx, line in enumerate(raw):
        entry = {"line_no": idx + 1, "raw": line}
        for name, pat in PATTERNS.items():
            m = pat.search(line)
            if m:
                entry["kind"] = name
                entry.update(m.groupdict())
                break
        else:
            # also capture timestamp prefix if any: "2026-08-30 04:03:34,355"
            ts_m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[,\.]\d+)", line)
            if ts_m:
                entry["ts"] = ts_m.group(1)
        if "kind" in entry:
            lines.append(entry)
    return lines


def classify(events: list[dict]) -> list[dict]:
    out = []
    for ev in events:
        if ev.get("kind") == "gap_detected":
            try:
                c1 = float(ev.get("c1", 1.0))
                c2 = float(ev.get("c2", 1.0))
                bbox = float(ev.get("bbox", 1.0))
                more = ev.get("more") == "True"
                severe = (c1 < SEVERE_THRESH_COVERED or c2 < SEVERE_THRESH_COVERED or bbox < SEVERE_THRESH_COVERED) and not more
                ev["severity"] = "SEVERE_BUG" if severe else ("expected_progress" if more else "mild")
                ev["is_bug"] = severe
            except Exception:
                ev["severity"] = "unknown"
        elif ev.get("kind") == "gap_bbox_dist":
            try:
                min_w = float(ev.get("min_w", 1.0))
                cov = float(ev.get("cov", 1.0))
                ev["narrow_bug"] = min_w < SEVERE_THRESH_BBOX_W and cov < SEVERE_THRESH_COVERED
            except Exception:
                pass
        out.append(ev)
    return out


def main():
    ap = argparse.ArgumentParser(description="Analyze IC gap logs")
    ap.add_argument("--log", type=Path, default=Path.home() / ".local/share/ImproveImgSLI/log.txt", help="path to log.txt")
    ap.add_argument("--trace", type=Path, default=None, help="path to trace.jsonl (optional)")
    ap.add_argument("--tile-dir", type=Path, default=None, help="tile_debug dir (optional)")
    ap.add_argument("--json", type=Path, default=None, help="write timeline JSON")
    ap.add_argument("--stdin", action="store_true", help="read log from stdin")
    ap.add_argument("--bug-only", action="store_true", help="only show SEVERE_BUG gaps")
    args = ap.parse_args()

    events = parse_log(args.log if not args.stdin else None, stdin=args.stdin)
    events = classify(events)

    if args.bug_only:
        events = [e for e in events if e.get("is_bug") or e.get("narrow_bug")]

    # Print timeline
    bug_count = sum(1 for e in events if e.get("is_bug"))
    narrow_count = sum(1 for e in events if e.get("narrow_bug"))
    print(f"Parsed {len(events)} gap-related events | SEVERE_BUG gaps: {bug_count} | narrow bbox events: {narrow_count}")
    print("-" * 80)
    for ev in events[-200:]:
        sev = ev.get("severity", "") or ("NARROW" if ev.get("narrow_bug") else "")
        ts = ev.get("ts", "")
        kind = ev.get("kind", "")
        print(f"{ev['line_no']:5d} {ts} [{kind} {sev}] {ev['raw'][:300]}")

    # Also check tile dumps if provided
    if args.tile_dir and args.tile_dir.exists():
        import glob

        tile_files = list(args.tile_dir.glob("tiles.jsonl"))
        for tf in tile_files:
            try:
                data = [json.loads(l) for l in tf.read_text().splitlines() if l.strip()]
                fb = [d for d in data if d.get("kind") == "fallback_lod" and d.get("fallback_kept") == 0 and d.get("fallback_raw", 0) > 0]
                if fb:
                    print(f"\nTile dump {tf}: {len(fb)} fallback EMPTY (kept 0, raw>0) -> gap without baseline")
                    for x in fb[:5]:
                        print(json.dumps(x, ensure_ascii=False)[:300])
            except Exception as e:
                print(f"tile parse error {tf}: {e}")

    if args.json:
        args.json.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote JSON timeline to {args.json}")


if __name__ == "__main__":
    main()
