from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


REPO_ROOT = Path(__file__).resolve().parents[2]
METAINFO_PATH = REPO_ROOT / "build" / "Flatpak-template" / "io.github.Loganavter.Improve-ImgSLI.metainfo.xml"
PKGBUILD_PATH = REPO_ROOT / "build" / "AUR-template" / "PKGBUILD"
INNO_PATH = REPO_ROOT / "build" / "Windows-template" / "inno_setup_6.iss"
BUILD_WINDOWS_PATH = REPO_ROOT / "build" / "Windows-template" / "build_windows.py"
FLATPAK_YAML_PATH = REPO_ROOT / "build" / "Flatpak-template" / "io.github.Loganavter.Improve-ImgSLI.yaml"


def _fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract(pattern: str, text: str, label: str) -> str:
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        raise ValueError(f"Unable to find {label}")
    return match.group(1)


def main() -> int:
    today_moscow = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%Y-%m-%d")

    root = ET.parse(METAINFO_PATH).getroot()
    releases = root.find("releases")
    if releases is None or not list(releases):
        return _fail("No releases found in metainfo XML")

    latest_release = list(releases)[0]
    flatpak_version = latest_release.attrib.get("version")
    flatpak_date = latest_release.attrib.get("date")
    if not flatpak_version:
        return _fail("Latest Flatpak release entry has no version")
    if flatpak_date != today_moscow:
        return _fail(
            f"Latest Flatpak release date is {flatpak_date}, expected today's Moscow date {today_moscow}"
        )

    pkgbuild_text = _read_text(PKGBUILD_PATH)
    aur_version = _extract(r"^pkgver=([^\n]+)$", pkgbuild_text, "AUR pkgver")

    inno_text = _read_text(INNO_PATH)
    windows_version = _extract(
        r'^#define MyAppVersion "([^"]+)"$',
        inno_text,
        "Windows installer version",
    )

    build_windows_text = _read_text(BUILD_WINDOWS_PATH)
    setup_version = _extract(
        r'Improve_ImgSLI_Setup_v([0-9][^"]*)\.exe',
        build_windows_text,
        "build_windows.py setup exe version",
    )

    flatpak_yaml_text = _read_text(FLATPAK_YAML_PATH)
    archive_version = _extract(
        r"Improve-ImgSLI-([0-9][^.]*(?:\.[0-9]+)+)\.tar\.gz",
        flatpak_yaml_text,
        "Flatpak archive version",
    )

    versions = {
        "flatpak_metainfo": flatpak_version,
        "aur_pkgbuild": aur_version,
        "windows_inno": windows_version,
        "windows_build_script": setup_version,
        "flatpak_archive": archive_version,
    }
    unique_versions = set(versions.values())
    if len(unique_versions) != 1:
        lines = ", ".join(f"{key}={value}" for key, value in versions.items())
        return _fail(f"Version mismatch detected: {lines}")

    version = unique_versions.pop()
    print(f"Release metadata OK: version={version}, date={flatpak_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
