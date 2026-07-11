#!/usr/bin/env python3
"""Rewrite fully-qualified import paths after moving a feature's modules.

Step 4 of the feature decomposition playbook
(docs/dev/rendering/feature-decomposition-playbook.md). Run this *after*
``decompose_feature_normalize_imports.py`` has made every internal import
fully qualified and the files have actually been ``git mv``'d into their
new subpackages.

Takes a move map (old top-level module name -> new dotted path relative to
the feature root, e.g. ``"store": "state.store"``) and, repo-wide,
replaces every whole-word occurrence of
``tabs.<tab>.canvas.features.<feature>.<old>`` with
``tabs.<tab>.canvas.features.<feature>.<new>``. This is safe without AST
because the prefix is unique to the feature (nothing else in the repo
shares it), so a word-boundary regex cannot touch unrelated code.

Does NOT auto-fix bare ``from tabs...features.<feature> import <old>``
imports (lazy re-exports, commonly in a feature's ``__init__.py``) since
rewriting those changes which module supplies the name, which needs a
human to route to the right subpackage. The script only warns about these;
fix them by hand.

Usage:
    python scripts/decompose_feature_rewrite_paths.py image_compare magnifier \\
        --map-file /tmp/magnifier_move_map.json
    python scripts/decompose_feature_rewrite_paths.py image_compare magnifier \\
        --map store=state.store --map actions=input.actions --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_move_map(args: argparse.Namespace) -> dict[str, str]:
    move_map: dict[str, str] = {}
    if args.map_file:
        move_map.update(json.loads(Path(args.map_file).read_text()))
    for pair in args.map:
        old, _, new = pair.partition("=")
        if not new:
            raise SystemExit(f"invalid --map entry (expected old=new): {pair!r}")
        move_map[old] = new
    if not move_map:
        raise SystemExit("no move map given (use --map-file or --map old=new)")
    return move_map


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tab", help="e.g. image_compare, multi_compare")
    parser.add_argument("feature", help="e.g. magnifier, divider, guides")
    parser.add_argument(
        "--map-file", help="JSON file: {\"old_module\": \"new.dotted.path\", ...}"
    )
    parser.add_argument(
        "--map",
        action="append",
        default=[],
        metavar="old=new",
        help="one move-map entry; repeatable",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print changes without writing files"
    )
    args = parser.parse_args()

    move_map = load_move_map(args)
    pkg_mod = f"tabs.{args.tab}.canvas.features.{args.feature}"

    bare_import_re = re.compile(r"^from\s+" + re.escape(pkg_mod) + r"\s+import\b")

    files = sorted(REPO_ROOT.rglob("*.py"))
    files = [f for f in files if "__pycache__" not in f.parts]

    changed = 0
    warnings: list[str] = []
    for f in files:
        src = f.read_text()
        if pkg_mod not in src:
            continue

        for lineno, line in enumerate(src.splitlines(), start=1):
            if bare_import_re.match(line):
                for old in move_map:
                    if re.search(r"\b" + re.escape(old) + r"\b", line):
                        warnings.append(
                            f"{f.relative_to(REPO_ROOT)}:{lineno}: bare import of "
                            f"{old!r} from {pkg_mod!r} — fix manually "
                            f"(target: {pkg_mod}.{move_map[old]})"
                        )

        # Combined single-pass regex: substituting keys one at a time risks a
        # later key's pattern matching text a previous substitution just
        # produced (e.g. old "store" -> "state.store", then old "state"
        # re-matching inside that result). One alternation with a callback
        # guarantees each occurrence is matched and replaced exactly once.
        # Longest-old-name-first so e.g. "store_common" is tried before
        # "store" when both are keys (regex alternation is first-match, not
        # longest-match).
        ordered_olds = sorted(move_map, key=len, reverse=True)
        combined = re.compile(
            "|".join(re.escape(f"{pkg_mod}.{old}") + r"\b" for old in ordered_olds)
        )

        def _sub(m: re.Match) -> str:
            for old, new in move_map.items():
                if m.group(0) == f"{pkg_mod}.{old}":
                    return f"{pkg_mod}.{new}"
            return m.group(0)

        new_src = combined.sub(_sub, src)

        if new_src != src:
            changed += 1
            rel = f.relative_to(REPO_ROOT)
            if args.dry_run:
                print(f"would update {rel}")
            else:
                f.write_text(new_src)
                print(f"updated {rel}")

    print(f"{changed} file(s) {'would be ' if args.dry_run else ''}updated")
    if warnings:
        print("\nNeeds manual review (bare re-exports):")
        for w in warnings:
            print(f"  {w}")


if __name__ == "__main__":
    main()
