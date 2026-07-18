"""Thin host API for main-window startup / runtime / lifecycle.

Main window code should import this module only — not overlay/pages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def resolve_plugin(window: Any) -> Any | None:
    host = getattr(window, "onboarding_host", None)
    if host is not None:
        return host
    ctx = getattr(window, "app_context", None)
    coordinator = getattr(ctx, "plugin_coordinator", None) if ctx is not None else None
    if coordinator is None:
        return None
    return coordinator.get_plugin("onboarding")


def should_present(window: Any) -> bool:
    plugin = resolve_plugin(window)
    if plugin is not None:
        return bool(plugin.should_present())
    settings_manager = getattr(window, "settings_manager", None)
    if settings_manager is None:
        return False
    return bool(settings_manager.is_first_run())


def maybe_present(
    window: Any,
    *,
    on_completed: Callable[[str], None] | None = None,
) -> bool:
    """Mount onboarding into the startup stack when needed. Returns True if shown."""
    plugin = resolve_plugin(window)
    if plugin is None or not plugin.should_present():
        return False
    plugin.present(window, on_completed=on_completed)
    return True


def is_active(window: Any) -> bool:
    plugin = resolve_plugin(window)
    return bool(plugin is not None and plugin.is_active())


def sync_geometry(window: Any) -> None:
    plugin = resolve_plugin(window)
    if plugin is not None:
        plugin.sync_geometry()


def prepare_after_show(window: Any) -> None:
    plugin = resolve_plugin(window)
    if plugin is not None:
        plugin.prepare_after_show()
