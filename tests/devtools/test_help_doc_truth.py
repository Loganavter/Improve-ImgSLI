"""Falsifiable guard: canon/skill docs must not name retired help mechanics."""

from __future__ import annotations

from pathlib import Path

from devtools.check_help_doc_truth import main, scan_file


def test_retired_token_is_flagged(tmp_path: Path) -> None:
    """A line naming a removed mechanism is a hit (falsifies a no-op scan)."""
    doc = tmp_path / "x.md"
    doc.write_text(
        "Body uses `{{tr:foo}}`.\n"
        "See src/resources/help/tree.json for the tree.\n",
        encoding="utf-8",
    )
    hits = scan_file(doc)
    assert [tok for _, tok, _ in hits] == ["{{tr:", "tree.json"]


def test_allow_marker_suppresses(tmp_path: Path) -> None:
    doc = tmp_path / "x.md"
    doc.write_text(
        "Do not use `{{tr:}}` any more. <!-- doc-truth:allow -->\n",
        encoding="utf-8",
    )
    assert scan_file(doc) == []


def test_canon_docs_are_truthful() -> None:
    """The shipped canon + skills pass the guard (green on the merged tree)."""
    assert main([]) == 0
