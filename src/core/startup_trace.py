"""Lightweight startup phase timing when IMGSLI_STARTUP_TRACE=1."""

from __future__ import annotations

import logging
import os
import time

logger = logging.getLogger("ImproveImgSLI.startup")

_origin: float | None = None
_last: float | None = None


def is_startup_trace_enabled() -> bool:
    return os.getenv("IMGSLI_STARTUP_TRACE", "0") == "1"


def startup_mark(phase: str) -> None:
    if not is_startup_trace_enabled():
        return
    global _origin, _last
    now = time.monotonic()
    if _origin is None:
        _origin = now
        _last = now
        logger.info("startup +%6.0fms  %s", 0.0, phase)
        return
    delta_ms = (now - _last) * 1000.0
    total_ms = (now - _origin) * 1000.0
    _last = now
    logger.info(
        "startup +%6.0fms (+%5.0fms)  %s",
        total_ms,
        delta_ms,
        phase,
    )
