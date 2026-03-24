from __future__ import annotations

from core.plugin_system.event_bus import EventBus
from core.plugin_system.plugin import Plugin
from core.plugin_system.registry import PluginRegistry
from core.plugin_system.decorators import get_registered_plugins, plugin
from core.plugin_system.settings import PluginSettings, SettingsScope, auto_persist

__all__ = [
    "PluginRegistry",
    "EventBus",
    "Plugin",
    "plugin",
    "get_registered_plugins",
    "PluginSettings",
    "SettingsScope",
    "auto_persist",
]
