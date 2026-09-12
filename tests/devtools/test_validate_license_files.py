"""Unit checks for Windows license bundle validation helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build" / "ci" / "validate_license_files.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_license_files", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _minimal_bundle(root: Path, *, pyside_rel: str) -> None:
    (root / "LICENSE").write_text("GNU GENERAL PUBLIC LICENSE\n", encoding="utf-8")
    (root / "THIRD_PARTY_LICENSES.md").write_text("third\n", encoding="utf-8")
    licenses = root / "licenses"
    licenses.mkdir(parents=True)
    (licenses / "WINDOWS_QT_NOTICE.txt").write_text("notice\n", encoding="utf-8")
    (licenses / "LGPL-3.0.txt").write_text("lgpl\n", encoding="utf-8")
    (licenses / "Qt_BUNDLE_INFO.txt").write_text(
        "PySide6 version: 6.0\n", encoding="utf-8"
    )
    pyside = root.joinpath(*pyside_rel.split("/"))
    pyside.mkdir(parents=True)
    (pyside / "Qt6Core.dll").write_bytes(b"dll")


def test_validate_windows_bundle_accepts_internal_pyside(tmp_path):
    mod = _load_module()
    bundle = tmp_path / "Improve_ImgSLI"
    bundle.mkdir()
    _minimal_bundle(bundle, pyside_rel="_internal/PySide6")
    assert mod.validate_windows_bundle(bundle) == 0


def test_validate_windows_bundle_accepts_root_pyside(tmp_path):
    mod = _load_module()
    bundle = tmp_path / "Improve_ImgSLI"
    bundle.mkdir()
    _minimal_bundle(bundle, pyside_rel="PySide6")
    assert mod.validate_windows_bundle(bundle) == 0


def test_validate_windows_bundle_rejects_missing_qt(tmp_path):
    mod = _load_module()
    bundle = tmp_path / "Improve_ImgSLI"
    bundle.mkdir()
    _minimal_bundle(bundle, pyside_rel="PySide6")
    for path in (bundle / "PySide6").rglob("*"):
        if path.is_file():
            path.unlink()
    assert mod.validate_windows_bundle(bundle) == 1
