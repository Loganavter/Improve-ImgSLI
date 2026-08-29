"""``IMGSLI_IMAGE_COMPARE_DEBUG``-gated tracing for Image Compare DnD.

Mirrors ``tabs/image_gallery/debug.py``:
``IMGSLI_GALLERY_DEBUG`` → ``[gallery-dnd]`` / ``[gallery-debug]``.

Env vars:
    IMGSLI_IMAGE_COMPARE_DEBUG=1 — official
    IMGSLI_IC_DEBUG=1            — short alias (same flag)
    IMGSLI_IC_PREVIEW_DEBUG=1    — preview display / re-render gate ([ic-preview])

Tags:
    [ic-dnd]     — drag-enter / accept / handle_drop routing
    [ic-debug]   — generic lifecycle
    [ic-preview] — preview display gate: when the canvas apply runs, and
                   every reason it is deferred/skipped instead (render_flow.py,
                   loading_pyramid.py, _session_controller.py)

All helpers emit ``WARNING`` when their explicit env flag is set (visible
without ``--debug``) and ``DEBUG`` when global ``--debug`` is on — hybrid per
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


def _emit(prefix: str, msg: str, *args, env_flags=("IMGSLI_IMAGE_COMPARE_DEBUG", "IMGSLI_IC_DEBUG"), **kwargs) -> None:
    if any(_env_flag(flag) for flag in env_flags):
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


def ic_preview_debug_enabled() -> bool:
    return _env_flag("IMGSLI_IC_PREVIEW_DEBUG") or logger.isEnabledFor(logging.DEBUG)


def ic_preview_debug(msg: str, *args, **kwargs) -> None:
    if ic_preview_debug_enabled():
        _emit(
            "[ic-preview]",
            msg,
            *args,
            env_flags=("IMGSLI_IC_PREVIEW_DEBUG",),
            **kwargs,
        )


def ic_preview_source_tier(img, preview, original, state_img) -> str:
    """Human-readable display tier for ``img`` (``[ic-preview]`` payload).

    ``pick_display_with_preview_backing`` / ``pick_display_image`` can hand
    the canvas any of: the unified full-res store (``image_state.image*``),
    the bounded preview ``QImage`` (``document.preview_image*``), or the
    original ``QImage`` (``document.original_image*``). Identity comparison
    -- the tiers are distinct objects, never shared.
    """
    if img is None:
        return "none"
    if img is preview:
        return "preview"
    if img is original:
        return "original"
    if img is state_img:
        return "store"
    return "other"
