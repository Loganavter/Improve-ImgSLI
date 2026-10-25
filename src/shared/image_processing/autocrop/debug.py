"""Единый поток логирования автокропа — IMGSLI_AUTOCROP_DEBUG=1."""
from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def autocrop_debug(message: str, *args) -> None:
    """Env-gated диагностика — префикс [autocrop-debug] для grep из log.txt."""
    if _env_flag("IMGSLI_AUTOCROP_DEBUG"):
        logger.debug("[autocrop-debug] " + message, *args)
