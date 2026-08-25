"""Centralized main-window / event-bus resolution.

Cross-module review C2 flagged three duplicated ``topLevelWidgets()`` hunts
for ``.presenter -> .event_bus / .main_controller`` (platform.py:83-90,
connections.py:104-109, persistence hunt). This module is the single
sanctioned accessor — all host code must call here instead of re-scanning.

For tabs, prefer ``TabContext`` / ``TabRegistry.get_shared_tab_registry()``
over reaching into the window.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QApplication


def find_main_window() -> Any | None:
    """Return the live ``MainWindow`` instance if one exists.

    Scans ``QApplication.topLevelWidgets()`` looking for an object that has
    a ``presenter`` attribute (the established main-window marker). Returns
    ``None`` when called off the GUI thread before the window exists.
    """
    try:
        app = QApplication.instance()
        if app is None:
            return None
        # Prefer activeWindow first — cheaper than full scan.
        try:
            active = QApplication.activeWindow()
            if active is not None and getattr(active, "presenter", None) is not None:
                return active
        except Exception:
            pass
        for widget in app.topLevelWidgets():
            if getattr(widget, "presenter", None) is not None:
                return widget
    except Exception:
        return None
    return None


def find_event_bus() -> Any | None:
    """Resolve the global ``EventBus`` via the main window.

    Checks ``window.presenter.event_bus`` then ``window.presenter.main_controller.event_bus``
    — the two folk-paths previously duplicated across platform.py and
    persistence helpers.
    """
    window = find_main_window()
    if window is None:
        return None
    presenter = getattr(window, "presenter", None)
    if presenter is None:
        return None
    bus = getattr(presenter, "event_bus", None)
    if bus is not None:
        return bus
    controller = getattr(presenter, "main_controller", None)
    if controller is not None:
        bus = getattr(controller, "event_bus", None)
        if bus is not None:
            return bus
    return None
