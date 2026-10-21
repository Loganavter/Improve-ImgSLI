"""Falsifiable guard for ``devtools.check_doc_home`` (knowledge-plane artifacts).

Every test builds its own tmp tree and passes the root explicitly, so the suite
needs neither a git repo nor the app's real checkout. ``find_signals`` is
exercised directly where the point is *which* signal fires; ``main`` where the
point is exit code / sanctioned-home behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from devtools.check_doc_home import default_repo_root, find_signals, main, scan_repo


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# --- one signal per test --------------------------------------------------


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("SESSION_2026-10-01.md", "# Session\n\nBody.\n"),
        ("INCIDENT_42.md", "# Incident\n\nBody.\n"),
        ("plan-help-prose.md", "# Whatever\n\nBody.\n"),
        ("audit-2026-10-01.md", "# Whatever\n\nBody.\n"),
        ("inv-loader-race.md", "# Whatever\n\nBody.\n"),
        ("HELP_PROSE_PLAN.md", "# Whatever\n\nBody.\n"),
        ("toast_stuck_report.md", "# Whatever\n\nBody.\n"),
        ("help-recon.md", "# Whatever\n\nBody.\n"),
    ],
)
def test_filename_signal_fires(name: str, document: str) -> None:
    """A knowledge-plane filename is a hit even with innocuous content."""
    kinds = [s.kind for s in find_signals(f"docs/archive/{name}", document)]
    assert kinds == ["filename"]


@pytest.mark.parametrize(
    "heading",
    [
        "# Plan: refactor the help prose",
        "# Session report: stuck loading toast",
        "# Audit 2026-08-25 orchestration halture",
        "# Recon notes for the help move",
        "# Investigation into the loader race",
        "# Help web-canon refactor — plan",
        "# Development TODO",
    ],
)
def test_h1_signal_fires(heading: str) -> None:
    """Each artifact heading shape is a hit on its own."""
    kinds = [s.kind for s in find_signals("docs/notes.md", f"{heading}\n\nBody.\n")]
    assert kinds == ["h1"]


def test_h1_signal_ignores_prose_that_merely_starts_with_the_word() -> None:
    """``# Auditing`` must not be read as ``# Audit`` (falsifies a loose prefix)."""
    assert find_signals("docs/notes.md", "# Auditing the loader\n\nBody.\n") == []


def test_h1_signal_skips_fenced_code() -> None:
    """A heading example inside a fence is not this doc's H1."""
    doc = "# Living doc\n\nThe old leak started with:\n\n```markdown\n# Plan: old\n```\n"
    assert find_signals("docs/notes.md", doc) == []


@pytest.mark.parametrize("prefix", ["plan", "session", "audit", "inv", "task", "adr"])
def test_frontmatter_id_signal_fires(prefix: str) -> None:
    """Frontmatter ids in the knowledge-plane namespace are a hit."""
    doc = f'---\nid: "{prefix}-something"\nstatus: active\n---\n\n# Living doc\n'
    kinds = [s.kind for s in find_signals("docs/dev/note.md", doc)]
    assert kinds == ["frontmatter-id"]


def test_frontmatter_id_outside_namespace_is_not_a_signal() -> None:
    """An unrelated frontmatter key/value is not an artifact id."""
    doc = "---\nid: helppage\n---\n\n# Living doc\n"
    assert find_signals("docs/dev/note.md", doc) == []


@pytest.mark.parametrize("status", ["done", "shipped", "approved"])
def test_status_line_signal_fires(status: str) -> None:
    """A closed-work-record status in the head of the doc is a hit."""
    doc = f"# Living doc\n\nStatus: {status}\n\nBody.\n"
    kinds = [s.kind for s in find_signals("docs/dev/note.md", doc)]
    assert kinds == ["status"]


def test_status_signal_only_reads_the_first_ten_lines() -> None:
    """A status line buried below the head is not the record marker."""
    doc = "# Living doc\n\n" + "filler\n\n" * 6 + "Status: done\n"
    assert find_signals("docs/dev/note.md", doc) == []


@pytest.mark.parametrize(
    "rel_path",
    ["docs/backlog/todo.md", "docs/legacy/old-notes.md", "docs/catalog.yaml"],
)
def test_path_signal_fires(rel_path: str) -> None:
    """A knowledge-plane location is a hit even with innocuous content."""
    kinds = [s.kind for s in find_signals(rel_path, "# Whatever\n\nBody.\n")]
    assert kinds == ["path"]


# --- sanctioned homes -----------------------------------------------------


def test_sanctioned_docs_dev_living_doc_passes(tmp_path: Path) -> None:
    """An innocuous ``docs/dev`` doc is neither a violation nor 'allowed'."""
    _write(tmp_path / "docs" / "dev" / "hello.md", "# Hello\n\nA living doc.\n")
    assert main(["--repo-root", str(tmp_path)]) == 0
    report = scan_repo(tmp_path)
    assert report.violations == ()
    assert report.allowed == ()
    assert report.scanned == ("docs/dev/hello.md",)


