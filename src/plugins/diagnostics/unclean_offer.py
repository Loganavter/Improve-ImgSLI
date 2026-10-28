"""The decision half of the unclean-shutdown report: offer it, or respect an opt-out.

Split from ``plugin.py`` (file-size policy) and from ``offer.py`` (the dialog):
this module owns *whether* and *what*, the dialog owns *how it looks*. Every
function takes the plugin, the repo's "thin owner + plain helper" shape.

Nothing is collected until the user presses "Create report": the failure payload
is assembled at that moment from the previous session's marker (log tail + fault
dump), so a user who dismisses the offer costs nothing.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def settings_store(plugin: Any) -> Any | None:
    """The live QSettings store (the manager, or the raw store as a fallback)."""
    store = getattr(plugin, "store", None)
    for candidate in (
        getattr(store, "settings_manager", None),
        getattr(store, "settings", None),
    ):
        if candidate is not None:
            return candidate
    return None


def offer(plugin: Any, previous: Any) -> bool:
    """Offer a report for *previous* unless the user opted out. Never raises."""
    try:
        from . import session_marker
    except Exception:
        return False
    if session_marker.offer_is_suppressed(settings_store(plugin)):
        return False
    try:
        plugin._pending_failure = session_marker.failure_payload(previous)
    except Exception:
        return False
    try:
        plugin.breadcrumbs.record("crash", "unclean previous session")
    except Exception:
        pass
    schedule(plugin, previous)
    return True


def schedule(plugin: Any, previous: Any) -> None:
    """Show the offer on the GUI thread, after the current event-loop turn."""
    try:
        QTimer.singleShot(0, lambda: show(plugin, previous))
    except Exception:
        logger.exception("diagnostics: could not schedule the unclean-shutdown offer")


def show(plugin: Any, previous: Any) -> None:
    """Open the offer dialog (one at a time)."""
    try:
        from .offer import show_unclean_shutdown_dialog

        existing = getattr(plugin, "_offer", None)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
        plugin._offer = show_unclean_shutdown_dialog(
            summary(previous),
            parent=plugin._parent_widget(),
            on_report=lambda: build_pending_report(plugin),
            on_suppress=lambda: suppress(plugin),
        )
    except Exception:
        logger.exception("diagnostics: failed to offer the unclean-shutdown report")


def summary(previous: Any) -> str:
    """One honest line about what the report will carry (no secret values)."""
    parts = [f"started {getattr(previous, 'started_at', '') or 'unknown'}"]
    if getattr(previous, "log_file", ""):
        parts.append("the end of the previous log")
    if getattr(previous, "fault_file", ""):
        parts.append("the crash traceback, if one was written")
    return "; ".join(parts)


def build_pending_report(plugin: Any) -> None:
    """Build the report from the pending failure (one shot) and show it."""
    failure = getattr(plugin, "_pending_failure", None)
    plugin._pending_failure = None
    try:
        plugin.create_report(failure)
    except Exception:
        logger.exception("diagnostics: failed to build the unclean-shutdown report")


def suppress(plugin: Any) -> None:
    """Persist "don't ask again"."""
    from . import session_marker

    session_marker.suppress_offer(settings_store(plugin))


__all__ = [
    "build_pending_report",
    "offer",
    "schedule",
    "settings_store",
    "show",
    "summary",
    "suppress",
]
