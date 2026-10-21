#!/usr/bin/env python3
"""Doc-home guard: knowledge-plane artifacts must not live in app-repo markdown.

The split (docs-orchestrator decision map) is: this repo keeps *living* docs
(``docs/dev/**``), tab-owned docs (``src/tabs/<tab>/docs/**``) and in-app help
manual bodies (``src/**/resources/help/**``); planning / review / audit /
recon material lives in the private ``improve-imgsli-internal-docs`` knowledge
plane (``docs/backlog/``, ``docs/catalog.yaml``, ``docs/legacy/``).

Six such docs leaked into this repo (a prose plan, a per-owner plan, a recon
note, an MCP plan, a wedged-toast session report, …) and were removed in
PR #514 — but only by hand, so nothing stopped the next one from landing and
agents kept executing stale plan text as truth. This guard classifies every
tracked ``*.md`` by CONTENT *and* PATH and fails on an artifact outside its
sanctioned home. Any single signal is enough:

- frontmatter ``id:`` in the knowledge-plane namespace (``plan-``, ``session-``,
  ``audit-``, ``inv-``, ``task-``, ``adr-``);
- an H1 titled Plan / Session report / Audit / Recon / Investigation, an H1
  containing "— plan", or an H1 that is "Development TODO";
- ``Status: done|shipped|approved`` within the first 10 lines;
- a filename shaped like ``SESSION_*``, ``INCIDENT_*``, ``plan-*``,
  ``audit-*``, ``inv-*``, ``*_PLAN.md``, ``*-report.md``, ``*recon.md``;
- a path under ``docs/backlog/``, ``docs/legacy/``, or ``docs/catalog.yaml``.

Sanctioned homes are narrow and every allowed file reports *why* it is allowed:

- ``docs/dev/**`` — living docs. A signal here is still a violation (that is
  exactly where the six leaks lived); the single named exception is
  ``docs/dev/TODO.md``, the canonical host backlog this guard protects.
- ``src/tabs/<tab>/docs/**`` — legal, including ``docs/investigations/**``
  (tab-scoped plans are the decision-map-sanctioned shape). An artifact in a
  tab's ``docs/`` outside ``investigations/`` is allowed-but-warned: it belongs
  in the investigations folder.
- ``src/**/resources/help/**`` — shipped manual bodies.

The scan is read-only, imports nothing from the app, does no network I/O, and
runs from a bare checkout: tracked files come from ``git ls-files`` when the
root is a git repo, otherwise from a filesystem walk (tests use plain tmp
trees).

Usage:
    python src/devtools/check_doc_home.py
    python src/devtools/check_doc_home.py --json
    python src/devtools/check_doc_home.py --strict    # warnings fail too
    python src/devtools/check_doc_home.py --verbose   # also list allowed files

Exit codes: 0 clean, 1 violations (or warnings under ``--strict``),
2 could-not-check (missing root, unreadable file).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

#: Frontmatter ``id:`` prefixes owned by the knowledge plane.
ARTIFACT_ID_PREFIXES = ("plan-", "session-", "audit-", "inv-", "task-", "adr-")

#: Filename schemes of knowledge-plane artifacts: ``(label, pattern)``.
FILENAME_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Uppercase-prefixed schemes stay case-sensitive on purpose: a lowercase
    # ``session_picker.md`` is a tab plugin doc, not a session record.
    ("SESSION_*", re.compile(r"^SESSION_")),
    ("INCIDENT_*", re.compile(r"^INCIDENT_")),
    ("plan-*", re.compile(r"^plan-", re.IGNORECASE)),
    ("audit-*", re.compile(r"^audit-", re.IGNORECASE)),
    ("inv-*", re.compile(r"^inv-", re.IGNORECASE)),
    ("*_PLAN.md", re.compile(r"_plan\.md$", re.IGNORECASE)),
    # Both separators: the real leak was ``toast_stuck_session_report.md``.
    ("*-report.md", re.compile(r"[-_]report\.md$", re.IGNORECASE)),
    ("*recon.md", re.compile(r"recon\.md$", re.IGNORECASE)),
)

#: Knowledge-plane locations inside this repo.
PATH_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("docs/backlog/", re.compile(r"^docs/backlog/")),
    ("docs/catalog.yaml", re.compile(r"^docs/catalog\.yaml$")),
    ("docs/legacy/", re.compile(r"^docs/legacy/")),
)

#: Non-markdown files that are knowledge-plane artifacts by path alone
#: (``docs/catalog.yaml`` is the registry the internal-docs plane owns).
EXTRA_WATCHED_PATHS = ("docs/catalog.yaml",)

#: The one ``docs/dev/`` file allowed to carry an artifact-shaped H1: the
#: canonical host backlog (its H1 is ``# Development TODO`` by contract).
CANONICAL_BACKLOG = "docs/dev/TODO.md"

#: Directories never worth walking in the non-git fallback.
_SKIP_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "venv",
        "node_modules",
        "build",
        "dist",
        "site-packages",
    }
)

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_STATUS_RE = re.compile(r"^Status:\s*(?:done|shipped|approved)\b", re.IGNORECASE)
_FRONTMATTER_ID_RE = re.compile(
    r"^id:\s*[\"']?(?:" + "|".join(re.escape(p) for p in ARTIFACT_ID_PREFIXES) + ")", re.IGNORECASE
)
#: H1 labels that name an artifact rather than a living doc. The trailing
#: ``\b`` keeps ``# Auditing the loader`` from matching ``# Audit``.
_H1_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Plan", re.compile(r"^plan\b", re.IGNORECASE)),
    ("Session report", re.compile(r"^session report\b", re.IGNORECASE)),
    ("Audit", re.compile(r"^audit\b", re.IGNORECASE)),
    ("Recon", re.compile(r"^recon\b", re.IGNORECASE)),
    ("Investigation", re.compile(r"^investigation\b", re.IGNORECASE)),
)
#: Em/en dash + "plan" anywhere in the H1 (``# Help — plan of record``).
_H1_DASH_PLAN_RE = re.compile(r"[\u2014\u2013]\s*plan\b", re.IGNORECASE)
_DEVELOPMENT_TODO = "development todo"


@dataclass(frozen=True, slots=True)
class Signal:
    """One knowledge-plane signal found in a file."""

    kind: str  # filename | h1 | frontmatter-id | status | path
    detail: str  # why this is an artifact (the "reason" in the report line)


@dataclass(frozen=True, slots=True)
class Entry:
    """A scanned file that carries at least one signal."""

    path: str  # repo-relative POSIX path
    signal: Signal
    why: str = ""  # why it was allowed (empty for violations)


@dataclass(frozen=True, slots=True)
class Report:
    scanned: tuple[str, ...]  # every checked path, sorted
    violations: tuple[Entry, ...]
    allowed: tuple[Entry, ...]
    warnings: tuple[Entry, ...]  # allowed only by a broad rule (fail under --strict)
    unreadable: tuple[str, ...] = ()


def default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _tracked_paths(root: Path) -> list[str] | None:
    """``git ls-files`` output for the root, or None when git is unusable."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", "*.md"],
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    raw = proc.stdout.decode("utf-8", "surrogateescape")
    return [name for name in raw.split("\0") if name]


