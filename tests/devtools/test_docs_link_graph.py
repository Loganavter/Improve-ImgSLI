"""Unit tests for ``devtools.docs_link_graph`` + real-repo freshness checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from devtools.docs_cited_paths import (
    MissingRepoPath,
    load_path_baseline,
    normalize_cited_repo_path,
    path_regressions,
    render_baseline,
)
from devtools.docs_link_graph import analyze_docs, default_repo_root, render_index


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "docs" / "dev" / "a.md", "# A\n\nSee [B](b.md) and [gone](missing.md).\n")
    _write(repo / "docs" / "dev" / "b.md", "# B\n\nBack to [A](a.md).\n")
    _write(
        repo / "src" / "tabs" / "demo" / "docs" / "c.md",
        "# C\n\nRefers to [A](../../../../docs/dev/a.md).\n",
    )
    # Fenced code block showing markdown syntax must not be treated as a real link.
    _write(
        repo / "docs" / "dev" / "d.md",
        "# D\n\n```markdown\n![x]({{img:some.slot}})\n```\n",
    )
    return repo


def test_analyze_docs_finds_broken_links_and_backlinks(tmp_path: Path):
    repo = _make_repo(tmp_path)
    report = analyze_docs(repo_root=repo)

    assert "docs/dev/a.md" in report.docs
    assert "src/tabs/demo/docs/c.md" in report.docs

    broken_targets = {b.target for b in report.broken}
    assert "missing.md" in broken_targets

    assert report.backlinks["docs/dev/a.md"] == (
        "docs/dev/b.md",
        "src/tabs/demo/docs/c.md",
    )
    assert report.backlinks["docs/dev/b.md"] == ("docs/dev/a.md",)


def test_analyze_docs_ignores_links_inside_fenced_code_blocks(tmp_path: Path):
    repo = _make_repo(tmp_path)
    report = analyze_docs(repo_root=repo)

    assert not any(b.source == "docs/dev/d.md" for b in report.broken)


def test_render_index_lists_every_doc_with_backlinks(tmp_path: Path):
    repo = _make_repo(tmp_path)
    report = analyze_docs(repo_root=repo)
    index = render_index(report, repo_root=repo)

    assert "AUTO-GENERATED" in index
    assert "docs/dev/a.md" in index
    assert "src/tabs/demo/docs/c.md" in index
    assert "Referenced by" in index


def test_real_repo_has_no_broken_doc_links():
    report = analyze_docs()
    assert not report.broken, "\n".join(
        f"{b.source}:{b.line} [{b.text}]({b.target})" for b in report.broken
    )


def test_real_repo_doc_index_is_up_to_date():
    root = default_repo_root()
    report = analyze_docs(repo_root=root)
    expected = render_index(report, repo_root=root)
    actual = (root / "docs" / "dev" / "DOC_INDEX.md").read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/dev/DOC_INDEX.md is stale — regenerate with "
        "`python src/devtools/docs_link_graph.py --write-index`"
    )


# --- agent-plane surfaces (AGENTS.md / skills / .cursor / .github) ----------


def _agent_repo(tmp_path: Path) -> Path:
    repo = _make_repo(tmp_path)
    _write(
        repo / "AGENTS.md",
        "# Agents\n\nRead [a](docs/dev/a.md) and [gone](docs/dev/nope.md).\n",
    )
    _write(
        repo / "skills" / "demo" / "SKILL.md",
        "# Skill\n\nEmpirical notes: [gotchas](../../../improve-imgsli-internal-docs/docs/dev/x.md).\n",
    )
    _write(repo / ".github" / "copilot-instructions.md", "# Copilot\n\nSee [b](docs/dev/b.md).\n")
    return repo


def test_agent_plane_surfaces_are_link_checked(tmp_path: Path):
    """Before the corpus was extended, a dead link in AGENTS.md was invisible."""
    report = analyze_docs(repo_root=_agent_repo(tmp_path))

    assert "AGENTS.md" in report.link_sources
    assert "skills/demo/SKILL.md" in report.link_sources
    assert ".github/copilot-instructions.md" in report.link_sources
    broken = {(b.source, b.target) for b in report.broken}
    assert ("AGENTS.md", "docs/dev/nope.md") in broken


def test_agent_plane_links_do_not_change_index_or_backlinks(tmp_path: Path):
    """The generated index stays a docs-only graph (byte-stable on agent edits)."""
    repo = _agent_repo(tmp_path)
    report = analyze_docs(repo_root=repo)

    assert "AGENTS.md" not in report.docs
    assert report.backlinks["docs/dev/a.md"] == (
        "docs/dev/b.md",
        "src/tabs/demo/docs/c.md",
    )
    index = render_index(report, repo_root=repo)
    assert "AGENTS.md" not in index
    assert "skills/demo/SKILL.md" not in index


def test_sibling_checkout_links_are_not_validated(tmp_path: Path):
    """A link into a sibling repo cannot be judged in a clean clone."""
    report = analyze_docs(repo_root=_agent_repo(tmp_path))

    assert not any(b.source == "skills/demo/SKILL.md" for b in report.broken)


# --- cited repo-root backticked paths --------------------------------------


def test_cited_repo_path_that_does_not_exist_is_found(tmp_path: Path):
    """MUST-fail: a doc citing a path that is not in this checkout."""
    repo = _make_repo(tmp_path)
    _write(repo / "src" / "demo" / "real_module.py", "x = 1\n")
    _write(
        repo / "docs" / "dev" / "e.md",
        "# E\n\nOwned by `src/demo/real_module.py`; the old seam lived in"
        " `src/demo/dead_module.py`.\n",
    )

    report = analyze_docs(repo_root=repo)

    assert report.missing_paths == (
        MissingRepoPath(source="docs/dev/e.md", line=3, token="src/demo/dead_module.py"),
    )


@pytest.mark.parametrize(
    "token",
    [
        "src/{a,b}/x.py",
        "docs/dev/…",
        "docs/dev/...",
        "tests/<tab>/test_x.py",
        "src/**/*.py",
        "src/x.py:12",
        "../improve-imgsli-internal-docs/docs/dev/x.md",
        "../sli-ui-toolkit/src/sli_ui_toolkit/widgets.py",
        "./relative/x.md",
        "mcp-server/missing/tool.py:*",
    ],
)
def test_illustrative_citations_are_skipped(tmp_path: Path, token: str):
    """Illustrative fragments are not citations — they must never be findings."""
    repo = _make_repo(tmp_path)
    _write(repo / "docs" / "dev" / "f.md", f"# F\n\nPattern: {token}\n")

    report = analyze_docs(repo_root=repo)

    assert report.missing_paths == ()
    assert normalize_cited_repo_path(token) is None


def test_dated_investigation_records_are_not_checked(tmp_path: Path):
    """Plans/investigations name what was true when written — evidence, not pointers."""
    repo = _make_repo(tmp_path)
    _write(
        repo / "docs" / "investigations" / "plan-old-2026-01-01.md",
        "# Plan\n\nTouched `src/deleted/module.py` back then.\n",
    )

    report = analyze_docs(repo_root=repo)

    assert report.missing_paths == ()


def test_path_baseline_ratchet(tmp_path: Path):
    """Grow -> fail; shrink -> pass. The baseline may only turn one way."""
    repo = _make_repo(tmp_path)
    doc = repo / "docs" / "dev" / "g.md"
    _write(doc, "# G\n\nOld home: `src/old/first.py`.\n")
    findings = analyze_docs(repo_root=repo).missing_paths
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(render_baseline(findings), encoding="utf-8")
    baseline = load_path_baseline(baseline_file)

    assert path_regressions(findings, baseline) == ()

    _write(doc, "# G\n\nOld home: `src/old/first.py`, newer: `src/old/second.py`.\n")
    grown = analyze_docs(repo_root=repo).missing_paths
    assert len(grown) == 2
    assert len(path_regressions(grown, baseline)) == 2

    # Shrinking is a pass, not a finding.
    assert path_regressions(grown[:1], baseline) == ()


def test_main_strict_fails_on_path_regression(tmp_path: Path):
    """The CLI gate: a baselined dead path passes, a NEW one fails."""
    from devtools.docs_link_graph import main

    repo = tmp_path / "repo"
    doc = repo / "docs" / "dev" / "h.md"
    _write(doc, "# H\n\nOld home: `src/old/first.py`.\n")
    baseline_file = tmp_path / "baseline.txt"
    baseline_file.write_text(
        render_baseline(analyze_docs(repo_root=repo).missing_paths), encoding="utf-8"
    )

    assert main(["--repo-root", str(repo), "--path-baseline", str(baseline_file), "--strict"]) == 0

    _write(doc, "# H\n\nOld home: `src/old/first.py`, new: `src/old/second.py`.\n")
    assert main(["--repo-root", str(repo), "--path-baseline", str(baseline_file), "--strict"]) == 1


def test_real_repo_cited_path_baseline_holds():
    """The committed baseline is the ratchet for pre-existing citation drift."""
    root = default_repo_root()
    baseline_file = root / "src" / "devtools" / "docs_path_baseline.txt"
    assert baseline_file.is_file(), (
        "the cited-path ratchet needs its baseline — regenerate with "
        "`python src/devtools/docs_link_graph.py --update-path-baseline`"
    )

    report = analyze_docs(repo_root=root)
    baseline = load_path_baseline(baseline_file)
    regressions = path_regressions(report.missing_paths, baseline)
    assert not regressions, "\n".join(
        f"{m.source}:{m.line} `{m.token}`" for m in regressions
    )
    # The baseline may only ever hold literal paths: an illustrative fragment
    # reaching it would mean the shape filter leaked.
    for finding in report.missing_paths:
        assert normalize_cited_repo_path(finding.token) == finding.token
