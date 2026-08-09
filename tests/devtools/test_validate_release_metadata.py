"""Unit checks for the sli-ui-toolkit AUR version-floor guard.

Regression this guards against: AUR users hit ``ModuleNotFoundError`` /
``ImportError: cannot import name '...'`` on startup because PKGBUILD's
``python-sli-ui-toolkit`` dependency had no minimum version, so pacman could
install a toolkit release older than what the packaged app release actually
imports. Flatpak's ``python3-modules.json`` pin is the version this project
has actually verified a release against, so it's the source of truth the AUR
floor is checked against.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "build" / "ci" / "validate_release_metadata.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("validate_release_metadata", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_repo_pkgbuild_floor_matches_flatpak_pin():
    mod = _load_module()
    assert mod._check_sli_ui_toolkit_version_floor() is None


def test_flags_unbounded_pkgbuild_dependency(monkeypatch, tmp_path):
    mod = _load_module()
    fake_pkgbuild = tmp_path / "PKGBUILD"
    fake_pkgbuild.write_text(
        "depends=(\n  'python-sli-ui-toolkit'\n)\n", encoding="utf-8"
    )
    monkeypatch.setattr(mod, "PKGBUILD_PATH", fake_pkgbuild)

    error = mod._check_sli_ui_toolkit_version_floor()
    assert error is not None
    assert "must pin a minimum" in error


def test_flags_pkgbuild_floor_older_than_flatpak_pin(monkeypatch, tmp_path):
    mod = _load_module()
    flatpak_text = mod.FLATPAK_MODULES_PATH.read_text(encoding="utf-8")
    pinned = re.search(r"sli_ui_toolkit-([0-9.]+)\.tar\.gz", flatpak_text).group(1)

    fake_pkgbuild = tmp_path / "PKGBUILD"
    fake_pkgbuild.write_text(
        "depends=(\n  'python-sli-ui-toolkit>=0.0.1'\n)\n", encoding="utf-8"
    )
    monkeypatch.setattr(mod, "PKGBUILD_PATH", fake_pkgbuild)

    error = mod._check_sli_ui_toolkit_version_floor()
    assert error is not None
    assert "0.0.1" in error and pinned in error


def test_accepts_pkgbuild_floor_newer_than_flatpak_pin(monkeypatch, tmp_path):
    mod = _load_module()
    fake_pkgbuild = tmp_path / "PKGBUILD"
    fake_pkgbuild.write_text(
        "depends=(\n  'python-sli-ui-toolkit>=999.0.0'\n)\n", encoding="utf-8"
    )
    monkeypatch.setattr(mod, "PKGBUILD_PATH", fake_pkgbuild)

    assert mod._check_sli_ui_toolkit_version_floor() is None
