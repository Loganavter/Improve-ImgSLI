"""``IMGSLI_FLYOUT_DEBUG``-gated tracing for the pinned corner HUD flyouts
(``ZoomIndicator``, ``InfoHUD``) — used to investigate how much rendering
load they add (backdrop grab+blur cost, how often they reposition/refresh
during a resize/zoom burst). Same convention as
``shared/rendering/render_debug.py``'s ``IMGSLI_RESIZE_DEBUG``: gate on an
env var, tag every line with a unique bracketed prefix, near-zero overhead
when disabled.
"""

from __future__ import annotations

import logging
import time

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def flyout_debug_enabled() -> bool:
    return _env_flag("IMGSLI_FLYOUT_DEBUG")


def flyout_debug(message: str, *args) -> None:
    if flyout_debug_enabled():
        logger.debug("[flyout-debug] " + message, *args)


def flyout_debug_timer() -> float:
    """Call before a timed block; pass the result to `flyout_debug_elapsed_ms`."""
    return time.perf_counter()


def flyout_debug_elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0