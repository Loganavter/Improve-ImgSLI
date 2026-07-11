from __future__ import annotations

import logging
import os

logger = logging.getLogger("ImproveImgSLI")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def rhi_render_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_DEBUG")


def rhi_render_debug(message: str, *args) -> None:
    if rhi_render_debug_enabled():
        logger.debug("[rhi-render-debug] " + message, *args)
