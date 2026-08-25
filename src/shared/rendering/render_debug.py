"""Shared ``IMGSLI_RESIZE_DEBUG``-gated render tracing, used by every tab's
QRhi render path. Originally scoped to a single tab's own ``rhi_renderer``
package (kept there as a thin re-export for existing call sites); moved here
so every tab's tile-array path can log the same way instead of each keeping
its own copy of this helper (docs/dev/rendering/tile-array-atlas-plan.md's
debug-instrumented phases relied on exactly this pattern to find real bugs
from user-shared logs).
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def rhi_render_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RESIZE_DEBUG")


def rhi_render_debug(message: str, *args) -> None:
    if rhi_render_debug_enabled():
        logger.debug("[rhi-render-debug] " + message, *args)
