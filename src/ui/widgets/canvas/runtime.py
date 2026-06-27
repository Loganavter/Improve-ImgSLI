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


def build_canvas_surface_format() -> QSurfaceFormat:
    fmt = QSurfaceFormat()
    if should_prefer_gles():
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGLES)
        fmt.setVersion(3, 0)
    else:
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setAlphaBufferSize(8)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSamples(0)
    return fmt


def log_canvas_backend_choice(canvas_type: str) -> None:
    logger.warning("Image canvas backend selected: %s", canvas_type)
