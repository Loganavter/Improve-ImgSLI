"""Windows packaging must ship QRhi *.qsb next to tab Python packages."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_validator():
    path = Path(__file__).resolve().parents[2] / "build" / "ci" / "validate_windows_shaders.py"
    spec = importlib.util.spec_from_file_location("validate_windows_shaders", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repo_has_base_canvas_qsb() -> None:
    repo = Path(__file__).resolve().parents[2]
    mod = _load_validator()
    rels = {str(p).replace("\\", "/") for p in mod.expected_qsb_relpaths(repo)}
    assert "tabs/image_compare/canvas/shaders/base.vert.qsb" in rels
    assert "tabs/image_compare/canvas/shaders/base.frag.qsb" in rels


def test_missing_shaders_detects_absent_bundle(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[2]
    empty_bundle = tmp_path / "Improve_ImgSLI"
    empty_bundle.mkdir()
    mod = _load_validator()
    missing = mod.missing_shaders(repo_root=repo, bundle_root=empty_bundle)
    assert "tabs/image_compare/canvas/shaders/base.vert.qsb" in missing