def test_docs_dev_plan_is_a_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``docs/dev`` is a living-docs home: a plan there is the leak itself."""
    _write(
        tmp_path / "docs" / "dev" / "HELP_PROSE_PLAN.md",
        "# Plan: refactor the help prose\n\nBody.\n",
    )
    assert main(["--repo-root", str(tmp_path)]) == 1
    out = capsys.readouterr().out
    assert "docs/dev/HELP_PROSE_PLAN.md: filename" in out
    assert "docs/dev/HELP_PROSE_PLAN.md: h1" in out
    assert "doc-home: 2 violation(s), 0 allowed, 1 scanned" in out


def test_canonical_backlog_is_allowed_with_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The host backlog keeps ``# Development TODO``; it passes even under --strict."""
    _write(tmp_path / "docs" / "dev" / "TODO.md", "# Development TODO\n\nOpen items.\n")
    assert main(["--repo-root", str(tmp_path), "--verbose", "--strict"]) == 0
    out = capsys.readouterr().out
    assert "allowed: canonical host backlog" in out
    assert "doc-home: 0 violation(s), 1 allowed, 1 scanned" in out


def test_development_todo_elsewhere_is_a_violation(tmp_path: Path) -> None:
    """The backlog shape outside its canonical home is an artifact."""
    _write(tmp_path / "docs" / "backlog-copy.md", "# Development TODO\n\nBody.\n")
    assert main(["--repo-root", str(tmp_path)]) == 1


def test_tab_scoped_plan_under_investigations_passes(tmp_path: Path) -> None:
    """Tab-scoped plans are legal (docs-orchestrator decision map) — even strict."""
    _write(
        tmp_path / "src" / "tabs" / "gallery" / "docs" / "investigations" / "plan-split.md",
        "# Plan — gallery split\n\nBody.\n",
    )
    argv = ["--repo-root", str(tmp_path), "--strict"]
    assert main(argv) == 0
    report = scan_repo(tmp_path)
    assert report.violations == ()
    assert report.warnings == ()
    assert {e.path for e in report.allowed} == {
        "src/tabs/gallery/docs/investigations/plan-split.md"
    }


def test_tab_artifact_outside_investigations_warns_and_strict_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Allowed by the tab-docs rule, but it belongs in ``investigations/``."""
    _write(
        tmp_path / "src" / "tabs" / "gallery" / "docs" / "audit-2026.md",
        "# Audit 2026\n\nBody.\n",
    )
    root = ["--repo-root", str(tmp_path)]
    assert main(root) == 0
    assert "1 warning(s)" in capsys.readouterr().out

    assert main([*root, "--strict"]) == 1
    out = capsys.readouterr().out
    assert "--strict]" in out
    assert "doc-home: 1 violation(s), 0 allowed, 1 scanned" in out


def test_help_manual_body_with_artifact_heading_is_allowed(tmp_path: Path) -> None:
    """Shipped help bodies are the help plane's text, not doc-plane artifacts."""
    _write(
        tmp_path / "src" / "resources" / "help" / "en" / "audit.md",
        "# Audit\n\nHow the audit panel works.\n",
    )
    assert main(["--repo-root", str(tmp_path), "--strict"]) == 0
    report = scan_repo(tmp_path)
    assert {e.path for e in report.allowed} == {"src/resources/help/en/audit.md"}


# --- CLI contract ---------------------------------------------------------


def test_exit_code_2_for_missing_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Cannot check is distinct from clean (0) and dirty (1)."""
    missing = tmp_path / "nope"
    assert main(["--repo-root", str(missing)]) == 2
    assert "cannot check" in capsys.readouterr().err


def test_exit_code_1_for_violation(tmp_path: Path) -> None:
    _write(tmp_path / "docs" / "notes" / "plan-x.md", "# Plan: x\n\nBody.\n")
    assert main(["--repo-root", str(tmp_path)]) == 1


def test_deterministic_order_and_summary_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Output is path-ordered and the summary counts violations/allowed/scanned."""
    _write(tmp_path / "docs" / "zeta" / "note.md", "# Audit 2026\n\nBody.\n")
    _write(tmp_path / "docs" / "alpha" / "note.md", "# Plan: x\n\nBody.\n")
    _write(tmp_path / "docs" / "dev" / "living.md", "# Living\n\nBody.\n")

    first = main(["--repo-root", str(tmp_path)])
    out_first = capsys.readouterr().out
    second = main(["--repo-root", str(tmp_path)])
    out_second = capsys.readouterr().out

    assert first == second == 1
    assert out_first == out_second
    lines = out_first.strip().splitlines()
    assert [line.split(":", 1)[0] for line in lines[:-1]] == [
        "docs/alpha/note.md",
        "docs/zeta/note.md",
    ]
    assert lines[-1] == "doc-home: 2 violation(s), 0 allowed, 3 scanned"


def test_json_report_lists_violation_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    _write(tmp_path / "docs" / "notes" / "note.md", "# Recon notes\n\nBody.\n")
    assert main(["--repo-root", str(tmp_path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["scanned"] == 1
    violation, = payload["violations"]
    assert violation["path"] == "docs/notes/note.md"
    assert violation["signal"] == "h1"
    assert "'# Recon notes'" in violation["reason"]


def test_catalog_yaml_is_scanned_even_though_it_is_not_markdown(tmp_path: Path) -> None:
    """The knowledge-plane catalog is watched by path, not by extension."""
    _write(tmp_path / "docs" / "catalog.yaml", "docs: []\n")
    report = scan_repo(tmp_path)
    assert report.scanned == ("docs/catalog.yaml",)
    assert [e.signal.kind for e in report.violations] == ["path"]


def test_real_repo_tree_has_no_violations(capsys: pytest.CaptureFixture[str]) -> None:
    """Green on the merged tree: no knowledge-plane artifact is tracked."""
    assert main(["--repo-root", str(default_repo_root())]) == 0
    assert "doc-home: 0 violation(s)" in capsys.readouterr().out
