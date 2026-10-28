"""Qt platform theme selection for the native file chooser.

Owner decision 2026-10-28: the project file dialogs must be the **native GNOME
chooser, through the XDG desktop portal** ("вернуть нативный через портал").
The portal answers in a separate application and parents that window itself, so
the native look and the "dialog lands under the main window" fix coexist; Qt's
*in-process* GTK dialog is the shape that could map behind us
(`docs/dev/platform/investigations/help-dialog-opens-below-main-window.md`).

Only seeds ``QT_QPA_PLATFORMTHEME`` — it must run before ``QApplication`` exists,
and it never overrides a theme the user (or the launcher) already chose.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

__all__ = ["apply_portal_platform_theme", "resolve_platform_theme"]


def resolve_platform_theme(
    environ: Mapping[str, str] | None = None, *, plugin_dir: str | None = None
) -> str | None:
    """Platform theme to seed for a portal-backed chooser, or ``None``.

    ``None`` in three cases, each deliberate: the user already chose a theme, the
    build has no portal plugin (Qt keeps its default instead of losing its whole
    platform theme), or the Qt plugin path cannot be resolved.
    """
    env = os.environ if environ is None else environ
    if env.get("QT_QPA_PLATFORMTHEME"):
        return None
    if plugin_dir is None:
        try:
            from PySide6.QtCore import QLibraryInfo

            plugin_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
        except Exception:
            return None
    try:
        from pathlib import Path

        themes = Path(plugin_dir) / "platformthemes"
        if not any(themes.glob("*xdgdesktopportal*")):
            return None
    except Exception:
        return None
    return "xdgdesktopportal"


def apply_portal_platform_theme() -> str | None:
    """Seed ``QT_QPA_PLATFORMTHEME`` once; return the value that was set."""
    theme = resolve_platform_theme()
    if not theme:
        return None
    os.environ.setdefault("QT_QPA_PLATFORMTHEME", theme)
    return theme
