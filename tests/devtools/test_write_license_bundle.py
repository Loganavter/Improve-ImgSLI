"""Windows license bundle post-step copies root LICENSE files."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build" / "Windows-template" / "write_license_bundle.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("write_license_bundle", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_license_bundle_copies_root_license_files(tmp_path, monkeypatch):
    module = _load_module()
    dist = tmp_path / "dist" / "Improve_ImgSLI"
    dist.mkdir(parents=True)
    # Pretend PyInstaller already left Qt binaries somewhere under the tree.
    (dist / "PySide6").mkdir()
    (dist / "PySide6" / "Qt6Core.dll").write_bytes(b"dll")

    monkeypatch.setattr(module, "_dist_dir", lambda repo_root: dist)
    monkeypatch.setattr(module, "_pyside6_root", lambda: dist / "PySide6")

    info = module.write_license_bundle(REPO)
    assert info.is_file()
    assert (dist / "LICENSE").is_file()
    assert (dist / "THIRD_PARTY_LICENSES.md").is_file()
    assert (dist / "licenses" / "WINDOWS_QT_NOTICE.txt").is_file()
    assert (dist / "licenses" / "LGPL-3.0.txt").is_file()
    assert "PySide6 version:" in info.read_text(encoding="utf-8")