def _walked_paths(root: Path) -> list[str]:
    out: list[str] = []
    for path in root.rglob("*.md"):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        out.append(_rel(path, root=root))
    return out


def discover_paths(root: Path) -> list[str]:
    """Checked paths: tracked markdown (+ watched artifact paths), sorted."""
    tracked = _tracked_paths(root)
    candidates = tracked if tracked is not None else _walked_paths(root)
    rels = {rel for rel in candidates if (root / rel).is_file()}
    rels.update(p for p in EXTRA_WATCHED_PATHS if (root / p).is_file())
    return sorted(rels)


def _frontmatter_lines(lines: Sequence[str]) -> list[str]:
    """Lines of a leading ``---`` YAML block (empty when there is none)."""
    if not lines or lines[0].strip() != "---":
        return []
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return list(lines[1:index])
    return []


def _first_h1(lines: Sequence[str]) -> tuple[int, str] | None:
    """First level-1 heading outside fenced code, as ``(lineno, text)``."""
    in_fence = False
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(stripped)
        if match and match.group(1) == "#":
            return lineno, match.group(2).strip()
    return None


def find_signals(rel_path: str, text: str) -> list[Signal]:
    """Every artifact signal in one file (sorted, deduplicated by kind+detail)."""
    lines = text.splitlines()
    signals: list[Signal] = []

    for label, pattern in PATH_SIGNALS:
        if pattern.search(rel_path):
            signals.append(
                Signal(
                    kind="path",
                    detail=(
                        f"path '{label}' is a knowledge-plane location "
                        "(backlog/catalog/legacy lives in improve-imgsli-internal-docs)"
                    ),
                )
            )

    name = rel_path.rsplit("/", 1)[-1]
    for label, pattern in FILENAME_SIGNALS:
        if pattern.search(name):
            signals.append(
                Signal(
                    kind="filename",
                    detail=(
                        f"name '{name}' matches '{label}'; plan/report/recon records "
                        "belong in the internal-docs knowledge plane, not in this repo"
                    ),
                )
            )

    for line in _frontmatter_lines(lines):
        match = _FRONTMATTER_ID_RE.match(line.strip())
        if match:
            ident = line.strip().split(":", 1)[1].strip().strip("\"'")
            signals.append(
                Signal(
                    kind="frontmatter-id",
                    detail=(
                        f"frontmatter id '{ident}' uses the knowledge-plane artifact "
                        "namespace (plan-/session-/audit-/inv-/task-/adr-)"
                    ),
                )
            )
            break

    heading = _first_h1(lines)
    if heading is not None:
        _, text_of_heading = heading
        lowered = text_of_heading.lower()
        if lowered == _DEVELOPMENT_TODO:
            signals.append(
                Signal(
                    kind="h1",
                    detail=(
                        "H1 '# Development TODO' is a backlog document shape; the app "
                        "repo does not own a development backlog"
                    ),
                )
            )
        else:
            for label, pattern in _H1_SIGNALS:
                if pattern.match(lowered):
                    signals.append(
                        Signal(
                            kind="h1",
                            detail=(
                                f"H1 '# {text_of_heading}' is a '{label}' record; such "
                                "docs belong in the internal-docs knowledge plane"
                            ),
                        )
                    )
                    break
            if _H1_DASH_PLAN_RE.search(text_of_heading):
                signals.append(
                    Signal(
                        kind="h1",
                        detail=(
                            f"H1 '# {text_of_heading}' is a '<topic> — plan' heading; "
                            "plans belong in the internal-docs knowledge plane"
                        ),
                    )
                )

    for lineno, line in enumerate(lines[:10], start=1):
        if _STATUS_RE.match(line.strip()):
            signals.append(
                Signal(
                    kind="status",
                    detail=(
                        f"line {lineno} '{line.strip()}' marks a closed work record, "
                        "not a living doc"
                    ),
                )
            )
            break

    deduped: list[Signal] = []
    for signal in signals:
        if signal not in deduped:
            deduped.append(signal)
    return deduped


