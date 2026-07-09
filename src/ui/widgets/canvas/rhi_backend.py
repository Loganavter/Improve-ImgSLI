from __future__ import annotations

import logging
import os
import sys

from PySide6.QtWidgets import QRhiWidget

logger = logging.getLogger("ImproveImgSLI.rhi")

RHI_BACKEND_ENV = "IMPROVE_IMGSLI_RHI_BACKEND"
ALLOW_LSFGVK_ENV = "IMPROVE_IMGSLI_ALLOW_LSFGVK"
DISABLE_LSFGVK_ENV = "DISABLE_LSFGVK"

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


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def configure_vulkan_layer_environment(backend_name: str) -> bool:
    """Disable known-bad implicit Vulkan layers for the app's QRhi widgets."""
    if (
        backend_name == "vulkan"
        and sys.platform.startswith("linux")
        and not _env_flag(ALLOW_LSFGVK_ENV)
    ):
        os.environ[DISABLE_LSFGVK_ENV] = "1"
        return True
    return False


def configure_rhi_process_environment(backend_name: str) -> None:
    """Apply the process-wide backend selection before QApplication exists."""
    os.environ[RHI_BACKEND_ENV] = backend_name


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


def log_initialized_rhi_widget(widget: QRhiWidget) -> None:
    pass
