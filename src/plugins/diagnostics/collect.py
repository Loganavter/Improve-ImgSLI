"""Environment / build snapshot for the diagnostics report.

Pure(-ish) collectors. **Every field is fail-open**: a probe that raises or
returns nothing yields ``None`` (or an ``"unknown"`` marker) instead of
breaking the report. Callers get plain JSON-able dicts.

File access is limited to *system* introspection (``/sys``, ``/etc``,
``/proc``-style paths and optional tool probes). This module never reads the
user's documents, projects, or images.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "collect_app_info",
    "collect_environment",
]

_PCI_VENDORS = {
    "0x10de": "NVIDIA",
    "0x1002": "AMD",
    "0x1022": "AMD",
    "0x8086": "Intel",
    "0x1af4": "Red Hat (virtio)",
    "0x15ad": "VMware",
    "0x1b36": "Red Hat (QXL)",
    "0x106b": "Apple",
}


def _safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try:
        value = fn()
    except Exception:
        return default
    return default if value is None else value


def _read_text(path: str | Path, limit: int = 512) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")[:limit].strip()
    except Exception:
        return None


def _run(argv: list[str], timeout: float = 2.0) -> str | None:
    if not shutil.which(argv[0]):
        return None
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None
    out = (proc.stdout or "").strip()
    return out or None


# --------------------------------------------------------------------------
# App / build
# --------------------------------------------------------------------------

def _app_version() -> str | None:
    try:
        from core.constants import AppConstants

        return str(AppConstants.APP_VERSION)
    except Exception:
        return None


def _install_source() -> str:
    if os.environ.get("FLATPAK_ID") or Path("/.flatpak-info").exists():
        return "flatpak"
    if os.environ.get("APPIMAGE"):
        return "appimage"
    if getattr(sys, "frozen", False):
        if sys.platform.startswith("win"):
            return "windows_installer"
        if sys.platform == "darwin":
            return "macos_bundle"
        return "frozen"
    return "source"


def _commit() -> str | None:
    for key in ("IMPROVE_IMGSLI_COMMIT", "GIT_COMMIT", "BUILD_COMMIT"):
        value = os.environ.get(key)
        if value:
            return value
    return None


def collect_app_info() -> dict[str, Any]:
    return {
        "name": _safe(lambda: "Improve ImgSLI", "Improve ImgSLI"),
        "version": _safe(_app_version),
        "commit": _safe(_commit),
        "channel": _safe(lambda: os.environ.get("IMPROVE_IMGSLI_CHANNEL") or "stable"),
        "install_source": _safe(_install_source, "unknown"),
        "frozen": _safe(lambda: bool(getattr(sys, "frozen", False)), False),
    }


# --------------------------------------------------------------------------
# Runtime (Python / Qt)
# --------------------------------------------------------------------------

def _qt_version() -> str | None:
    try:
        from PySide6 import __version__ as pyside_version  # type: ignore
    except Exception:
        return None
    qt = _safe(lambda: __import__("PySide6.QtCore", fromlist=["qVersion"]).qVersion())
    if qt:
        return f"PySide6 {pyside_version} (Qt {qt})"
    return f"PySide6 {pyside_version}"


def _faulthandler_enabled() -> bool | None:
    try:
        import faulthandler

        return bool(faulthandler.is_enabled())
    except Exception:
        return None


def collect_runtime() -> dict[str, Any]:
    return {
        "python_version": _safe(lambda: platform.python_version()),
        "python_implementation": _safe(lambda: platform.python_implementation()),
        "executable": _safe(lambda: sys.executable),
        "qt": _safe(_qt_version, "unknown"),
        "faulthandler_enabled": _safe(_faulthandler_enabled),
    }


# --------------------------------------------------------------------------
# Machine
# --------------------------------------------------------------------------

def _ram_bytes() -> int | None:
    try:
        return int(os.sysconf("SC_PAGE_SIZE")) * int(os.sysconf("SC_PHYS_PAGES"))
    except Exception:
        pass
    return _safe(
        lambda: int(
            __import__("re").search(
                r"MemTotal:\s+(\d+) kB", _read_text("/proc/meminfo") or ""
            ).group(1)
        )
        * 1024
    )


def _total_ram_human() -> str | None:
    value = _ram_bytes()
    if not value:
        return None
    return f"{value / (1024 ** 3):.1f} GiB"


def _cpu_model() -> str | None:
    text = _read_text("/proc/cpuinfo", limit=8192)
    if text:
        match = re.search(r"^model name\s*:\s*(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    return _safe(lambda: platform.processor() or None)


def _gpu_info() -> list[dict[str, Any]]:
    """Best-effort GPU list. Linux sysfs + optional ``nvidia-smi``."""
    gpus: list[dict[str, Any]] = []

    nvidia = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if nvidia:
        for line in nvidia.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if parts and parts[0]:
                gpus.append(
                    {
                        "name": parts[0],
                        "driver": parts[1] if len(parts) > 1 else None,
                        "vendor": "NVIDIA",
                    }
                )

    if not gpus and sys.platform.startswith("linux"):
        try:
            for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
                device = card / "device"
                uevent = _read_text(device / "uevent")
                if not uevent:
                    continue
                fields = dict(
                    (line.split("=", 1) + [""])[:2]
                    for line in uevent.splitlines()
                    if "=" in line
                )
                pci_id = fields.get("PCI_ID", "")
                vendor_id = pci_id.split(":")[0].lower() if ":" in pci_id else ""
                gpus.append(
                    {
                        "name": fields.get("DRIVER") and f"{pci_id} ({fields['DRIVER']})" or pci_id,
                        "driver": fields.get("DRIVER") or None,
                        "vendor": _PCI_VENDORS.get(vendor_id, vendor_id or "unknown"),
                        "pci_id": pci_id or None,
                    }
                )
        except Exception:
            pass
    return gpus


def _rhi_backend() -> str | None:
    env_value = os.environ.get("IMPROVE_IMGSLI_RHI_BACKEND")
    if env_value:
        return env_value.strip().lower()
    settings_value = _safe(
        lambda: __import__(
            "PySide6.QtCore", fromlist=["QSettings"]
        ).QSettings("improve-imgsli", "improve-imgsli").value("rhi_backend")
    )
    if settings_value:
        return str(settings_value).strip().lower()
    return "default"


def collect_machine() -> dict[str, Any]:
    return {
        "os": _safe(lambda: f"{platform.system()} {platform.release()}", "unknown"),
        "os_version": _safe(lambda: platform.version()),
        "kernel": _safe(
            lambda: platform.uname().release if hasattr(platform, "uname") else os.uname().release
        ),
        "arch": _safe(lambda: platform.machine()),
        "cpu": _safe(_cpu_model, "unknown"),
        "cpu_count": _safe(lambda: os.cpu_count()),
        "ram": _safe(_total_ram_human),
        "gpu": _safe(_gpu_info, []),
        "rhi_backend": _safe(_rhi_backend, "unknown"),
    }


# --------------------------------------------------------------------------
# Session / display
# --------------------------------------------------------------------------

def _compositor() -> str | None:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("XDG_SESSION_DESKTOP")
    if desktop:
        return desktop
    if os.environ.get("SWAYSOCK"):
        return "sway"
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return "Hyprland"
    if os.environ.get("KDE_FULL_SESSION"):
        return "KDE"
    if os.environ.get("GNOME_DESKTOP_SESSION_ID"):
        return "GNOME"
    return None


def _compositor_version() -> str | None:
    for argv in (
        ["plasmashell", "--version"],
        ["gnome-shell", "--version"],
        ["sway", "--version"],
        ["hyprctl", "version"],
        ["kwin_wayland", "--version"],
    ):
        out = _run(argv, timeout=1.5)
        if out:
            return out.splitlines()[0][:120]
    return None


def _session_type() -> str:
    explicit = os.environ.get("XDG_SESSION_TYPE")
    if explicit:
        return explicit.strip().lower()
    if os.environ.get("WAYLAND_DISPLAY"):
        return "wayland"
    if os.environ.get("DISPLAY"):
        return "x11"
    return "unknown"


def _display_server() -> str:
    stype = _session_type()
    if stype == "wayland":
        return f"Wayland ({os.environ.get('WAYLAND_DISPLAY', '?')})"
    if stype == "x11":
        return f"X11 ({os.environ.get('DISPLAY', '?')})"
    return "unknown"


def _locale() -> dict[str, Any]:
    return {
        "lang": _safe(lambda: os.environ.get("LANG")),
        "lc_all": _safe(lambda: os.environ.get("LC_ALL")),
        "preferred": _safe(lambda: __import__("locale").getlocale()[0]),
    }


def _timezone() -> dict[str, Any]:
    offset = _safe(lambda: -time.timezone / 3600 if not time.daylight else -time.altzone / 3600)
    name = _safe(lambda: time.tzname[time.daylight] if time.tzname else None)
    return {
        "name": _safe(lambda: os.environ.get("TZ")),
        "tzname": name,
        "utc_offset_hours": None if offset is None else round(float(offset), 2),
    }


def _screens() -> list[dict[str, Any]]:
    screens: list[dict[str, Any]] = []
    try:
        from PySide6.QtGui import QGuiApplication

        app = QGuiApplication.instance()
        if app is None:
            return screens
        for screen in app.screens():
            geometry = screen.geometry()
            screens.append(
                {
                    "name": screen.name(),
                    "size": [geometry.width(), geometry.height()],
                    "dpi_scale": round(float(screen.devicePixelRatio()), 2),
                }
            )
    except Exception:
        return screens
    return screens


def _theme() -> str | None:
    try:
        from sli_ui_toolkit.theme import ThemeManager

        return str(ThemeManager.get_instance().get_current_theme())
    except Exception:
        return None


def collect_environment() -> dict[str, Any]:
    return {
        "session_type": _safe(_session_type, "unknown"),
        "display_server": _safe(_display_server, "unknown"),
        "compositor": _safe(_compositor),
        "compositor_version": _safe(_compositor_version),
        "locale": _safe(_locale, {}),
        "timezone": _safe(_timezone, {}),
        "screens": _safe(_screens, []),
        "theme": _safe(_theme),
    }
