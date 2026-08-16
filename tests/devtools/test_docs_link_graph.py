"""Unit tests for ``devtools.docs_link_graph`` + real-repo freshness checks."""

from __future__ import annotations

from pathlib import Path

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