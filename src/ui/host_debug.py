"""Env-gated tracing for noisy host-UI subsystems.

Follows the unique-prefix recipe from ``docs/dev/LOGGING.md`` (and the
canonical ``sli_ui_toolkit`` conventions): each noisy stream gets its OWN
``IMGSLI_*_DEBUG`` env flag, checked via ``shared.debug_flags.env_flag``, and
every line carries a unique bracketed prefix. With the flag unset the stream
is completely silent — even when the global level is DEBUG. This is the
documented "do not wire a noisy subsystem's debug stream to the global
``debug_mode_enabled`` switch" rule: one log file must not become white
noise just because the persisted setting turned DEBUG on.

Hybrid emit (same as ``tabs/image_gallery/debug.py`` and
``tabs/image_compare/debug.py``): when the explicit flag IS set the line is
emitted at ``WARNING`` so it is visible without ``--debug``; when the flag is
unset nothing is emitted at all. WARNING here is a visibility device for a
deliberately requested trace, not a claim that something is wrong.

Streams / flags / prefixes:

    IMGSLI_TRANSIENT_DEBUG     -> [transient], [transient-close]
    IMGSLI_CTX_MENU_DEBUG      -> [ctx-menu]
    IMGSLI_WORKSPACE_DEBUG     -> [workspace-transition]
    IMGSLI_LAYOUT_DEBUG        -> [layout-tree]
    IMGSLI_STARTUP_DEBUG       -> [startup]
    IMGSLI_RHI_PRIMER_DEBUG    -> [rhi-primer]
    IMGSLI_SCROLL_VALUE_DEBUG  -> [scroll-value]

Keyboard-navigation traces live in ``core/nav_debug.py`` (they reuse the
pre-existing ``UI_NAV_DEBUG`` flag owned by ``events/router.py`` — one flag
for the whole nav firehose, never a fork).

Usage:
    from ui.host_debug import ctx_menu_debug
    ctx_menu_debug("open key=%r surface=%s", key, surface)
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")


def _emit(prefix: str, flag: str, msg: str, *args, **kwargs) -> None:
    """Emit ``prefix + msg`` only when ``flag`` is set (at WARNING)."""
    if _env_flag(flag):
        logger.warning(prefix + " " + msg, *args, **kwargs)


# --- transient UI (flyout close sweeps + lazy service resolution) ---------


def transient_debug_enabled() -> bool:
    return _env_flag("IMGSLI_TRANSIENT_DEBUG")


def transient_debug(msg: str, *args, **kwargs) -> None:
    _emit("[transient]", "IMGSLI_TRANSIENT_DEBUG", msg, *args, **kwargs)


def transient_close_debug(msg: str, *args, **kwargs) -> None:
    _emit("[transient-close]", "IMGSLI_TRANSIENT_DEBUG", msg, *args, **kwargs)


# --- context menus --------------------------------------------------------


def ctx_menu_debug_enabled() -> bool:
    return _env_flag("IMGSLI_CTX_MENU_DEBUG")


def ctx_menu_debug(msg: str, *args, **kwargs) -> None:
    _emit("[ctx-menu]", "IMGSLI_CTX_MENU_DEBUG", msg, *args, **kwargs)


# --- workspace tab transitions -------------------------------------------


def workspace_transition_debug_enabled() -> bool:
    return _env_flag("IMGSLI_WORKSPACE_DEBUG")


def workspace_transition_debug(msg: str, *args, **kwargs) -> None:
    _emit("[workspace-transition]", "IMGSLI_WORKSPACE_DEBUG", msg, *args, **kwargs)


# --- main-window layout tree dump ----------------------------------------


def layout_tree_debug_enabled() -> bool:
    return _env_flag("IMGSLI_LAYOUT_DEBUG")


def layout_tree_debug(msg: str, *args, **kwargs) -> None:
    _emit("[layout-tree]", "IMGSLI_LAYOUT_DEBUG", msg, *args, **kwargs)


# --- main-window startup pipeline ----------------------------------------


def startup_debug_enabled() -> bool:
    return _env_flag("IMGSLI_STARTUP_DEBUG")


def startup_debug(msg: str, *args, **kwargs) -> None:
    _emit("[startup]", "IMGSLI_STARTUP_DEBUG", msg, *args, **kwargs)


# --- RHI surface primer ---------------------------------------------------


def rhi_primer_debug_enabled() -> bool:
    return _env_flag("IMGSLI_RHI_PRIMER_DEBUG")


def rhi_primer_debug(msg: str, *args, **kwargs) -> None:
    _emit("[rhi-primer]", "IMGSLI_RHI_PRIMER_DEBUG", msg, *args, **kwargs)


# --- scroll-value control (fires on every wheel tick / key press) ---------


def scroll_value_debug_enabled() -> bool:
    return _env_flag("IMGSLI_SCROLL_VALUE_DEBUG")


def scroll_value_debug(msg: str, *args, **kwargs) -> None:
    _emit("[scroll-value]", "IMGSLI_SCROLL_VALUE_DEBUG", msg, *args, **kwargs)
