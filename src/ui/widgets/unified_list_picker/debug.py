"""``IMGSLI_DOUBLE_GEOM_DEBUG``-gated tracing for UnifiedListPicker geometry.

Own env var + own prefix per docs/dev/LOGGING.md "unique-prefix convention":
the shared ``[flyout-debug]`` stream (HUD hovers, presenter sync, zoom
bursts) is far too noisy to reuse — enabling it floods the log with
thousands of lines. These points fire rarely (flyout open / single↔double
switch / refresh), so hybrid emit is safe: WARNING when the explicit env
flag is set (visible without ``--debug``), DEBUG otherwise.

Usage:
    IMGSLI_DOUBLE_GEOM_DEBUG=1 ./launcher.sh run
    rg '\\[double-geom\\]' ~/.local/share/ImproveImgSLI/log.txt

Temporary collaborative diagnostics — remove after the double-list
geometry investigation lands (see LOGGING.md "Collaborative debugging").
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def double_geom_debug_enabled() -> bool:
    return _env_flag("IMGSLI_DOUBLE_GEOM_DEBUG")


def double_geom_debug(message: str, *args) -> None:
    if double_geom_debug_enabled():
        logger.warning("[double-geom] " + message, *args)
    else:
        logger.debug("[double-geom] " + message, *args)
