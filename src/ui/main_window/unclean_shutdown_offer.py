"""Offer a diagnostics report when the PREVIOUS session ended abnormally.

The detector is ``plugins.diagnostics.session_marker`` (a marker file the app
writes at startup and rewrites as clean on a normal exit). This module is only
the startup plumbing: after the window is shown, hand the previous session to the
diagnostics plugin, which decides whether to offer (and whether the user opted
out).

Why a notice and not a modal at boot: the user opened the app to work. The offer
appears once the first paint is done, it describes what the report WOULD carry,
and it collects **nothing** until the button is pressed.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)

#: Long enough that the window is painted and the offer is not the first thing
#: the compositor draws; short enough that a user who came back for the report
#: does not have to hunt for it.
OFFER_DELAY_MS = 1200


def _diagnostics_plugin(window: Any) -> Any | None:
    """The live diagnostics plugin, or ``None`` (never raises on the startup path)."""
    context = getattr(window, "app_context", None)
    coordinator = getattr(context, "plugin_coordinator", None)
    getter = getattr(coordinator, "get_plugin", None)
    if not callable(getter):
        return None
    try:
        return getter("diagnostics")
    except Exception:
        return None


def schedule_unclean_shutdown_offer(window: Any, previous: Any) -> None:
    """Ask the diagnostics plugin to offer a report for *previous* (if any)."""
    if previous is None:
        return

    def _present() -> None:
        plugin = _diagnostics_plugin(window)
        offer = getattr(plugin, "offer_unclean_shutdown", None)
        if not callable(offer):
            logger.debug("unclean-shutdown offer skipped: no diagnostics plugin")
            return
        try:
            offer(previous)
        except Exception:
            logger.exception("unclean-shutdown offer failed")

    try:
        QTimer.singleShot(OFFER_DELAY_MS, _present)
    except Exception:
        logger.exception("unclean-shutdown offer could not be scheduled")


__all__ = ["OFFER_DELAY_MS", "schedule_unclean_shutdown_offer"]
