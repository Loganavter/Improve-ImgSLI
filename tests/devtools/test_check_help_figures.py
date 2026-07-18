"""Unit tests for ``devtools.check_help_figures``."""

from __future__ import annotations

import json
from pathlib import Path

from devtools.check_help_figures import analyze_help_figures, main


def _write_png(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _make_repo(tmp_path: Path) -> Path:
    """Minimal host + one tab Help package layout."""
    repo = tmp_path / "repo"
    host = repo / "src" / "resources" / "help"
    tab = repo / "src" / "tabs" / "demo" / "resources" / "help"
    stub = b"STUB-BYTES"
    real = b"REAL-SCREENSHOT-BYTES"

    _write_png(host / "assets" / "_stub.jpg", stub)
    _write_png(host / "assets" / "ui" / "lists.jpg", stub)
    (host / "figures.json").write_text(
        json.dumps({"ui.lists": "ui/lists.jpg"}),
        encoding="utf-8",
    )
    body = host / "en" / "lists.md"
    body.parent.mkdir(parents=True)
    body.write_text("![x]({{img:ui.lists}})\n", encoding="utf-8")

    _write_png(tab / "assets" / "grid.jpg", real)
    _write_png(tab / "assets" / "orphan.jpg", b"ORPHAN")
    (tab / "figures.json").write_text(
        json.dumps(
            {
                "workspace.demo.grid": "grid.jpg",
                "workspace.demo.missing": "gone.jpg",
            }
        ),
        encoding="utf-8",
    )
    tab_body = tab / "en" / "overview.md"
    tab_body.parent.mkdir(parents=True)
    tab_body.write_text(
        "![g]({{img:workspace.demo.grid}})\n![u]({{img:workspace.demo.unknown}})\n",
        encoding="utf-8",
    )
    return repo


def test_analyze_help_figures_across_host_and_tab_packages(tmp_path: Path):
    repo = _make_repo(tmp_path)
    report = analyze_help_figures(repo_root=repo)
    by_slot = {row.slot: row for row in report.rows}

    assert by_slot["ui.lists"].status == "stub"
    assert by_slot["ui.lists"].package.endswith("src/resources/help")
    assert by_slot["workspace.demo.grid"].status == "ready"
    assert "tabs/demo/resources/help" in by_slot["workspace.demo.grid"].package
    assert by_slot["workspace.demo.missing"].status == "missing"

    assert report.orphans == (("src/tabs/demo/resources/help", "orphan.jpg"),)
    assert (
        "src/tabs/demo/resources/help/en/overview.md",
        "workspace.demo.unknown",
    ) in report.unknown_tokens
    assert report.gap_count >= 3  # stub + missing + unknown


def test_main_strict_exits_nonzero_when_stubs_present(tmp_path: Path, capsys):
    repo = _make_repo(tmp_path)
    code = main(["--repo-root", str(repo), "--strict"])
    assert code == 1
    out = capsys.readouterr().out
    assert "Need screenshots" in out
    assert "ui.lists" in out
