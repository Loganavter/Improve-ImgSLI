"""Write version-specific license metadata into a Windows PyInstaller bundle."""

from __future__ import annotations

import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path


def _dist_dir(repo_root: Path) -> Path:
    return repo_root / "dist" / "Improve_ImgSLI"


def _pyside6_root() -> Path:
    pyside6 = importlib.import_module("PySide6")
    module_file = getattr(pyside6, "__file__", None)
    if not module_file:
        raise RuntimeError("Unable to locate PySide6 installation.")
    return Path(module_file).resolve().parent


def _relative_qt_paths(dist_dir: Path) -> list[str]:
    paths: list[str] = []
    for path in sorted(dist_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".dll", ".pyd"}:
            continue
        rel = path.relative_to(dist_dir)
        if "PySide6" in rel.parts:
            paths.append(rel.as_posix())
    return paths


def write_license_bundle(repo_root: Path | None = None) -> Path:
    repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    dist_dir = _dist_dir(repo_root)
    if not dist_dir.is_dir():
        raise FileNotFoundError(f"Windows bundle directory not found: {dist_dir}")

    licenses_dir = dist_dir / "licenses"
    licenses_dir.mkdir(parents=True, exist_ok=True)

    template_dir = repo_root / "build" / "Windows-template" / "licenses"
    for name in ("WINDOWS_QT_NOTICE.txt", "LGPL-3.0.txt", "FFMPEG_NOTICE.txt"):
        source = template_dir / name
        if source.is_file():
            (licenses_dir / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    pyside6 = importlib.import_module("PySide6")
    shiboken6 = importlib.import_module("shiboken6")
    pyside_root = _pyside6_root()
    qt_root = pyside_root / "Qt6" if (pyside_root / "Qt6").exists() else pyside_root

    qt_paths = _relative_qt_paths(dist_dir)
    lines = [
        "Improve ImgSLI — Qt bundle metadata",
        "=================================",
        "",
        f"Generated (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"PySide6 version: {getattr(pyside6, '__version__', 'unknown')}",
        f"shiboken6 version: {getattr(shiboken6, '__version__', 'unknown')}",
        f"Build-time PySide6 root: {pyside_root}",
        f"Build-time Qt root: {qt_root}",
        "",
        "Replaceable Qt / PySide6 files in this installation:",
        "",
    ]
    if qt_paths:
        lines.extend(f"  - {path}" for path in qt_paths)
    else:
        lines.append("  (none found — rebuild the bundle on Windows with PySide6 present)")

    lines.extend(
        [
            "",
            "See licenses\\WINDOWS_QT_NOTICE.txt for replacement instructions.",
            "See LICENSE and THIRD_PARTY_LICENSES.md in the install root.",
            "",
        ]
    )

    bundle_info = licenses_dir / "Qt_BUNDLE_INFO.txt"
    bundle_info.write_text("\n".join(lines), encoding="utf-8")
    return bundle_info


def main(argv: list[str] | None = None) -> int:
    repo_root = Path(argv[1]).resolve() if argv and len(argv) > 1 else None
    try:
        path = write_license_bundle(repo_root)
    except Exception as exc:
        print(f"Failed to write Windows license bundle: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
