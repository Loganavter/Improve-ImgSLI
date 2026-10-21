#!/usr/bin/env python3
"""One entry point over BOTH Help-figure manifests: devtool figures, then live.

Devtool only. ``help_figures.py`` renders the reproducible surfaces from
``help_figures.json``; ``help_live.py`` drives a real app instance for the
figures that only exist in a running window (``help_figures_live.json``). Both
own their own contract, and both must stay separate processes — they create a
``QApplication`` and spawn capture pools — so this module never imports either
one; it only runs them, in order, and reports.

    python src/devtools/help_figures_suite.py              # devtool, then live
    python src/devtools/help_figures_suite.py --dry-run    # print the commands
    python src/devtools/help_figures_suite.py --only live
    python src/devtools/help_figures_suite.py --check      # devtool drift gate

Why a single entry point: the terminal criterion of the Help-figure work is
"a cold checkout, one launch and a few minutes of waiting is the entire
procedure" — judgement belongs to authoring the scenario and reviewing the
content, never to remembering which script runs with which flags in which
order.

The run is **fail-fast**: a red devtool stage makes the live stage pointless
(the live stage boots an app instance per figure), so the suite stops at the
first failing stage, names it and prints the tail of its output. There is no
retry and no "continue anyway" flag — a failed stage is a failed run.

``--check`` is the drift gate and only the devtool set has a sha256 baseline;
the live slot prints ``live: unverified — no sha256 baseline yet (P10-D)``
instead of booting an app (so ``--check --only live`` is refused: it would
verify nothing).
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

#: Repo root (``<repo>/src/devtools/help_figures_suite.py`` -> ``<repo>``).
REPO_ROOT = Path(__file__).resolve().parents[2]
DEVTOOL_SCRIPT = Path("src/devtools") / "help_figures.py"
LIVE_SCRIPT = Path("src/devtools") / "help_live.py"
DEVTOOL_MANIFEST = Path("src/devtools") / "help_figures.json"
LIVE_MANIFEST = Path("src/devtools") / "help_figures_live.json"
STAGES = ("devtool", "live")
#: Devtool capture workers per stage run. A cell is dominated by its settle
#: pump, so four is the measured-parallelism default of ``help_figures.py``.
DEFAULT_JOBS = 4
#: Per-stage budget. Generous because the live stage boots one app instance per
#: figure; exceeding it is a failed stage naming the violation, never a hang.
DEFAULT_TIMEOUT_S = 1800.0
#: How many of a stage's last stdout+stderr lines the summary keeps.
TAIL_LINES = 20
#: A stage that ran out of budget, spelled the way ``timeout(1)`` spells it.
TIMEOUT_EXIT = 124
#: Printed in the live slot of a ``--check`` run. Pinned verbatim so a reader
#: (or a CI log scan) can tell "not gated" apart from "gated and clean".
UNVERIFIED_LIVE = "live: unverified — no sha256 baseline yet (P10-D)"


@dataclass(frozen=True)
class StageResult:
    """What one stage did: its command, exit code, wall time and output tail."""

    name: str
    argv: list[str]
    returncode: int
    duration_s: float
    tail: list[str]


@dataclass(frozen=True)
class Stage:
    """A stage before it runs: the command line and the cells it stands for."""

    name: str
    argv: list[str]
    cells: int


def devtool_argv(*, jobs: int = DEFAULT_JOBS, check: bool = False) -> list[str]:
    """Command line for the devtool stage (``--jobs`` belongs to this one only)."""
    mode = "--check" if check else "--all"
    return [sys.executable, str(DEVTOOL_SCRIPT), mode, "--jobs", str(jobs)]


def live_argv() -> list[str]:
    """Command line for the live stage: no ``--jobs`` and no drift mode."""
    return [sys.executable, str(LIVE_SCRIPT), "--all"]


def manifest_cells(manifest: Path | str) -> int:
    """``figure x locale x theme`` units in a manifest, uncovered entries skipped.

    Read as plain JSON, never through the owning module: importing
    ``help_figures`` would pull the capture stack into this process, and the
    count is a workload figure, not a validation. A missing or broken manifest
    counts 0 — the stage that owns it reports the real error.
    """
    try:
        raw = json.loads(Path(manifest).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    total = 0
    for entry in raw.get("figures") or []:
        if not entry.get("covered", True):
            continue
        total += len(entry.get("locales") or ["en"]) * len(entry.get("themes") or ["dark"])
    return total


def plan(
    *,
    jobs: int = DEFAULT_JOBS,
    check: bool = False,
    only: str | None = None,
) -> list[Stage]:
    """The stages a run would execute, devtool first.

    ``--check`` leaves the live slot out of the plan on purpose: it has no
    baseline to compare against, and booting nine app instances to not compare
    them would be the opposite of the one-launch criterion. The slot still
    speaks — :func:`main` prints :data:`UNVERIFIED_LIVE` in its place.
    """
    stages: list[Stage] = []
    if only in (None, "devtool"):
        stages.append(
            Stage("devtool", devtool_argv(jobs=jobs, check=check), manifest_cells(DEVTOOL_MANIFEST))
        )
    if only in (None, "live") and not check:
        stages.append(Stage("live", live_argv(), manifest_cells(LIVE_MANIFEST)))
    return stages


def _as_text(value: str | bytes | None) -> str:
    """Timeout output arrives as bytes on some paths and str on others."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _tail(*streams: str | None, limit: int = TAIL_LINES) -> list[str]:
    """Last ``limit`` non-blank lines of the given streams, in stream order."""
    lines = [line for stream in streams for line in (stream or "").splitlines() if line.strip()]
    return lines[-limit:]


