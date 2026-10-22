#!/usr/bin/env python3
"""Cited repo-root path existence — a baseline ratchet over markdown prose.

Companion to ``docs_link_graph.py``, deliberately a separate module: the link
graph validates *markdown links* and renders the doc index, while this checks
*backticked repo-root paths* (``src/…``, ``tests/…``, ``docs/…``, ``scripts/…``,
``mcp-server/…``) against the checkout. Different finding model, different
baseline, different failure semantics — mixing them made both unreadable.

Why it exists: docs that cite a path are executable instructions. A path that
does not exist (a moved module, a doc that never existed, a sibling-repo doc
written without its prefix) fails silently — the reader invents the rest.

Not checked, by design:

* illustrative forms — ``…``/``...``, ``{a,b}``, ``<placeholder>``, globs,
  shell transcripts, ``path:NNN`` citations (the line is volatility, and the
  comment checker owns ``.py:NNN``);
* bare relative paths and paths escaping the repo — nothing to compare against;
* a path naming a sibling checkout (``sli-ui-toolkit``,
  ``improve-imgsli-internal-docs``): those must be written with the sibling
  prefix and cannot be resolved in a clean clone;
* dated records under ``**/investigations/`` — they name what was true when
  they were written (evidence, not pointers).

Findings are a ratchet: the committed baseline (``file<TAB>count``) accepts the
pre-existing drift, a grown count or a new file fails, and a shrinking count
passes. Regenerate with ``docs_link_graph.py --update-path-baseline``.

Stdlib only; static string work, no Qt, no app import.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

#: ``\`token\``` — the citation shape markdown prose uses for paths.
BACKTICK_RE = re.compile(r"`([^`\n]+)`")

#: First path segment of a backticked path that means "relative to this repo".
REPO_ROOT_PREFIXES = ("src", "tests", "docs", "scripts", "mcp-server")

#: Dated records name what was true when written; a dead path there is evidence.
DATED_RECORD_DIRS = frozenset({"investigations"})

#: A path naming another checkout is not resolvable here by design.
SIBLING_REPO_DIRS = frozenset({"sli-ui-toolkit", "improve-imgsli-internal-docs"})

#: Characters that mark a token as illustrative rather than a literal path.
ILLUSTRATIVE_CHARS = frozenset("…{}<>*|$")

#: Committed ratchet for cited-path findings (``file<TAB>count``).
PATH_BASELINE_REL = "src/devtools/docs_path_baseline.txt"

BASELINE_HEADER = (
    "# Cited-path baseline for src/devtools/docs_link_graph.py.",
    "# Format: <repo-relative doc path><TAB><accepted missing-path count>.",
    "# Regenerate: python src/devtools/docs_link_graph.py --update-path-baseline",
    "# A count may only shrink. Never add a file here to silence a NEW dead path",
    "# — fix the citation instead (or write the sibling prefix for sibling paths).",
)


@dataclass(frozen=True, slots=True)
class MissingRepoPath:
    """A backticked repo-root path that does not exist in this checkout."""

    source: str  # repo-relative path of the citing file
    line: int
    token: str  # the cited path as written


def _rel(path: Path, *, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def is_dated_record(source_rel: str) -> bool:
    """``True`` for plans/session logs/investigations (evidence, not pointers)."""
    return any(part in DATED_RECORD_DIRS for part in Path(source_rel).parts)


def normalize_cited_repo_path(token: str) -> str | None:
    """Return the literal repo-root path a backticked token cites, or None.

    ``None`` means "not a checkable path": illustrative fragments
    (``…``/``...``, ``{a,b}``, ``<placeholder>``, globs, shell transcripts),
    line-number/URL shapes, relative or escaping paths, and paths that name a
    sibling checkout (those must be written with the sibling prefix and are
    not resolvable here).
    """
    token = token.strip()
    if not token or any(ch.isspace() for ch in token):
        return None
    if any(ch in ILLUSTRATIVE_CHARS for ch in token) or "..." in token:
        return None
    if ":" in token:  # line-number citations (``foo.py`` + line) / URLs
        return None
    token = token.split("#", 1)[0]
    parts = [part for part in token.split("/") if part]
    if not parts or parts[0] not in REPO_ROOT_PREFIXES:
        return None
    if any(part in {"..", "."} for part in parts):
        return None
    if any(part in SIBLING_REPO_DIRS for part in parts):
        return None
    return "/".join(parts)


def collect_missing_repo_paths(
    sources: Iterable[Path], repo_root: Path
) -> tuple[MissingRepoPath, ...]:
    """Cited repo-root paths in ``sources`` that do not exist under ``repo_root``.

    ``sources`` is supplied by the caller (the link graph decides which markdown
    files make up the corpus) so this module stays walk-free and testable.
    """
    findings: list[MissingRepoPath] = []
    for source in sources:
        source_rel = _rel(source, repo_root=repo_root)
        if is_dated_record(source_rel):
            continue
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            continue
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or line.lstrip().startswith("$ "):
                continue
            for match in BACKTICK_RE.finditer(line):
                cited = normalize_cited_repo_path(match.group(1))
                if cited is None:
                    continue
                if not (repo_root / cited).exists():
                    findings.append(
                        MissingRepoPath(source=source_rel, line=lineno, token=cited)
                    )
    return tuple(findings)


def baseline_counts(findings: Iterable[MissingRepoPath]) -> dict[str, int]:
    """``source -> finding count`` for the committed ``file<TAB>count`` baseline."""
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.source] = counts.get(finding.source, 0) + 1
    return counts


def render_baseline(findings: Iterable[MissingRepoPath]) -> str:
    counts = baseline_counts(findings)
    lines = list(BASELINE_HEADER)
    lines.extend(f"{source}\t{counts[source]}" for source in sorted(counts))
    return "\n".join(lines) + "\n"


def load_path_baseline(path: Path) -> dict[str, int]:
    """Read ``file<TAB>count`` lines; ``#`` comments and blanks are ignored."""
    counts: dict[str, int] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return counts
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        source, _, count = line.partition("\t")
        try:
            counts[source.strip()] = int(count.strip())
        except ValueError:
            continue
    return counts


def path_regressions(
    findings: Iterable[MissingRepoPath], baseline: dict[str, int]
) -> tuple[MissingRepoPath, ...]:
    """Findings that exceed the baseline for their file (new file or grown count).

    A file whose count dropped (or vanished) is a pass: the ratchet only turns
    one way and a shrinking baseline is the point.
    """
    findings = tuple(findings)
    counts = baseline_counts(findings)
    regressing = {source for source, n in counts.items() if n > baseline.get(source, 0)}
    return tuple(f for f in findings if f.source in regressing)
