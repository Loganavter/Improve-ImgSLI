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
    assert checker.KIND_MISSING_DOC_PATH == "missing-doc-path"
    assert checker.KIND_MISSING_DOC_PATH in checker.FAILING_KINDS


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


# --- v2: shape filter ------------------------------------------------------


def test_shape_filter_skips_non_symbol_shapes(checker, tmp_path, capsys) -> None:
    """MUST-pass: env var, 3-segment token, path, asset file, external symbol."""
    root = tmp_path / "tree"
    _write(
        root / "citing.py",
        '"""Shape cases: `UI_NAV_DEBUG_XYZ` (env), `acme.card.border` (theme),\n'
        "`docs/some_dir` (dir), `notes.json` (asset), "
        '`sli_ui_toolkit.xyz` (external).\n"""\n',
    )

    assert checker.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == ""


def test_shape_filter_keeps_real_unknown_symbol(checker, tmp_path, capsys) -> None:
    """The filter skips shapes, never the whole line — a real symbol still flags."""
    root = tmp_path / "tree"
    _write(
        root / "citing.py",
        "# `UI_NAV_DEBUG_XYZ` is fine, but `totally_undefined_s05_symbol` is not.\n",
    )
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["unknown-symbol"]
    assert "totally_undefined_s05_symbol" in rows[0]["snippet"]


def test_shape_filter_whitespace_is_impossible(checker) -> None:
    """Phrases cannot reach the filter (regex guard), asserted in code."""
    assert checker.SYMBOL_RE.search("`two words`") is None
    with pytest.raises(AssertionError):
        checker.is_symbol_shaped("two words")


# --- v2: basename resolution ----------------------------------------------


def test_unique_basename_resolves(checker, tmp_path, capsys) -> None:
    """MUST-pass: basename-only cite to a file deeper in the tree resolves."""
    root = tmp_path / "tree"
    _write(
        root / "pkg" / "deep" / "unique_basename_mod_s05.py",
        '"""Deep module."""\n\n\ndef seam() -> int:\n    return 1\n',
    )
    _write(
        root / "citing" / "citing.py",
        "# The seam lives in unique_basename_mod_s05.py:2.\n",
    )

    assert checker.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out == ""


def test_unique_basename_out_of_range_is_flagged(checker, tmp_path) -> None:
    """The resolved basename honours the line bound (proves resolution happened)."""
    root = tmp_path / "tree"
    _write(
        root / "pkg" / "deep" / "unique_basename_mod_s05.py",
        '"""Deep module."""\n\n\ndef seam() -> int:\n    return 1\n',
    )
    _write(
        root / "citing" / "citing.py",
        "# The seam lives in unique_basename_mod_s05.py:999.\n",
    )
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["line-out-of-range"]


def test_ambiguous_basename_is_flagged(checker, tmp_path, capsys) -> None:
    """MUST-fail: two same-named files -> unresolved-path, collision named."""
    root = tmp_path / "tree"
    _write(root / "a" / "dup_mod_s05.py", '"""A."""\n')
    _write(root / "b" / "dup_mod_s05.py", '"""B."""\n')
    _write(root / "citing" / "citing.py", "# See dup_mod_s05.py:1 for details.\n")
    report = tmp_path / "report.json"

    assert checker.main(["--root", str(root), "--json", str(report)]) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["unresolved-path"]
    assert "ambiguous basename" in rows[0]["snippet"]
    assert "2 matches" in rows[0]["snippet"]
    assert "unresolved-path" in capsys.readouterr().out


# --- v2: --extra-root ------------------------------------------------------


def test_extra_root_resolves_symbols_without_scanning_comments(
    checker, tmp_path
) -> None:
    """--extra-root indexes names only; its comments are never scanned."""
    root = tmp_path / "tree"
    _write(root / "citing.py", "# Provided by `ToolkitSymbolS05` from the toolkit.\n")
    ext = tmp_path / "ext"
    _write(
        ext / "toolkit_mod.py",
        '"""Toolkit stub."""\n\n\nclass ToolkitSymbolS05:\n'
        '    """Real definition."""\n',
    )
    _write(ext / "dirty.py", "# stale cite to nope_s05.py:3 lives here.\n")

    # Without the extra root the symbol is (correctly) unknown.
    assert checker.main(["--root", str(root)]) == 1

    report = tmp_path / "report.json"
    assert (
        checker.main(
            ["--root", str(root), "--extra-root", str(ext), "--json", str(report)]
        )
        == 0
    )
    # The extra root supplied names, but none of its comments were scanned.
    assert _findings(report) == []