def run_stage(
    name: str,
    argv: list[str],
    *,
    cwd: Path,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> StageResult:
    """Run one stage to completion without streaming, keeping its output tail.

    A timeout is a failed stage naming the violation, not an exception into the
    caller and never a hang: the summary must always say what happened.
    """
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(argv),
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        tail = _tail(_as_text(exc.stdout), _as_text(exc.stderr))
        tail.append(f"{name}: timed out after {timeout_s:.0f}s (violation: a stage must finish inside its budget)")
        return StageResult(
            name=name,
            argv=list(argv),
            returncode=TIMEOUT_EXIT,
            duration_s=time.monotonic() - started,
            tail=tail,
        )
    return StageResult(
        name=name,
        argv=list(argv),
        returncode=completed.returncode,
        duration_s=time.monotonic() - started,
        tail=_tail(completed.stdout, completed.stderr),
    )


def summary_line(result: StageResult, cells: int) -> str:
    """One deterministic summary row: ``<name>: exit=<code> <duration>s cells=<n>``."""
    return f"{result.name}: exit={result.returncode} {result.duration_s:.1f}s cells={cells}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="help_figures_suite",
        description="Capture every Help figure: devtool recipes first, then the live set.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the command lines and exit (no display, nothing is captured)",
    )
    parser.add_argument("--only", choices=STAGES, default=None, metavar="STAGE", help="run one stage only")
    parser.add_argument(
        "--check", action="store_true",
        help="regenerate the devtool set and compare sha256 (exit 1 on drift); live is unverified",
    )
    parser.add_argument(
        "--jobs", type=int, default=DEFAULT_JOBS, metavar="N",
        help=f"devtool capture workers (default {DEFAULT_JOBS}; live has no --jobs)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.check and args.only == "live":
        parser.error(
            "--check cannot verify the live set (no sha256 baseline yet, P10-D); "
            "run --check without --only, or --only live to capture"
        )
    stages = plan(jobs=args.jobs, check=args.check, only=args.only)
    if args.dry_run:
        for stage in stages:
            print(shlex.join(stage.argv))
        if args.check:
            print(UNVERIFIED_LIVE)
        return 0

    exit_code = 0
    for index, stage in enumerate(stages):
        result = run_stage(stage.name, stage.argv, cwd=REPO_ROOT)
        print(summary_line(result, stage.cells))
        if result.returncode == 0:
            continue
        exit_code = result.returncode if result.returncode > 0 else 1
        if result.tail:
            print(f"{stage.name}: last {len(result.tail)} line(s) of its output:", file=sys.stderr)
            for line in result.tail:
                print(f"  {line}", file=sys.stderr)
        skipped = [later.name for later in stages[index + 1:]]
        if skipped:
            print(
                f"skipping {', '.join(skipped)}: {stage.name} failed "
                "(no retry, no continue-anyway)",
                file=sys.stderr,
            )
        break
    if args.check:
        # Not gated whether the devtool stage passed or drifted: a reader must
        # never read "suite: ok" as "every figure was compared".
        print(UNVERIFIED_LIVE)
    print(f"suite: {'ok' if exit_code == 0 else 'failed'}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
