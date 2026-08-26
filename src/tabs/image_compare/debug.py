"""``IMGSLI_IMAGE_COMPARE_DEBUG``-gated tracing for Image Compare DnD.

Mirrors ``tabs/image_gallery/debug.py``:
``IMGSLI_GALLERY_DEBUG`` → ``[gallery-dnd]`` / ``[gallery-debug]``.

Env vars:
    IMGSLI_IMAGE_COMPARE_DEBUG=1 — official
    IMGSLI_IC_DEBUG=1            — short alias (same flag)

Tags:
    [ic-dnd]   — drag-enter / accept / handle_drop routing
    [ic-debug] — generic lifecycle

Both helpers emit ``WARNING`` when explicit env flag is set (visible without
``--debug``) and ``DEBUG`` when global ``--debug`` is on — hybrid per
gallery fix 2026-08-26. See ``docs/dev/LOGGING.md``.
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def _ic_debug_enabled() -> bool:
    return (
        _env_flag("IMGSLI_IMAGE_COMPARE_DEBUG")
        or _env_flag("IMGSLI_IC_DEBUG")
        or logger.isEnabledFor(logging.DEBUG)
    )


def _emit(prefix: str, msg: str, *args, **kwargs) -> None:
    if _env_flag("IMGSLI_IMAGE_COMPARE_DEBUG") or _env_flag("IMGSLI_IC_DEBUG"):
        logger.warning(prefix + " " + msg, *args, **kwargs)
    else:
        logger.debug(prefix + " " + msg, *args, **kwargs)


def ic_debug_enabled() -> bool:
    return _ic_debug_enabled()


def ic_dnd_debug_enabled() -> bool:
    return _ic_debug_enabled()


def ic_debug(msg: str, *args, **kwargs) -> None:
    if ic_debug_enabled():
        _emit("[ic-debug]", msg, *args, **kwargs)


def ic_dnd_debug(msg: str, *args, **kwargs) -> None:
    if ic_dnd_debug_enabled():
        _emit("[ic-dnd]", msg, *args, **kwargs)
