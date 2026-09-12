"""Devtool: dump/validate navigation graph.

Mirrors file_meta.py / docs_link_graph.py.

Usage:
    python src/devtools/nav_graph.py --dump
    python src/devtools/nav_graph.py --dump --json
    python src/devtools/nav_graph.py --check
    python src/devtools/nav_graph.py --write-snapshot docs/dev/nav_graph_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_nav_graph():
    # Prefer toolkit's nav_graph (editable install)
    try:
        from sli_ui_toolkit.ui.managers.nav_graph import snapshot, validate, focus_reason

        return snapshot, validate, focus_reason
    except Exception as e:
        print(f"nav_graph not available: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Navigation graph dump/validate")
    ap.add_argument("--dump", action="store_true", help="Human dump")
    ap.add_argument("--json", action="store_true", help="JSON dump (with --dump)")
    ap.add_argument("--check", action="store_true", help="Validate and exit non-zero on violations")
    ap.add_argument("--write-snapshot", type=Path, default=None, help="Write snapshot JSON")
    args = ap.parse_args()

    snapshot, validate, focus_reason = _load_nav_graph()

    if args.check:
        violations = validate()
        if not violations:
            print("nav_graph OK — no violations")
            sys.exit(0)
        print(f"nav_graph violations ({len(violations)}):")
        for v in violations:
            print(f"  - {v}")
        sys.exit(1)

    if args.write_snapshot:
        graph = snapshot()
        data = {
            "_generated_by": "src/devtools/nav_graph.py --write-snapshot",
            "nodes": [
                {"owner": n.owner, "section": n.section, "visible": n.visible, "extra_keys": sorted(n.extra_keys)}
                for n in graph.nodes
            ],
        }
        args.write_snapshot.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {args.write_snapshot} ({len(data['nodes'])} nodes)")
        return

    # default dump
    graph = snapshot()
    reason = focus_reason()
    if args.json:
        data = {
            "focus_reason": reason.name,
            "nodes": [
                {"owner": n.owner, "section": n.section, "visible": n.visible, "extra_keys": sorted(n.extra_keys)}
                for n in graph.nodes
            ],
        }
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    print(f"Focus reason (current input): {reason.name} ({'keyboard' if reason.name != 'MouseFocusReason' else 'mouse'})")
    if not graph.nodes:
        print("(no sections registered — run inside app or with QApplication)")
        return
    print(f"Graph nodes ({len(graph.nodes)}):")
    for i, n in enumerate(graph.nodes):
        vis = "visible" if n.visible else "hidden"
        keys = ",".join(str(k) for k in sorted(n.extra_keys)) if n.extra_keys else "-"
        print(f"  {i}: {n.owner:25} {n.section:25} {vis:7} extra_keys={keys}")
    violations = validate(graph)
    if violations:
        print(f"\nViolations ({len(violations)}):")
        for v in violations:
            print(f"  - {v}")
    else:
        print("\nNo violations")


if __name__ == "__main__":
    main()
