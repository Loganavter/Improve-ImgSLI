"""Единый поток логирования автокропа — IMGSLI_AUTOCROP_DEBUG=1."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("ImproveImgSLI")


def autocrop_debug(message: str, *args) -> None:
    """Env-gated диагностика — префикс [autocrop-debug] для grep из log.txt."""
    if os.environ.get("IMGSLI_AUTOCROP_DEBUG") == "1":
        logger.debug("[autocrop-debug] " + message, *args)
