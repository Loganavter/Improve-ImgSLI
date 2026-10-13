#!/usr/bin/env python3
"""Doc-truth guard: canon/skill docs must not reference retired help mechanics.

The help plane's mechanics changed (``{{tr:}}`` interpolation, ``tree.json``,
``figures.json``, ``check_help_figures.py``, ``resolve_alias`` all removed) while
the canon/skills kept describing them — so agents executed stale instructions
and redid work. This guard fails when a canon/skill doc references a retired
mechanism, with a file:line so it is fixable. A line may opt out with the
``doc-truth:allow`` marker when the retired name is mentioned on purpose (e.g.
"do not use ``{{tr:}}`` any more").

Usage:
    python src/devtools/check_help_doc_truth.py
    python src/devtools/check_help_doc_truth.py docs/dev/HELP_SYSTEM.md skills
    python src/devtools/check_help_doc_truth.py --list-tokens
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Names/mechanisms that no longer exist in the code. Referencing them in the
#: canon is a lie an agent will execute.
RETIRED_TOKENS = (
    "{{tr:",
    "{{img:",
    "tree.json",
    "figures.json",
    "check_help_figures",
    "resolve_alias",
)

#: Per-line opt-out marker for a deliberate mention of a retired name.
ALLOW_MARKER = "doc-truth:allow"

DEFAULT_TARGETS = (
    ROOT / "docs/dev/HELP_AUTHORING.md",
    ROOT / "docs/dev/HELP_STYLE_GUIDE.md",
    ROOT / "docs/dev/HELP_SYSTEM.md",
    ROOT / "skills",
)


def iter_markdown(targets: list[Path]):
    for target in targets:
        if target.is_dir():
            yield from sorted(target.rglob("*.md"))
        elif target.is_file():
            yield target


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return ``(lineno, token, line)`` for each retired token on a line."""
    hits: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if ALLOW_MARKER in line:
            continue
        for token in RETIRED_TOKENS:
            if token in line:
                hits.append((lineno, token, line.strip()))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="files/dirs (default: canon + skills)")
    parser.add_argument("--list-tokens", action="store_true", help="print retired tokens")
    args = parser.parse_args(argv)

    if args.list_tokens:
        print("\n".join(RETIRED_TOKENS))
        return 0

    targets = [Path(p) for p in args.paths] if args.paths else list(DEFAULT_TARGETS)
    total = 0
    for path in iter_markdown(targets):
        if not path.is_file():
            continue
        for lineno, token, line in scan_file(path):
            try:
                shown = path.relative_to(ROOT)
            except ValueError:
                shown = path
            print(f"{shown}:{lineno}: retired '{token}' — {line[:140]}")
            total += 1

    if total:
        print(
            f"\ndoc-truth FAILED: {total} reference(s) to retired help mechanics. "
            f"Update the doc, or add '{ALLOW_MARKER}' to the line if the mention "
            "is deliberate.",
            file=sys.stderr,
        )
        return 1

    print("doc-truth OK: canon/skill docs reference only live mechanics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
