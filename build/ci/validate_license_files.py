"""Static checks for application and Windows LGPL license artifacts."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

LICENSE_PATH = REPO_ROOT / "LICENSE"
THIRD_PARTY_PATH = REPO_ROOT / "THIRD_PARTY_LICENSES.md"
PKGBUILD_PATH = REPO_ROOT / "build" / "AUR-template" / "PKGBUILD"
INNO_PATH = REPO_ROOT / "build" / "Windows-template" / "inno_setup_6.iss"
BUILD_WINDOWS_PATH = REPO_ROOT / "build" / "Windows-template" / "build_windows.py"
WRITE_BUNDLE_PATH = REPO_ROOT / "build" / "Windows-template" / "write_license_bundle.py"
WINDOWS_LICENSES_DIR = REPO_ROOT / "build" / "Windows-template" / "licenses"
FLATPAK_YAML_PATH = REPO_ROOT / "build" / "Flatpak-template" / "io.github.Loganavter.Improve-ImgSLI.yaml"
INSTALL_DOC_PATH = REPO_ROOT / "docs" / "INSTALL.md"
CONTRIBUTING_PATH = REPO_ROOT / "CONTRIBUTING.md"


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_static_license_files() -> int:
    required_paths = [
        LICENSE_PATH,
        THIRD_PARTY_PATH,
        WINDOWS_LICENSES_DIR / "WINDOWS_QT_NOTICE.txt",
        WINDOWS_LICENSES_DIR / "LGPL-3.0.txt",
        WINDOWS_LICENSES_DIR / "FFMPEG_NOTICE.txt",
        WRITE_BUNDLE_PATH,
    ]
    for path in required_paths:
        if not path.is_file():
            return _fail(f"Missing required license file: {path.relative_to(REPO_ROOT)}")

    license_text = _read_text(LICENSE_PATH)
    if "GNU GENERAL PUBLIC LICENSE" not in license_text:
        return _fail("LICENSE does not look like GPL-3.0")

    pkgbuild_text = _read_text(PKGBUILD_PATH)
    if "GPL-3.0-or-later" not in pkgbuild_text:
        return _fail("PKGBUILD must declare license=('GPL-3.0-or-later')")
    if "THIRD_PARTY_LICENSES.md" not in pkgbuild_text:
        return _fail("PKGBUILD must install THIRD_PARTY_LICENSES.md")

    flatpak_yaml = _read_text(FLATPAK_YAML_PATH)
    if "THIRD_PARTY_LICENSES.md" not in flatpak_yaml:
        return _fail("Flatpak manifest must install THIRD_PARTY_LICENSES.md")

    inno_text = _read_text(INNO_PATH)
    for needle in (
        "LicenseFile=..\\..\\LICENSE",
        "InfoBeforeFile=licenses\\WINDOWS_QT_NOTICE.txt",
        "licenses\\Qt_BUNDLE_INFO.txt",
    ):
        if needle not in inno_text:
            return _fail(f"Inno Setup missing expected entry: {needle}")

    build_windows_text = _read_text(BUILD_WINDOWS_PATH)
    if "write_license_bundle.py" not in build_windows_text:
        return _fail("build_windows.py must invoke write_license_bundle.py")

    for doc_path in (INSTALL_DOC_PATH, CONTRIBUTING_PATH):
        doc_text = _read_text(doc_path)
        if "MIT-licensed" in doc_text or "MIT License" in doc_text:
            return _fail(f"{doc_path.relative_to(REPO_ROOT)} still mentions MIT for the application")

    if "GPL-3.0-or-later" not in _read_text(INSTALL_DOC_PATH):
        return _fail("docs/INSTALL.md must document GPL-3.0-or-later")

    print("Static license files OK")
    return 0


def validate_windows_bundle(dist_dir: Path | None = None) -> int:
    bundle_dir = (dist_dir or (REPO_ROOT / "dist" / "Improve_ImgSLI")).resolve()
    if not bundle_dir.is_dir():
        return _fail(f"Windows bundle directory not found: {bundle_dir}")

    required = [
        "LICENSE",
        "THIRD_PARTY_LICENSES.md",
        "licenses/WINDOWS_QT_NOTICE.txt",
        "licenses/LGPL-3.0.txt",
        "licenses/Qt_BUNDLE_INFO.txt",
    ]
    for relative in required:
        path = bundle_dir / relative
        if not path.is_file():
            return _fail(f"Windows bundle missing {relative}")

    qt_info = _read_text(bundle_dir / "licenses" / "Qt_BUNDLE_INFO.txt")
    if "PySide6 version:" not in qt_info:
        return _fail("Qt_BUNDLE_INFO.txt is missing PySide6 version metadata")

    qt_dlls = list((bundle_dir / "PySide6").rglob("*.dll"))
    qt_pyds = list((bundle_dir / "PySide6").rglob("*.pyd"))
    if not qt_dlls and not qt_pyds:
        return _fail("Windows bundle has no replaceable Qt files under PySide6/")

    print(
        "Windows license bundle OK: "
        f"{len(qt_dlls)} dll, {len(qt_pyds)} pyd under PySide6/"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--windows-bundle":
        dist = Path(argv[1]).resolve() if len(argv) > 1 else None
        return validate_windows_bundle(dist)

    return validate_static_license_files()


if __name__ == "__main__":
    raise SystemExit(main())
