"""Audit-Meta registry for file-size policy.

Scans src/ for Audit-Meta: / File-Size-Exempt: markers, generates
docs/dev/file_size_registry.json, and reports oversized files without markers.

Usage:
    python src/devtools/file_meta.py --scan
    python src/devtools/file_meta.py --report
    python src/devtools/file_meta.py --report --cloc cloc.txt
    python src/devtools/file_meta.py --write-registry
    python src/devtools/file_meta.py --check

See docs/dev/FILE_SIZE_POLICY.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Policy constants (mirrors FILE_SIZE_POLICY.md)
AUDIT_LIMIT = 500
CANVAS_LIMIT = 400
AUDIT_MARKER = "Audit-Meta:"
CANVAS_MARKER = "File-Size-Exempt:"

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
REGISTRY_PATH = REPO_ROOT / "docs" / "dev" / "file_size_registry.json"

# Regex to capture Audit-Meta line and optional key=value pairs + free reason
# Anchored to line start (optional comment) to avoid matching documentation mentions.
_AUDIT_RE = re.compile(r"^\s*#?\s*Audit-Meta:\s*(.*)", re.MULTILINE)
_CANVAS_RE = re.compile(r"^\s*#?\s*File-Size-Exempt:\s*(.*)", re.MULTILINE)

EXCLUDE_PARTS = {"__pycache__", ".git", "tests", "venv", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache"}


def _is_excluded(path: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in path.parts)


def _line_count(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return len(text.splitlines())


def _extract_meta(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    # Prefer Audit-Meta, fallback to File-Size-Exempt for canvas
    m = _AUDIT_RE.search(text)
    if m:
        raw = m.group(1).strip()
        return {"marker": AUDIT_MARKER, "raw": raw, "text": text}
    m2 = _CANVAS_RE.search(text)
    if m2:
        raw = m2.group(1).strip()
        return {"marker": CANVAS_MARKER, "raw": raw, "text": text}
    return None


def _parse_kv(raw: str) -> dict:
    """Parse key=value pairs and leftover reason."""
    kv: dict[str, str] = {}
    # naive: split by spaces respecting quotes
    # use shlex for robustness
    import shlex

    try:
        tokens = shlex.split(raw)
    except ValueError:
        tokens = raw.split()
    reason_parts: list[str] = []
    for tok in tokens:
        if "=" in tok and not tok.startswith("reason"):
            k, v = tok.split("=", 1)
            kv[k] = v
        elif tok.startswith("reason="):
            # reason may contain spaces, shlex already handled
            kv["reason"] = tok[len("reason=") :]
        else:
            reason_parts.append(tok)
    if reason_parts and "reason" not in kv:
        # fallback: raw is free-form reason
        kv["reason"] = " ".join(reason_parts)
    elif reason_parts and "reason" in kv:
        # append stray tokens to reason
        kv["reason"] = kv["reason"] + " " + " ".join(reason_parts)
        kv["reason"] = kv["reason"].strip()
    if not raw:
        kv["reason"] = ""
    # ensure reason key exists if raw was plain text
    if "reason" not in kv and raw and "=" not in raw:
        kv["reason"] = raw
    return kv


def scan(threshold: int = AUDIT_LIMIT, include_canvas: bool = True) -> list[dict]:
    """Scan src/ for all py files, return entries."""
    entries: list[dict] = []
    if not SRC_ROOT.exists():
        return entries
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if _is_excluded(path.relative_to(REPO_ROOT)):
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        lines = _line_count(path)
        meta = _extract_meta(path)
        is_canvas = "canvas/features" in rel
        limit = CANVAS_LIMIT if (include_canvas and is_canvas) else threshold
        # only track files that are oversized OR have a marker (for registry completeness)
        if lines > limit or meta is not None:
            kv = _parse_kv(meta["raw"]) if meta else {}
            entries.append(
                {
                    "path": rel,
                    "lines": lines,
                    "limit": limit,
                    "marker": meta["marker"] if meta else None,
                    "raw": meta["raw"] if meta else None,
                    "parsed": kv,
                    "is_canvas": is_canvas,
                }
            )
    return entries


def build_registry(entries: list[dict] | None = None) -> dict:
    if entries is None:
        entries = scan()
    # only include entries that have a marker
    registry_entries = []
    for e in entries:
        if e["marker"] is None:
            continue
        registry_entries.append(
            {
                "path": e["path"],
                "lines": e["lines"],
                "limit": e["limit"],
                "marker": e["marker"],
                "raw": e["raw"],
                "parsed": e["parsed"],
            }
        )
    registry_entries.sort(key=lambda x: x["path"])
    return {
        "_generated_by": "src/devtools/file_meta.py --write-registry",
        "_policy": "docs/dev/FILE_SIZE_POLICY.md",
        "entries": registry_entries,
    }


def write_registry() -> Path:
    entries = scan()
    reg = build_registry(entries)
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return REGISTRY_PATH


def check_registry() -> bool:
    """Return True if registry is up-to-date, else False and print diff."""
    if not REGISTRY_PATH.exists():
        print(f"Missing registry: {REGISTRY_PATH}", file=sys.stderr)
        return False
    existing = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    expected = build_registry()
    if existing == expected:
        return True
    # simple diff: compare sorted path sets
    existing_paths = {e["path"] for e in existing.get("entries", [])}
    expected_paths = {e["path"] for e in expected.get("entries", [])}
    missing = sorted(expected_paths - existing_paths)
    extra = sorted(existing_paths - expected_paths)
    if missing:
        print(f"Registry missing entries: {missing}", file=sys.stderr)
    if extra:
        print(f"Registry has extra entries: {extra}", file=sys.stderr)
    # deeper: raw differences
    exp_map = {e["path"]: e for e in expected["entries"]}
    exist_map = {e["path"]: e for e in existing.get("entries", [])}
    for p in sorted(expected_paths & existing_paths):
        if exp_map[p] != exist_map[p]:
            print(f"Registry mismatch for {p}:", file=sys.stderr)
            print(f"  expected: {exp_map[p]}", file=sys.stderr)
            print(f"  existing: {exist_map[p]}", file=sys.stderr)
    return False


def report(threshold: int = AUDIT_LIMIT, cloc_path: Path | None = None) -> int:
    """Print report of oversized files without markers. Return violation count."""
    entries = scan(threshold=threshold)
    violations = [e for e in entries if e["marker"] is None and e["lines"] > e["limit"]]
    # optional cloc cross-check: just informational
    cloc_info = ""
    if cloc_path and cloc_path.exists():
        cloc_info = f" (cloc: {cloc_path})"

    if not violations:
        print(f"OK: no oversized files without Audit-Meta/File-Size-Exempt{cloc_info} (limit {threshold})")
        # also print registry size
        reg_count = len([e for e in entries if e["marker"] is not None])
        print(f"Tracked with markers: {reg_count}")
        for e in sorted([x for x in entries if x["marker"] is not None], key=lambda x: x["path"]):
            print(f"  {e['path']} {e['lines']}L {e['marker']} {e['raw']}")
        return 0

    print(f"VIOLATIONS: {len(violations)} file(s) over {threshold} lines without marker{cloc_info}:")
    for v in sorted(violations, key=lambda x: -x["lines"]):
        print(f"  {v['path']} — {v['lines']} lines (limit {v['limit']})")
    print("\nFix: split via use_cases/ per CODE_PATTERNS.md, or add Audit-Meta: pattern=... reason=\"...\" and run --write-registry")
    return len(violations)


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit-Meta file-size registry")
    ap.add_argument("--scan", action="store_true", help="Dump JSON scan to stdout")
    ap.add_argument("--report", action="store_true", help="Human report of violations")
    ap.add_argument("--write-registry", action="store_true", help="Write docs/dev/file_size_registry.json")
    ap.add_argument("--check", action="store_true", help="Check registry is up-to-date (CI)")
    ap.add_argument("--cloc", type=Path, default=None, help="Optional cloc.txt path for cross-check")
    ap.add_argument("--limit", type=int, default=AUDIT_LIMIT, help="Audit threshold (default 500)")
    args = ap.parse_args()

    if args.scan:
        entries = scan(threshold=args.limit)
        json.dump(entries, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
        return

    if args.write_registry:
        p = write_registry()
        print(f"Wrote {p} ({len(json.loads(p.read_text(encoding='utf-8'))['entries'])} entries)")
        return

    if args.check:
        ok = check_registry()
        if ok:
            print("Registry OK")
            sys.exit(0)
        else:
            print("Registry stale — run: python src/devtools/file_meta.py --write-registry", file=sys.stderr)
            sys.exit(1)

    if args.report:
        n = report(threshold=args.limit, cloc_path=args.cloc)
        sys.exit(0 if n == 0 else 1)

    # default: report
    n = report(threshold=args.limit, cloc_path=args.cloc)
    sys.exit(0 if n == 0 else 1)


if __name__ == "__main__":
    main()
