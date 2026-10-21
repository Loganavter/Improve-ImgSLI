"""``help_figures_suite``: one entry point over both Help-figure manifests.

No display and no app here: ``subprocess.run`` is replaced by a recorder, so a
test proves the command lines, the stage order, the fail-fast rule, the summary
block and the timeout-as-failed-stage rule without capturing anything.

Falsification: a base checkout has no ``src/devtools/help_figures_suite.py``, so
every test below fails at import (and the dry-run assertion would print nothing).
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from devtools import help_figures_suite as suite


class _Runner:
    """Stand-in for ``subprocess.run``: records the call, answers per script."""

    def __init__(self, codes=None, output=None, hook=None):
        self.codes = dict(codes or {})
        self.output = dict(output or {})
        self.hook = hook
        self.calls: list[dict] = []

    def __call__(self, argv, **kwargs):
        self.calls.append({"argv": list(argv), "kwargs": kwargs})
        script = Path(argv[1]).name
        if self.hook is not None:
            replaced = self.hook(script, argv, kwargs)
            if replaced is not None:
                return replaced
        stdout, stderr = self.output.get(script, (f"{script}: done\n", ""))
        return subprocess.CompletedProcess(
            args=list(argv), returncode=self.codes.get(script, 0), stdout=stdout, stderr=stderr
        )

    @property
    def scripts(self) -> list[str]:
        return [Path(call["argv"][1]).name for call in self.calls]


@pytest.fixture()
def fake_run(monkeypatch):
    """Install a recorder; a test mutates ``runner.codes`` / ``runner.output``."""

    def install(codes=None, output=None, hook=None):
        runner = _Runner(codes=codes, output=output, hook=hook)
        monkeypatch.setattr(suite.subprocess, "run", runner)
        return runner

    return install


# ---------------------------------------------------------------------------
# --dry-run: the whole procedure is legible without a display
# ---------------------------------------------------------------------------


def test_dry_run_prints_both_commands_and_runs_nothing(fake_run, capsys, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    runner = fake_run(hook=lambda *a: pytest.fail("--dry-run must not run anything"))

    assert suite.main(["--dry-run"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2, "one command line per stage, nothing else"
    devtool, live = (shlex.split(line) for line in lines)
    assert devtool == [sys.executable, str(suite.DEVTOOL_SCRIPT), "--all", "--jobs", "4"]
    assert live == [sys.executable, str(suite.LIVE_SCRIPT), "--all"]
    assert runner.calls == []


def test_dry_run_follows_only_and_jobs_without_a_run(fake_run, capsys):
    runner = fake_run()

    assert suite.main(["--dry-run", "--only", "live", "--jobs", "2"]) == 0
    assert suite.main(["--dry-run", "--only", "devtool", "--jobs", "2"]) == 0

    out = capsys.readouterr().out.splitlines()
    assert len(out) == 2
    assert shlex.split(out[0]) == [sys.executable, str(suite.LIVE_SCRIPT), "--all"]
    devtool = shlex.split(out[1])
    assert devtool[devtool.index("--jobs") + 1] == "2"
    assert runner.calls == []


# ---------------------------------------------------------------------------
# Stage execution (subprocess replaced)
# ---------------------------------------------------------------------------


def test_both_stages_green_print_the_summary_and_exit_zero(fake_run, capsys):
    runner = fake_run()

    assert suite.main([]) == 0

    out = capsys.readouterr().out
    assert runner.scripts == ["help_figures.py", "help_live.py"], "devtool first, then live"
    # Counts pin the committed manifests: 6 covered x 4 locales x 2 themes,
    # and 14 single-variant live figures. A manifest change must be re-pinned.
    assert re.search(r"^devtool: exit=0 \d+\.\ds cells=48$", out, re.M)
    assert re.search(r"^live: exit=0 \d+\.\ds cells=14$", out, re.M)
    assert out.rstrip().endswith("suite: ok")
    for call in runner.calls:
        assert call["kwargs"]["cwd"] == str(suite.REPO_ROOT)
        assert call["kwargs"]["text"] is True
        assert call["kwargs"]["capture_output"] is True
        assert call["kwargs"]["timeout"] == suite.DEFAULT_TIMEOUT_S


def test_second_stage_failure_fails_the_suite_and_names_it(fake_run, capsys):
    runner = fake_run(
        codes={"help_live.py": 1},
        output={"help_live.py": ("", "FAILED help-toolbar [en/dark]: app did not boot\n")},
    )

    assert suite.main([]) == 1

    captured = capsys.readouterr()
    assert runner.scripts == ["help_figures.py", "help_live.py"]
    assert re.search(r"^devtool: exit=0 \d+\.\ds cells=48$", captured.out, re.M)
    assert re.search(r"^live: exit=1 \d+\.\ds cells=14$", captured.out, re.M)
    assert captured.out.rstrip().endswith("suite: failed")
    assert "FAILED help-toolbar [en/dark]: app did not boot" in captured.err, (
        "the failing stage's tail must be visible, not just its exit code"
    )


def test_failed_first_stage_skips_live_and_is_never_retried(fake_run, capsys):
    runner = fake_run(codes={"help_figures.py": 2})

    assert suite.main([]) == 2

    captured = capsys.readouterr()
    assert runner.scripts == ["help_figures.py"], "no retry, and live must not run after a red devtool stage"
    assert "devtool: exit=2" in captured.out
    assert "live:" not in captured.out, "a stage that never ran gets no summary row"
    assert "suite: failed" in captured.out
    assert "skipping live" in captured.err


def test_a_signalled_stage_reports_its_code_and_fails_the_run(fake_run, capsys):
    """A killed stage (negative code) must still exit the suite with a failure."""
    fake_run(hook=lambda script, argv, kwargs: subprocess.CompletedProcess(argv, -9, "", ""))

    assert suite.main([]) == 1

    out = capsys.readouterr().out
    assert re.search(r"^devtool: exit=-9 \d+\.\ds cells=48$", out, re.M)
    assert out.rstrip().endswith("suite: failed")


def test_timeout_is_a_failed_stage_naming_the_violation(fake_run, capsys):
    def _timeout(script, argv, kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=b"partial live boot log\n")

    runner = fake_run(hook=_timeout)

    assert suite.main(["--only", "live"]) == suite.TIMEOUT_EXIT

    captured = capsys.readouterr()
    assert runner.scripts == ["help_live.py"], "a timeout is reported, never retried"
    assert f"live: exit={suite.TIMEOUT_EXIT}" in captured.out
    assert "suite: failed" in captured.out
    assert "timed out after 1800s" in captured.err
    assert "violation: a stage must finish inside its budget" in captured.err
    assert "partial live boot log" in captured.err


def test_run_stage_keeps_only_the_tail_of_both_streams(monkeypatch):
    stdout = "\n".join(f"out{index}" for index in range(30))
    stderr = "\n".join(f"err{index}" for index in range(5))
    monkeypatch.setattr(
        suite.subprocess,
        "run",
        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 7, stdout, stderr),
    )

    result = suite.run_stage("devtool", ["devtool", "--all"], cwd=suite.REPO_ROOT, timeout_s=5)

    assert (result.name, result.returncode, result.argv) == ("devtool", 7, ["devtool", "--all"])
    assert len(result.tail) == suite.TAIL_LINES
    assert result.tail[-1] == "err4", "stderr follows stdout in the tail"
    assert "out0" not in result.tail
    assert re.fullmatch(r"devtool: exit=7 \d+\.\ds cells=48", suite.summary_line(result, 48))


# ---------------------------------------------------------------------------
# --check: the drift gate covers the devtool set only
# ---------------------------------------------------------------------------


def test_check_runs_only_the_devtool_gate_and_never_boots_the_app(fake_run, capsys):
    runner = fake_run()

    assert suite.main(["--check"]) == 0

    out = capsys.readouterr().out
    assert runner.scripts == ["help_figures.py"]
    argv = runner.calls[0]["argv"]
    assert argv == [sys.executable, str(suite.DEVTOOL_SCRIPT), "--check", "--jobs", "4"]
    for call in runner.calls:
        assert "--all" not in call["argv"], "a check must not generate a live capture"
    assert suite.UNVERIFIED_LIVE in out
    assert "live: unverified — no sha256 baseline yet (P10-D)" in out
    assert out.rstrip().endswith("suite: ok")


def test_check_exits_with_the_devtool_drift_code(fake_run, capsys):
    runner = fake_run(codes={"help_figures.py": 1})

    assert suite.main(["--check"]) == 1

    captured = capsys.readouterr()
    assert runner.scripts == ["help_figures.py"]
    assert "devtool: exit=1" in captured.out
    assert "suite: failed" in captured.out
    assert suite.UNVERIFIED_LIVE in captured.out, (
        "a drifted check must still say the live set was not compared"
    )


def test_check_with_only_live_is_refused_before_any_run(fake_run, capsys):
    runner = fake_run()

    with pytest.raises(SystemExit) as exc:
        suite.main(["--check", "--only", "live"])

    assert exc.value.code == 2
    assert runner.calls == []
    assert "no sha256 baseline yet" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# --only / argparse
# ---------------------------------------------------------------------------


def test_only_live_runs_exactly_one_stage(fake_run, capsys):
    runner = fake_run()

    assert suite.main(["--only", "live"]) == 0

    out = capsys.readouterr().out
    assert runner.scripts == ["help_live.py"]
    assert runner.calls[0]["argv"] == [sys.executable, str(suite.LIVE_SCRIPT), "--all"]
    assert re.search(r"^live: exit=0 \d+\.\ds cells=14$", out, re.M)
    assert "devtool:" not in out
    assert out.rstrip().endswith("suite: ok")


def test_only_devtool_runs_exactly_one_stage(fake_run, capsys):
    runner = fake_run()

    assert suite.main(["--only", "devtool"]) == 0

    out = capsys.readouterr().out
    assert runner.scripts == ["help_figures.py"]
    assert "live:" not in out
    assert out.rstrip().endswith("suite: ok")


def test_unknown_only_stage_is_rejected():
    with pytest.raises(SystemExit) as exc:
        suite.main(["--only", "bogus"])

    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Cell counts come from the manifests, read as data (no capture import)
# ---------------------------------------------------------------------------


def test_manifest_cells_match_the_committed_manifests():
    assert suite.manifest_cells(suite.DEVTOOL_MANIFEST) == 48
    assert suite.manifest_cells(suite.LIVE_MANIFEST) == 14


def test_manifest_cells_skips_uncovered_and_survives_a_broken_file(tmp_path):
    manifest = tmp_path / "figures.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "figures": [
                    {"id": "uncovered", "covered": False, "locales": ["en", "ru"]},
                    {"id": "matrix", "locales": ["en", "ru", "zh"], "themes": ["dark", "light"]},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert suite.manifest_cells(manifest) == 6
    assert suite.manifest_cells(tmp_path / "no-such-manifest.json") == 0

    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert suite.manifest_cells(broken) == 0


def test_plan_orders_the_stages_and_has_no_live_stage_under_check():
    assert [stage.name for stage in suite.plan()] == ["devtool", "live"]
    assert [stage.name for stage in suite.plan(check=True)] == ["devtool"]
    assert [stage.name for stage in suite.plan(only="live")] == ["live"]
