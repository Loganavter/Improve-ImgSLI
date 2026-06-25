from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QRhiWidget

logger = logging.getLogger("ImproveImgSLI.rhi")

RHI_BACKEND_ENV = "IMPROVE_IMGSLI_RHI_BACKEND"

_API_BY_NAME = {
    "default": None,
    "opengl": QRhiWidget.Api.OpenGL,
    "vulkan": QRhiWidget.Api.Vulkan,
    "d3d11": QRhiWidget.Api.Direct3D11,
    "d3d12": QRhiWidget.Api.Direct3D12,
    "metal": QRhiWidget.Api.Metal,
    "null": QRhiWidget.Api.Null,
}


def supported_rhi_backend_names() -> tuple[str, ...]:
    return tuple(_API_BY_NAME)


def requested_rhi_backend_name() -> str:
    value = os.environ.get(RHI_BACKEND_ENV, "default").strip().lower()
    return value if value in _API_BY_NAME else "default"


def configure_rhi_process_environment(backend_name: str) -> bool:
    """Apply process-wide platform requirements before QApplication exists.

    On the verified Qt 6.11.1 + GNOME Wayland + NVIDIA environment,
    QRhiWidget with the Vulkan API gets zero frame margins. The same minimal
    widget works correctly through XWayland, so explicit Vulkan requests use
    the xcb QPA plugin on Linux Wayland unless the caller already selected a
    platform.
    """
    os.environ[RHI_BACKEND_ENV] = backend_name
    if (
        backend_name == "vulkan"
        and sys.platform.startswith("linux")
        and (
            os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )
        and not os.environ.get("QT_QPA_PLATFORM")
    ):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
        return True
    return False


def configure_rhi_widget(widget: QRhiWidget) -> None:
    name = requested_rhi_backend_name()
    api = _API_BY_NAME[name]
    if api is not None:
        widget.setApi(api)
    actual_name = getattr(widget.api(), "name", "platform-default")
    widget.renderFailed.connect(
        lambda: logger.error(
            "%s renderFailed requested=%s actual=%s",
            type(widget).__name__,
            name,
            getattr(widget.api(), "name", "platform-default"),
        )
    )
    logger.debug(
        "%s configured requested=%s api=%s",
        type(widget).__name__,
        name,
        actual_name,
    )


def log_initialized_rhi_widget(widget: QRhiWidget) -> None:
    rhi = widget.rhi()
    logger.debug(
        "%s initialized requested=%s api=%s rhi=%r target=%r size=%s",
        type(widget).__name__,
        requested_rhi_backend_name(),
        widget.api().name,
        rhi,
        widget.renderTarget(),
        widget.renderTarget().pixelSize() if widget.renderTarget() is not None else None,
    )
