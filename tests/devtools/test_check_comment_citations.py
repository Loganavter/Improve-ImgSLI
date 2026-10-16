"""Falsifiable fixtures for the comment-citation checker.

The checker under test is ``scripts/check_comment_citations.py``. Each test
builds a small tree under ``tmp_path``, runs the real CLI entry point
(``main([...])``) and asserts findings/exit codes — so a regression that makes
the scanner a silent no-op (returning 0 with no findings) fails these tests.

The MUST-pass/MUST-fail pairs are deliberately paired: the same citation shape
appears in a resolvable and an unresolvable form, so a scanner that always
reports (or never reports) cannot be green.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_comment_citations.py"


def _load_checker():
    """Load the checker from its path (the documented importlib incantation).

    Registering the module in ``sys.modules`` before ``exec_module`` is part of
    the documented recipe: ``dataclasses`` resolves string annotations through
    ``sys.modules[cls.__module__]``, so skipping this makes any dataclass in the
    module blow up on import under ``from __future__ import annotations``.
    """
    name = "check_comment_citations_under_test"
    spec = importlib.util.spec_from_file_location(name, _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def checker():
    return _load_checker()


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _findings(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_module_import_has_no_side_effects(checker) -> None:
    assert callable(checker.main)
    assert checker.KIND_UNRESOLVED_PATH == "unresolved-path"
    assert checker.KIND_LINE_OUT_OF_RANGE == "line-out-of-range"
    assert checker.KIND_UNKNOWN_SYMBOL == "unknown-symbol"
    assert checker.KIND_UNVERIFIABLE_ID == "unverifiable-id"


def test_valid_path_and_stdlib_symbol_pass(checker, tmp_path, capsys) -> None:
    """MUST-pass: an existing file at a valid line + a builtin backtick."""
    root = tmp_path / "tree"
    _write(
        root / "helpers.py",
        '"""Helper module."""\n\n\ndef helper() -> int:\n    return 1\n',
    )
    _write(
        root / "citing.py",
        '"""See helpers.py:2 for the helper seam. `print` is always available."""\n',
    )

    assert checker.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == ""


def test_nonexistent_path_is_flagged(checker, tmp_path, capsys) -> None:
    """MUST-fail: a cited file that does not exist anywhere."""
    root = tmp_path / "tree"
    _write(root / "citing.py", "# Load order documented in nope.py:12.\n")
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["unresolved-path"]
    assert rows[0]["line"] == 1
    assert rows[0]["file"] == str(root / "citing.py")
    assert "nope.py:12" in rows[0]["snippet"]
    assert "unresolved-path" in capsys.readouterr().out


def test_out_of_range_line_is_flagged(checker, tmp_path, capsys) -> None:
    """MUST-fail: the file exists but the cited line is past end-of-file."""
    root = tmp_path / "tree"
    _write(root / "helpers.py", '"""One."""\n\n\ndef helper() -> int:\n    return 1\n')
    _write(root / "citing.py", "# The seam moved to helpers.py:999 last week.\n")
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["line-out-of-range"]
    assert rows[0]["file"] == str(root / "citing.py")
    assert "line-out-of-range" in capsys.readouterr().out


def test_unknown_symbol_is_flagged(checker, tmp_path, capsys) -> None:
    """MUST-fail: a backticked symbol defined nowhere in the tree."""
    root = tmp_path / "tree"
    _write(
        root / "citing.py",
        '"""Dispatches through `definitely_not_a_symbol_xyz` on retry."""\n',
    )
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["unknown-symbol"]
    assert rows[0]["line"] == 1


def test_symbol_defined_in_tree_passes(checker, tmp_path) -> None:
    """MUST-pass: the symbol is defined in another file under the root."""
    root = tmp_path / "tree"
    _write(
        root / "owner.py",
        '"""Owner."""\n\n\nclass WidgetSync:\n    """Sync seam."""\n',
    )
    _write(root / "citing.py", "# The `WidgetSync` seam owns the merge.\n")

    assert checker.main(["--root", str(root)]) == 0


def test_allow_file_extends_allowlist(checker, tmp_path) -> None:
    """A name absent by default is accepted once listed in --allow."""
    root = tmp_path / "tree"
    _write(root / "citing.py", "# Provided by `SomeVendorType` from a wheel.\n")
    assert checker.main(["--root", str(root)]) == 1

    allow = tmp_path / "allow.txt"
    _write(allow, "# vendor names\nSomeVendorType\n")
    assert checker.main(["--root", str(root), "--allow", str(allow)]) == 0


def test_code_body_is_not_scanned(checker, tmp_path) -> None:
    """Only comments/docstrings count; a literal in code is not a citation."""
    root = tmp_path / "tree"
    _write(root / "citing.py", 'PATH = "nope.py:12"\n')

    assert checker.main(["--root", str(root)]) == 0


def test_baseline_suppresses_known_finding(checker, tmp_path, capsys) -> None:
    """MUST-pass with baseline: the ratchet suppresses an accepted finding."""
    root = tmp_path / "tree"
    _write(root / "citing.py", "# Load order documented in nope.py:12.\n")
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    key = f"{rows[0]['file']}:{rows[0]['line']}:{rows[0]['kind']}"
    capsys.readouterr()

    baseline = tmp_path / "baseline.txt"
    _write(baseline, f"# accepted for now\n{key}\n")
    assert checker.main(["--root", str(root), "--baseline", str(baseline)]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_ids_resolver_off_by_default(checker, tmp_path) -> None:
    """plan-/inv- ids are not resolved (and not reported) without --ids-file."""
    root = tmp_path / "tree"
    _write(root / "citing.py", '"""Implements plan-gallery-redux-2026-09-24."""\n')

    report = tmp_path / "report.json"
    assert checker.main(["--root", str(root), "--json", str(report)]) == 0
    assert _findings(report) == []


def test_ids_file_flags_unknown_id(checker, tmp_path) -> None:
    """With --ids-file, a known id passes and an unknown id is a finding."""
    root = tmp_path / "tree"
    _write(
        root / "citing.py",
        '"""Part of plan-known-id-2026-01-01 and inv-missing-id-2026-01-02."""\n',
    )
    ids = tmp_path / "ids.txt"
    _write(ids, "plan-known-id-2026-01-01\n")
    report = tmp_path / "report.json"

    assert checker.main(
        ["--root", str(root), "--ids-file", str(ids), "--json", str(report)]
    ) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["unverifiable-id"]
    assert "inv-missing-id-2026-01-02" in rows[0]["snippet"]


def test_report_is_sorted_and_deterministic(checker, tmp_path) -> None:
    root = tmp_path / "tree"
    _write(root / "b.py", "# `nope_symbol_bbb` here.\n# also nope_b.py:3\n")
    _write(root / "a.py", "# `nope_symbol_aaa` here.\n")
    first = tmp_path / "one.json"
    second = tmp_path / "two.json"

    assert checker.main(["--root", str(root), "--json", str(first)]) == 1
    assert checker.main(["--root", str(root), "--json", str(second)]) == 1
    rows = _findings(first)
    assert rows == _findings(second)
    assert rows == sorted(rows, key=lambda r: (r["file"], r["line"], r["kind"], r["snippet"]))
    assert [row["file"] for row in rows] == [str(root / "a.py"), str(root / "b.py"), str(root / "b.py")]
