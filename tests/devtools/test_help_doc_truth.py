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


def test_retired_widget_names_are_flagged(tmp_path: Path) -> None:
    """The retired help/glass-panel widget families are live lies, not history."""
    doc = tmp_path / "x.md"
    doc.write_text(
        "Body in `HelpDocumentView` / `HelpDocumentBodyCanvas`.\n"
        "Panels: GlassPanelDisplayWidgetCpu and GlassPanelDisplayWidgetRhi.\n",
        encoding="utf-8",
    )
    assert [token for _, token, _ in scan_file(doc)] == [
        "HelpDocumentView",
        "HelpDocumentBodyCanvas",
        "GlassPanelDisplayWidgetCpu",
        "GlassPanelDisplayWidgetRhi",
    ]


def test_live_glass_panel_widget_is_not_flagged(tmp_path: Path) -> None:
    """The surviving single widget must stay clean (a token match, not a prefix)."""
    doc = tmp_path / "x.md"
    doc.write_text("`GlassPanelDisplayWidget` is the live surface.\n", encoding="utf-8")
    assert scan_file(doc) == []


def test_canon_docs_are_truthful() -> None:
    """The shipped canon + skills pass the guard (green on the merged tree)."""
    assert main([]) == 0
