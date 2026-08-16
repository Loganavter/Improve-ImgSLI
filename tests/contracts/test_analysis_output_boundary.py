"""AST contract: analysis results finalize only through shared/analysis/output.py.

Every analysis entry point (differ, ssim_source, edge_detector,
channel_analyzer, diff_source) must route its numpy result through
`finalize_diff_output` instead of constructing a full-frame PIL container
with `Image.fromarray` directly. One boundary owns the small-PIL / spill-to-
TiledPixelStore decision and can be extended (e.g. new channels) without
touching consumers. See the archived pyvips-streaming plan (private improve-imgsli-internal-docs repo) / the analysis-output
unification review.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.contracts._framework import ROOT, rel

ANALYSIS_DIR = ROOT / "src" / "shared" / "analysis"
BOUNDARY_MODULE = "src/shared/analysis/output.py"


def _analysis_py_files() -> list[Path]:
    return sorted(p for p in ANALYSIS_DIR.glob("*.py") if p.name != "__init__.py")


def _fromarray_calls(path: Path) -> list[int]:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "fromarray":
            continue
        value = func.value
        if isinstance(value, ast.Name) and value.id == "Image":
            hits.append(node.lineno)
    return hits


def test_image_fromarray_confined_to_output_boundary():
    offenders: list[str] = []
    for path in _analysis_py_files():
        rel_path = rel(path)
        if rel_path == BOUNDARY_MODULE:
            continue
        hits = _fromarray_calls(path)
        if hits:
            offenders.append(f"{rel_path}: {hits}")
    assert not offenders, (
        "Analysis modules must not construct PIL result containers via "
        "Image.fromarray directly — use shared.analysis.output.finalize_diff_output:\n"
        + "\n".join(offenders)
    )


def test_output_boundary_defines_finalizer():
    text = (ROOT / BOUNDARY_MODULE).read_text(encoding="utf-8")
    assert "def finalize_diff_output" in text
    assert "Image.fromarray" in text, "finalizer must own the fromarray boundary"