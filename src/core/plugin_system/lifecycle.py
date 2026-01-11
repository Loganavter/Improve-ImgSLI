from __future__ import annotations

import logging
from typing import Any, Iterable

from core.plugin_system.event_bus import EventBus
from core.plugin_system.plugin import Plugin, PluginState
from core.events import PluginEvent

logger = logging.getLogger("ImproveImgSLI.plugin.lifecycle")

class PluginLifecycleManager:

    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        name = self._plugin_name(plugin)
        if name not in self._plugins:
            self._plugins[name] = plugin

    def register_many(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            self.register(plugin)

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> tuple[Plugin, ...]:
        return tuple(self._plugins.values())

    def initialize_all(self, context: Any) -> None:
        for name, plugin in self._plugins.items():
            self._safe_call(plugin, "initialize", context, name, PluginState.INITIALIZED)

    def activate_all(self) -> None:
        for name, plugin in self._plugins.items():
            self._safe_call(plugin, "activate", None, name, PluginState.ACTIVE)

    def deactivate_all(self) -> None:
        for name, plugin in self._plugins.items():
            self._safe_call(plugin, "deactivate", None, name, PluginState.INACTIVE)

    def shutdown_all(self) -> None:
        for name, plugin in self._plugins.items():
            self._safe_call(plugin, "shutdown", None, name, PluginState.SHUTDOWN)

    def activate(self, name: str) -> None:
        plugin = self.get(name)
        if plugin:
            self._safe_call(plugin, "activate", None, name, PluginState.ACTIVE)

    def deactivate(self, name: str) -> None:
        plugin = self.get(name)
        if plugin:
            self._safe_call(plugin, "deactivate", None, name, PluginState.INACTIVE)

    def shutdown(self, name: str) -> None:
        plugin = self.get(name)
        if plugin:
            self._safe_call(plugin, "shutdown", None, name, PluginState.SHUTDOWN)

    def _safe_call(
        self,
        plugin: Plugin,
        method_name: str,
        context: Any | None,
        plugin_name: str,
        expected_state: PluginState,
    ) -> None:
        method = getattr(plugin, method_name, None)
        if not method:
            return
        try:
            if context is not None:
                method(context)
            else:
                method()
        except Exception as err:  # noqa: BLE001 (logging of exception is intentional)
            logger.exception("Plugin %s failed during %s: %s", plugin_name, method_name, err)
            plugin._set_state(PluginState.ERROR)
            self._emit_event("error", plugin_name, err)
        else:
            if plugin.get_state() == expected_state:
                self._emit_event(method_name, plugin_name)

    def _plugin_name(self, plugin: Plugin) -> str:
        meta = getattr(plugin, "_plugin_meta", {})
        return meta.get("name", plugin.__class__.__name__)

    def _emit_event(self, stage: str, plugin_name: str, payload: Any | None = None) -> None:
        if not self._event_bus:
            return

        event = PluginEvent(plugin_name=plugin_name, stage=stage)
        self._event_bus.emit(event)

    def plugin_name(self, plugin: Plugin) -> str:
        return self._plugin_name(plugin)

