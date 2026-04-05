from __future__ import annotations

import logging
import os

from PyQt6.QtGui import QSurfaceFormat

logger = logging.getLogger("ImproveImgSLI")

def quick_canvas_backend_name() -> str:
    return os.getenv("IMPROVE_IMGSLI_CANVAS_BACKEND", "").strip().lower()

def should_use_quick_probe_canvas() -> bool:
    return quick_canvas_backend_name() in {"quick", "quick-probe", "qml"}

def should_use_opengl_widget_canvas() -> bool:
    backend = quick_canvas_backend_name()
    if backend in {"opengl-widget", "widget", "qopenglwidget"}:
        return True
    if backend in {"opengl-window", "window", "qopenglwindow"}:
        return False
    if backend:
        return False
    return True

def should_use_software_canvas() -> bool:
    force_sw = os.getenv("IMPROVE_IMGSLI_FORCE_SOFTWARE_CANVAS", "").strip().lower()
    if force_sw in {"1", "true", "yes", "on"}:
        return True

    return False

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