def sanction(rel_path: str) -> tuple[str, bool] | None:
    """``(why_allowed, is_warning)`` for a sanctioned home, else None."""
    if rel_path == CANONICAL_BACKLOG:
        return (
            "canonical host backlog — the living backlog this guard protects, "
            "whose H1 is '# Development TODO' by contract",
            False,
        )
    if rel_path.startswith("docs/dev/"):
        # Living docs: a signal here is exactly the leak this guard exists for.
        return None
    if re.match(r"^src/tabs/[^/]+/docs/", rel_path):
        if "/docs/investigations/" in rel_path:
            return (
                "tab-scoped investigation — legal per the docs-orchestrator "
                "decision map (src/tabs/<tab>/docs/investigations/)",
                False,
            )
        return (
            "tab-owned docs are legal, but artifact-class docs belong in "
            "src/tabs/<tab>/docs/investigations/",
            True,
        )
    if re.match(r"^src/(?:[^/]+/)*resources/help/", rel_path):
        return ("in-app help manual body — the help plane owns its text", False)
    return None


def scan_repo(root: Path) -> Report:
    """Scan ``root`` and classify every signal-carrying file."""
    scanned: list[str] = []
    violations: list[Entry] = []
    allowed: list[Entry] = []
    warnings: list[Entry] = []
    unreadable: list[str] = []

    for rel_path in discover_paths(root):
        scanned.append(rel_path)
        try:
            text = (root / rel_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(rel_path)
            continue
        for signal in find_signals(rel_path, text):
            decision = sanction(rel_path)
            if decision is None:
                violations.append(Entry(path=rel_path, signal=signal))
                continue
            why, is_warning = decision
            entry = Entry(path=rel_path, signal=signal, why=why)
            if is_warning:
                warnings.append(entry)
            else:
                allowed.append(entry)

    def _order(entry: Entry) -> tuple[str, str, str]:
        return (entry.path, entry.signal.kind, entry.signal.detail)

    return Report(
        scanned=tuple(scanned),
        violations=tuple(sorted(set(violations), key=_order)),
        allowed=tuple(sorted(set(allowed), key=_order)),
        warnings=tuple(sorted(set(warnings), key=_order)),
        unreadable=tuple(sorted(unreadable)),
    )


def _print_report(report: Report, *, strict: bool, verbose: bool) -> None:
    for entry in report.violations:
        print(f"{entry.path}: {entry.signal.kind} — {entry.signal.detail}")
    for entry in report.unreadable:
        print(f"{entry}: unreadable — could not classify this file")
    if strict:
        for entry in report.warnings:
            print(f"{entry.path}: {entry.signal.kind} — {entry.signal.detail} [warning, --strict]")
    elif verbose:
        for entry in report.warnings:
            print(f"{entry.path}: {entry.signal.kind} — allowed (warning): {entry.why}")
    if verbose:
        for entry in report.allowed:
            print(f"{entry.path}: {entry.signal.kind} — allowed: {entry.why}")

    violations = len(report.violations) + (len({e.path for e in report.warnings}) if strict else 0)
    allowed = len({e.path for e in report.allowed})
    warned = len({e.path for e in report.warnings})
    summary = f"doc-home: {violations} violation(s), {allowed} allowed, {len(report.scanned)} scanned"
    if warned and not strict:
        summary += f", {warned} warning(s)"
    if report.unreadable:
        summary += f", {len(report.unreadable)} unreadable"
    print(summary)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Knowledge-plane artifact guard for markdown.")
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--strict", action="store_true", help="treat allowed-but-warned files as violations")
    parser.add_argument("--verbose", action="store_true", help="also list allowed files and why")
    args = parser.parse_args(list(argv) if argv is not None else None)

    root: Path = args.repo_root
    if not root.is_dir():
        print(f"doc-home: cannot check: repository root not found: {root}", file=sys.stderr)
        return 2

    report = scan_repo(root)

    if args.json:
        payload = {
            "scanned": len(report.scanned),
            "violations": [
                {"path": e.path, "signal": e.signal.kind, "reason": e.signal.detail}
                for e in report.violations
            ],
            "allowed": [
                {"path": e.path, "signal": e.signal.kind, "reason": e.why} for e in report.allowed
            ],
            "warnings": [
                {"path": e.path, "signal": e.signal.kind, "reason": e.why} for e in report.warnings
            ],
            "unreadable": list(report.unreadable),
            "strict": args.strict,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_report(report, strict=args.strict, verbose=args.verbose)

    if report.unreadable:
        print(
            f"doc-home: could not check {len(report.unreadable)} file(s); "
            "fix readability before trusting this run",
            file=sys.stderr,
        )
        return 2
    if report.violations or (args.strict and report.warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
