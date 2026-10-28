"""Dialog plumbing for a diagnostics report: schedule it, show it, find a parent.

Split out of ``plugin.py`` (file-size policy): the plugin builds a report on
whatever thread noticed the failure, and these three functions are the only place
that touches Qt to put it on screen. Keeping them here means the plugin's own
body stays the lifecycle + report assembly.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import QTimer

from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(APP_LOGGER_NAME)


def parent_widget() -> Any | None:
    """The active top-level window, or ``None`` before there is one."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        return app.activeWindow() if app is not None else None
    except Exception:
        return None


def schedule(plugin: Any, diagnostics: Any) -> None:
    """Show *diagnostics* on the GUI thread (never blocking the calling thread)."""
    presenter = getattr(plugin, "_presenter", None)
    if presenter is not None:
        try:
            presenter.request(diagnostics)
            return
        except Exception:
            pass
    try:
        QTimer.singleShot(0, lambda: show(plugin, diagnostics))
    except Exception:
        logger.exception("diagnostics: could not schedule the report dialog")


def show(plugin: Any, diagnostics: Any) -> None:
    """Open the report dialog, replacing any older one."""
    try:
        from .dialog import show_diagnostics_dialog

        existing = getattr(plugin, "_dialog", None)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
        plugin._dialog = show_diagnostics_dialog(diagnostics, parent=parent_widget())
    except Exception:
        logger.exception("diagnostics: failed to show report dialog")


__all__ = ["parent_widget", "schedule", "show"]
