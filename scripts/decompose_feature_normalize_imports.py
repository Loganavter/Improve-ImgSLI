#!/usr/bin/env python3
"""Normalize a canvas feature's internal relative imports to absolute form.

Step 1 of the feature decomposition playbook
(docs/dev/rendering/feature-decomposition-playbook.md). Rewrites every
``from .x import ...`` / ``from ..x.y import ...`` inside a feature package
to the fully qualified ``tabs.<tab>.canvas.features.<feature>.x[.y]`` form,
using an AST-based source-span edit so multi-line/parenthesized import
lists are preserved untouched apart from the ``from ... import`` head.

This pass is a behavior no-op: it does not move any file, only makes each
import's target explicit. Verify with a syntax check and the feature's test
suite before moving on to the file-move step.

Usage:
    python scripts/decompose_feature_normalize_imports.py image_compare magnifier
    python scripts/decompose_feature_normalize_imports.py multi_compare grid_dividers --dry-run
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _offset(lines: list[str], lineno: int, col: int) -> int:
    return sum(len(l) for l in lines[: lineno - 1]) + col


def normalize_file(path: Path, cur_pkg_parts: list[str], pkg_mod: str) -> str | None:
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)

    edits: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.level < 1:
            continue
        start = _offset(lines, node.lineno, node.col_offset)
        end = _offset(lines, node.end_lineno, node.end_col_offset)
        segment = src[start:end]

        ndots = node.level
        modpath = node.module or ""
        up = ndots - 1
        if up > len(cur_pkg_parts):
            raise SystemExit(
                f"{path}:{node.lineno}: import escapes feature package root: "
                f"{segment[:60]!r}"
            )
        base_parts = cur_pkg_parts[: len(cur_pkg_parts) - up] if up else cur_pkg_parts
        target_parts = base_parts + (modpath.split(".") if modpath else [])
        abs_mod = pkg_mod + ("." + ".".join(target_parts) if target_parts else "")

        dots_and_mod_len = ndots + len(modpath)
        head_end = start + len("from ") + dots_and_mod_len
        new_segment = f"from {abs_mod}" + src[head_end:end]
        edits.append((start, end, new_segment))

    if not edits:
        return None
    edits.sort()
    new_src = src
    for start, end, new_segment in reversed(edits):
        new_src = new_src[:start] + new_segment + new_src[end:]
    return new_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab", help="e.g. image_compare, multi_compare")
    parser.add_argument("feature", help="e.g. magnifier, divider, guides")
    parser.add_argument(
        "--dry-run", action="store_true", help="print changes without writing files"
    )
    args = parser.parse_args()

    feature_dir = (
        REPO_ROOT / "src" / "tabs" / args.tab / "canvas" / "features" / args.feature
    )
    if not feature_dir.is_dir():
        raise SystemExit(f"not a directory: {feature_dir}")
    pkg_mod = f"tabs.{args.tab}.canvas.features.{args.feature}"

    files = sorted(feature_dir.rglob("*.py"))
    files = [f for f in files if "__pycache__" not in f.parts]

    changed = 0
    for f in files:
        rel = f.relative_to(feature_dir)
        cur_pkg_parts = list(rel.parts[:-1])
        new_src = normalize_file(f, cur_pkg_parts, pkg_mod)
        if new_src is None:
            continue
        changed += 1
        if args.dry_run:
            print(f"would update {rel}")
        else:
            f.write_text(new_src)
            print(f"updated {rel}")

    print(f"{changed} file(s) {'would be ' if args.dry_run else ''}updated")


if __name__ == "__main__":
    main()
