from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
METAINFO_PATH = REPO_ROOT / "build" / "Flatpak-template" / "io.github.Loganavter.Improve-ImgSLI.metainfo.xml"
PKGBUILD_PATH = REPO_ROOT / "build" / "AUR-template" / "PKGBUILD"
INNO_PATH = REPO_ROOT / "build" / "Windows-template" / "inno_setup_6.iss"
BUILD_WINDOWS_PATH = REPO_ROOT / "build" / "Windows-template" / "build_windows.py"
FLATPAK_YAML_PATH = REPO_ROOT / "build" / "Flatpak-template" / "io.github.Loganavter.Improve-ImgSLI.yaml"
FLATPAK_MODULES_PATH = REPO_ROOT / "build" / "Flatpak-template" / "python3-modules.json"


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


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _check_sli_ui_toolkit_version_floor() -> str | None:
    """AUR's declared minimum sli-ui-toolkit version must not lag behind the
    exact version Flatpak pins and actually tests against.

    Regression this guards: an unpinned/too-low ``python-sli-ui-toolkit``
    dependency in PKGBUILD let pacman install an old toolkit release whose
    API didn't have symbols this app's release already imports
    (``ModuleNotFoundError`` / ``ImportError: cannot import name '...'``
    reported by AUR users). Flatpak's pin in python3-modules.json is the
    version this project has actually verified the release against, so it's
    the source of truth for the AUR floor.
    """
    flatpak_modules_text = _read_text(FLATPAK_MODULES_PATH)
    flatpak_toolkit_version = _extract(
        r"sli_ui_toolkit-([0-9]+(?:\.[0-9]+)+)\.tar\.gz",
        flatpak_modules_text,
        "Flatpak-pinned sli-ui-toolkit version",
    )

    pkgbuild_text = _read_text(PKGBUILD_PATH)
    match = re.search(r"'python-sli-ui-toolkit>=([0-9]+(?:\.[0-9]+)+)'", pkgbuild_text)
    if not match:
        return (
            "PKGBUILD's 'depends' must pin a minimum sli-ui-toolkit version "
            "('python-sli-ui-toolkit>=X.Y.Z'), not an unbounded dependency — "
            "an unbounded/absent version let AUR install an incompatible "
            "toolkit release before (ModuleNotFoundError / ImportError on "
            "startup)."
        )
    aur_floor = match.group(1)

    if _version_tuple(aur_floor) < _version_tuple(flatpak_toolkit_version):
        return (
            f"PKGBUILD's python-sli-ui-toolkit floor ({aur_floor}) is older than "
            f"the sli-ui-toolkit version Flatpak actually pins/tests "
            f"({flatpak_toolkit_version}) — bump PKGBUILD's depends bound to "
            f"at least {flatpak_toolkit_version}."
        )
    return None


def main() -> int:
    moscow_tz = timezone(timedelta(hours=3))
    today_moscow = datetime.now(timezone.utc).astimezone(moscow_tz).strftime("%Y-%m-%d")

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

    toolkit_error = _check_sli_ui_toolkit_version_floor()
    if toolkit_error:
        return _fail(toolkit_error)

    print(f"Release metadata OK: version={version}, date={flatpak_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())