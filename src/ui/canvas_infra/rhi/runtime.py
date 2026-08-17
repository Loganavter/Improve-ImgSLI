from __future__ import annotations

import logging
import os

from PySide6.QtGui import QSurfaceFormat

logger = logging.getLogger("ImproveImgSLI")


def should_prefer_gles() -> bool:
    force_desktop = os.getenv("IMPROVE_IMGSLI_FORCE_DESKTOP_GL", "").strip().lower()
    if force_desktop in {"1", "true", "yes", "on"}:
        return False

    force_gles = os.getenv("IMPROVE_IMGSLI_FORCE_GLES", "").strip().lower()
    if force_gles in {"1", "true", "yes", "on"}:
        return True

    session_type = os.getenv("XDG_SESSION_TYPE", "").strip().lower()
    has_wayland = bool(os.getenv("WAYLAND_DISPLAY"))
    return session_type == "wayland" or has_wayland


