"""``UI_NAV_DEBUG``-gated tracing for host-shell keyboard navigation.

Reuses the pre-existing ``UI_NAV_DEBUG`` env var already honored by
``events/router.py`` / ``events/app_event_handler.py`` for the same
keyboard-navigation firehose — one flag for the whole nav stream, never a
fork. The router sets a sub-logger level from the flag; here the sections
call an env-gated emitter (same unique-prefix recipe as
``ui/host_debug.py``), so the section traces are silent unless the flag is
set even when the global level is DEBUG.

Prefixes (embedded by callers):
    [nav-titlebar] / [nav-tabstrip] / [nav-picker] — app-shell section
        registration (``core/app_shell_navigation.py``).
    [nav-card] / [nav-tab] — per-key section routing
        (``core/navigation_sections.py``).

Usage:
    from core.nav_debug import nav_debug
    nav_debug("[nav-card] navigate key=%s widget=%s", key, label)
"""

from __future__ import annotations

import logging

from shared.debug_flags import env_flag as _env_flag

logger = logging.getLogger("ImproveImgSLI")

_FLAG = "UI_NAV_DEBUG"


def nav_debug_enabled() -> bool:
    return _env_flag(_FLAG)


def nav_debug(msg: str, *args, **kwargs) -> None:
    """Emit ``msg`` (already carrying its bracketed prefix) when the flag is set."""
    if _env_flag(_FLAG):
        logger.debug(msg, *args, **kwargs)
