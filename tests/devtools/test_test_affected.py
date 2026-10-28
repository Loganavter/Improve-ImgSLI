"""Tests for `tools/test_affected.py` (the affected-tests selector).

The tool is a planning aid that gates what a developer runs, so its two failure
modes matter more than its happy path: a *false negative* (a test that should
have run did not) and a *false "everything"* (which only costs time). These
tests pin both, on a synthetic tree, so they never touch the real suite.

Contract under test (`tools/test_affected.py` docstring):
- stdout: one repo-relative test path per line, sorted;
- exit 0 = the printed list is the affected set; exit 2 = full tier (fail-closed);
- `--explain` adds the import chain that pulled each test in.

Falsification story: the module and these assertions did not exist before; the
synthetic tree is built from scratch, so a green run proves the graph is built
from imports rather than from file names, and that the shared-module rule fires
before any graph work.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "test_affected.py"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Synthetic tree: leaf <- service <- test_service (a 2-hop import chain)."""
    _write(tmp_path / "src" / "core" / "store.py", "VALUE = 1\n")
    _write(tmp_path / "src" / "app" / "leaf.py", "X = 1\n")
    _write(tmp_path / "src" / "app" / "service.py", "from app.leaf import X\n\nY = X + 1\n")
    _write(tmp_path / "src" / "other" / "thing.py", "Z = 3\n")
    _write(tmp_path / "tests" / "test_leaf.py", "from app.leaf import X\n")
    _write(tmp_path / "tests" / "test_service.py", "from app.service import Y\n")
    _write(tmp_path / "tests" / "test_nothing.py", "def test_nothing():\n    assert True\n")
    return tmp_path


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_TOOL), "--root", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_leaf_change_pulls_direct_and_transitive_importers(repo: Path):
    proc = _run(repo, "src/app/leaf.py")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["tests/test_leaf.py", "tests/test_service.py"]
    # The test that imports nothing from the changed tree stays out.
    assert "test_nothing" not in proc.stdout


def test_depth_one_stops_before_the_transitive_importer(repo: Path):
    proc = _run(repo, "--depth", "1", "src/app/leaf.py")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["tests/test_leaf.py"]


def test_mid_module_pulls_only_its_own_test(repo: Path):
    proc = _run(repo, "src/app/service.py")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["tests/test_service.py"]


def test_shared_module_fails_closed_to_full_tier(repo: Path):
    proc = _run(repo, "src/core/store.py")

    assert proc.returncode == 2, proc.stdout + proc.stderr
    first_line = proc.stdout.splitlines()[0]
    assert first_line.startswith("full-tier:")
    assert "src/core/store.py" in proc.stdout


def test_root_pytest_ini_fails_closed_to_full_tier(repo: Path):
    _write(repo / "pytest.ini", "[pytest]\n")

    proc = _run(repo, "pytest.ini")

    assert proc.returncode == 2
    assert proc.stdout.splitlines()[0].startswith("full-tier:")


def test_nonexistent_file_is_skipped_with_an_explicit_message(repo: Path):
    proc = _run(repo, "src/app/ghost.py")

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert "src/app/ghost.py" in proc.stderr
    assert "does not exist" in proc.stderr


def test_unimported_module_prints_a_note_instead_of_guessing(repo: Path):
    proc = _run(repo, "src/other/thing.py")

    assert proc.returncode == 0
    assert proc.stdout.strip() == ""
    assert "no test imports src/other/thing.py" in proc.stderr


def test_changed_test_file_selects_itself(repo: Path):
    proc = _run(repo, "tests/test_service.py")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["tests/test_service.py"]


def test_explain_prints_the_import_chain(repo: Path):
    proc = _run(repo, "--explain", "src/app/leaf.py")

    assert proc.returncode == 0, proc.stderr
    assert "tests/test_service.py" in proc.stdout
    assert "why: src/app/leaf.py -> src/app/service.py -> tests/test_service.py" in proc.stdout
    # The changed module must not be repeated as its own importer.
    assert "src/app/leaf.py -> src/app/leaf.py" not in proc.stdout


def test_docs_change_maps_to_the_docs_link_graph_test(repo: Path):
    _write(repo / "docs" / "dev" / "a.md", "# A\n")
    _write(repo / "tests" / "devtools" / "test_docs_link_graph.py", "def test_x():\n    pass\n")

    proc = _run(repo, "docs/dev/a.md")

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines() == ["tests/devtools/test_docs_link_graph.py"]
