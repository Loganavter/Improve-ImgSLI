"""Windows shell registration for portable ``.blinktable`` project files.

Registers a ProgID (BlinkTable.Project) under HKCU so Explorer shows a
document-style icon and opens files with this app instead of treating them as
generic ZIP archives. Pre-rename ``.imgsli`` projects are mapped to the same
ProgID, so existing files keep opening after the format rename. Content
thumbnails (``IThumbnailProvider``) are still a separate native shell extension
— see ``docs/dev/tabs/session-lifecycle.md``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from core.log_names import APP_LOGGER_NAME
from shared.debug_flags import env_value as _env_value

logger = logging.getLogger(APP_LOGGER_NAME)

PROGID = "BlinkTable.Project"
LEGACY_PROGID = "ImproveImgSLI.Project"
FRIENDLY_TYPE_NAME = "BlinkTable Project"
CONTENT_TYPE = "application/vnd.blinktable.project+zip"
LEGACY_CONTENT_TYPE = "application/x-improve-imgsli"
EXTENSION = ".blinktable"
LEGACY_EXTENSION = ".imgsli"


def extension_mappings() -> tuple[tuple[str, str], ...]:
    """``(extension, Content Type)`` pairs: current format + pre-rename files."""
    return ((EXTENSION, CONTENT_TYPE), (LEGACY_EXTENSION, LEGACY_CONTENT_TYPE))


def _is_windows() -> bool:
    return sys.platform == "win32"


def _frozen_exe() -> Path | None:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


def _icon_candidates(exe: Path | None) -> list[Path]:
    candidates: list[Path] = []
    if exe is not None:
        root = exe.parent
        candidates.extend(
            [
                root / "icons" / "blinktable-file.ico",
                root / "blinktable-file.ico",
                root / "icons" / "icon.ico",
                root / "icon.ico",
            ]
        )
    try:
        from utils.resource_loader import resource_path

        candidates.append(Path(resource_path("resources/icons/blinktable-file.ico")))
        candidates.append(Path(resource_path("resources/icons/icon.png")))
    except Exception:
        pass
    here = Path(__file__).resolve()
    candidates.append(here.parents[2] / "resources" / "icons" / "blinktable-file.ico")
    return candidates


def resolve_file_type_icon(exe: Path | None = None) -> Path | None:
    for path in _icon_candidates(exe if exe is not None else _frozen_exe()):
        try:
            if path.is_file():
                return path.resolve()
        except OSError:
            continue
    return None


def open_command_for_exe(exe: Path) -> str:
    return f'"{exe}" "%1"'


def _reg_set(key, name: str | None, value: str) -> None:
    import winreg

    winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


def _reg_get(key, name: str | None) -> str | None:
    import winreg

    try:
        value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None
    return str(value) if value is not None else None


def association_is_current(*, exe: Path, icon: Path | None) -> bool:
    """Return True when HKCU already matches this install."""
    if not _is_windows():
        return True
    import winreg

    command = open_command_for_exe(exe)
    icon_value = f"{icon},0" if icon is not None else None
    try:
        for extension, _content_type in extension_mappings():
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{extension}"
            ) as key:
                if _reg_get(key, None) != PROGID:
                    return False
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}\shell\open\command"
        ) as key:
            if _reg_get(key, None) != command:
                return False
        if icon_value is not None:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}\DefaultIcon"
            ) as key:
                if _reg_get(key, None) != icon_value:
                    return False
    except OSError:
        return False
    return True


def register_project_file_association(
    *,
    exe: Path | None = None,
    icon: Path | None = None,
    force: bool = False,
) -> bool:
    """Write HKCU ProgID + project extension mappings.

    Maps both ``.blinktable`` and the pre-rename ``.imgsli`` to ``PROGID`` so a
    double-click on an old project keeps working. Returns True if the registry
    changed.
    """
    if not _is_windows():
        return False

    resolved_exe = (exe or _frozen_exe())
    if resolved_exe is None or not resolved_exe.is_file():
        logger.debug("Skip project file association: no frozen executable")
        return False

    resolved_icon = icon if icon is not None else resolve_file_type_icon(resolved_exe)
    if not force and association_is_current(exe=resolved_exe, icon=resolved_icon):
        return False

    import winreg

    command = open_command_for_exe(resolved_exe)
    icon_value = f"{resolved_icon},0" if resolved_icon is not None else f"{resolved_exe},0"

    # Extension(s) → ProgID
    for extension, content_type in extension_mappings():
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{extension}"
        ) as key:
            _reg_set(key, None, PROGID)
            _reg_set(key, "Content Type", content_type)
            # Avoid Explorer treating the package as a generic compressed folder.
            try:
                winreg.DeleteValue(key, "PerceivedType")
            except OSError:
                pass

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{extension}\OpenWithProgids"
        ) as key:
            _reg_set(key, PROGID, "")
            # Keep the pre-rename ProgID offered for installs that still have it.
            _reg_set(key, LEGACY_PROGID, "")

    # ProgID
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}") as key:
        _reg_set(key, None, FRIENDLY_TYPE_NAME)
        _reg_set(key, "FriendlyTypeName", FRIENDLY_TYPE_NAME)

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}\DefaultIcon"
    ) as key:
        _reg_set(key, None, icon_value)

    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROGID}\shell\open\command"
    ) as key:
        _reg_set(key, None, command)

    _notify_shell_assoc_changed()
    logger.info(
        "Registered Windows file associations for %s, %s → %s",
        EXTENSION,
        LEGACY_EXTENSION,
        resolved_exe,
    )
    return True


def ensure_windows_file_association() -> None:
    """Idempotent startup hook for frozen Windows builds."""
    if not _is_windows() or not getattr(sys, "frozen", False):
        return
    if (_env_value("IMGSLI_SKIP_FILE_ASSOCIATION", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return
    try:
        register_project_file_association()
    except Exception:
        logger.debug("Windows project association failed", exc_info=True)


def _notify_shell_assoc_changed() -> None:
    try:
        import ctypes

        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        logger.debug("SHChangeNotify failed", exc_info=True)