# --- v3: cited doc paths ----------------------------------------------------


def _doc_repo(tmp_path: Path) -> Path:
    """A tiny checkout with one live doc to cite."""
    repo = tmp_path / "checkout"
    _write(repo / "docs" / "dev" / "live.md", "# Live\n\nA real doc.\n")
    return repo


def test_missing_doc_path_is_flagged(checker, tmp_path, capsys) -> None:
    """MUST-fail: a comment citing a doc that never existed."""
    repo = _doc_repo(tmp_path)
    root = tmp_path / "tree"
    _write(
        root / "citing.py",
        "# The seam is frozen by `docs/dev/never_existed_s05.md` (ADR-008).\n",
    )
    report = tmp_path / "report.json"

    assert checker.main(
        ["--root", str(root), "--repo-root", str(repo), "--json", str(report)]
    ) == 1
    rows = _findings(report)
    assert [row["kind"] for row in rows] == ["missing-doc-path"]
    assert rows[0]["token"] == "docs/dev/never_existed_s05.md"
    assert "missing-doc-path" in capsys.readouterr().out


def test_existing_doc_path_passes(checker, tmp_path, capsys) -> None:
    """MUST-pass: the same citation shape resolves against a live doc."""
    repo = _doc_repo(tmp_path)
    root = tmp_path / "tree"
    _write(root / "citing.py", "# The seam is frozen by `docs/dev/live.md` (ADR-008).\n")

    assert checker.main(["--root", str(root), "--repo-root", str(repo)]) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "citation",
    [
        "docs/dev/…",
        "docs/dev/...",
        "docs/{a,b}/x.md",
        "tests/<tab>/test_x.md",
        "tests/**/*.py",
        "docs/dev/x.md:12",
        "./docs/dev/x.md",
        "../improve-imgsli-internal-docs/docs/dev/x.md",
        "README.md",
        "live.md",
    ],
)
def test_illustrative_doc_citations_pass(checker, tmp_path, capsys, citation: str) -> None:
    """Illustrative / ambiguous / sibling shapes are not citations of this repo."""
    repo = _doc_repo(tmp_path)
    root = tmp_path / "tree"
    _write(root / "citing.py", f"# Shape: `{citation}`\n")

    assert checker.main(["--root", str(root), "--repo-root", str(repo)]) == 0
    assert capsys.readouterr().out == ""


def test_doc_path_baseline_ratchet(checker, tmp_path, capsys) -> None:
    """Grow -> fail; a baselined count passes; shrinking is a pass."""
    repo = _doc_repo(tmp_path)
    root = tmp_path / "tree"
    citing = root / "citing.py"
    baseline = tmp_path / "doc_paths_baseline.txt"
    _write(citing, "# Old home: `docs/dev/gone_s05.md`.\n")

    assert (
        checker.main(
            [
                "--root",
                str(root),
                "--repo-root",
                str(repo),
                "--doc-path-baseline",
                str(baseline),
                "--update-doc-path-baseline",
            ]
        )
        == 0
    )
    assert baseline.read_text(encoding="utf-8").count("gone_s05") == 0
    assert "citing.py\t1" in baseline.read_text(encoding="utf-8")

    def run() -> int:
        return checker.main(
            [
                "--root",
                str(root),
                "--repo-root",
                str(repo),
                "--doc-path-baseline",
                str(baseline),
            ]
        )

    assert run() == 0
    capsys.readouterr()

    _write(citing, "# Old home: `docs/dev/gone_s05.md`, new: `docs/dev/gone2_s05.md`.\n")
    assert run() == 1
    assert "gone2_s05" in capsys.readouterr().out

    _write(citing, "# Old home: `docs/dev/gone_s05.md`.\n")
    assert run() == 0


def test_real_repo_doc_path_baseline_holds(checker) -> None:
    """The committed baseline accepts pre-existing drift and nothing newer."""
    baseline_file = checker.DOC_PATH_BASELINE
    assert baseline_file.is_file(), (
        "missing-doc-path needs its committed ratchet — regenerate with "
        "`python3 scripts/check_comment_citations.py --root src --root tests "
        "--update-doc-path-baseline`"
    )
    baseline = checker.load_doc_path_baseline(baseline_file)
    assert baseline, "an empty baseline cannot be a ratchet"

    findings = checker.collect_findings([checker.DEFAULT_ROOT])
    _, regressions = checker.split_doc_path_baseline(findings, baseline)
    assert not regressions, "\n".join(
        f"{f.file}:{f.line} `{f.token}`" for f in regressions
    )
