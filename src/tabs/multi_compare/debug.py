"""``IMGSLI_MULTI_COMPARE_DEBUG``-gated tracing for Multi Compare DnD.

Mirrors ``tabs/image_compare/debug.py``:
``IMGSLI_IMAGE_COMPARE_DEBUG`` / ``IMGSLI_IC_DEBUG`` → ``[ic-dnd]`` / ``[ic-debug]``.

Env vars:
    IMGSLI_MULTI_COMPARE_DEBUG=1 — official
    IMGSLI_MC_DEBUG=1            — short alias (same flag)

Tags:
    [mc-dnd]   — drag-enter / move / leave / drop routing, drop-target
                 resolution (path/side/root/swap), internal move-vs-swap,
                 pending duplicate/paste placement lifecycle
    [mc-debug] — generic lifecycle (currently same gate as [mc-dnd])

All helpers emit ``WARNING`` when their explicit env flag is set (visible
without ``--debug``) and ``DEBUG`` when global ``--debug`` is on — hybrid per
gallery fix 2026-08-26. See ``docs/dev/LOGGING.md``.
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")

_DND_FLAGS = ("IMGSLI_MULTI_COMPARE_DEBUG", "IMGSLI_MC_DEBUG")


def _mc_debug_enabled() -> bool:
    return any(_env_flag(flag) for flag in _DND_FLAGS)


def _emit(prefix: str, msg: str, *args, env_flags=_DND_FLAGS, **kwargs) -> None:
    if any(_env_flag(flag) for flag in env_flags):
        logger.warning(prefix + " " + msg, *args, **kwargs)
    else:
        logger.debug(prefix + " " + msg, *args, **kwargs)


def mc_debug_enabled() -> bool:
    return _mc_debug_enabled()


def mc_dnd_debug_enabled() -> bool:
    return _mc_debug_enabled()


def mc_debug(msg: str, *args, **kwargs) -> None:
    if mc_debug_enabled():
        _emit("[mc-debug]", msg, *args, **kwargs)


def mc_dnd_debug(msg: str, *args, **kwargs) -> None:
    if mc_dnd_debug_enabled():
        _emit("[mc-dnd]", msg, *args, **kwargs)
