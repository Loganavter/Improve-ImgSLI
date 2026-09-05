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
    # Hybrid per gallery fix 2026-08-26 (see docs/dev/LOGGING.md
    # "Collaborative debugging"): WARNING when the explicit env flag is set
    # (visible without --debug, no flag-flipping needed to collaborate),
    # DEBUG otherwise (visible with global --debug).
    if flyout_debug_enabled():
        logger.warning("[flyout-debug] " + message, *args)
    else:
        logger.debug("[flyout-debug] " + message, *args)


def flyout_debug_timer() -> float:
    """Call before a timed block; pass the result to `flyout_debug_elapsed_ms`."""
    return time.perf_counter()


def flyout_debug_elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000.0