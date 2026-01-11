from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from core.plugin_system.event_bus import EventBus
from core.plugin_system.interfaces import IControllablePlugin
from core.plugin_system.lifecycle import PluginLifecycleManager
from core.plugin_system.plugin import Plugin

class PluginCoordinator:
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus
        self.lifecycle = PluginLifecycleManager(event_bus)
        self._capability_map: dict[str, list[str]] = defaultdict(list)

    def register_plugin(self, plugin: Plugin) -> None:
        plugin_name = self.lifecycle.plugin_name(plugin)
        self.lifecycle.register(plugin)
        self._register_capabilities(plugin_name, plugin)

    def register_plugins(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            self.register_plugin(plugin)

    def initialize(self, context: Any) -> None:
        self.lifecycle.initialize_all(context)
        self.lifecycle.activate_all()

    def get_plugin(self, name: str) -> Plugin | None:
        return self.lifecycle.get(name)

    def get_plugin_by_capability(self, capability: str) -> Plugin | None:
        plugin_names = self._capability_map.get(capability, [])
        for name in plugin_names:
            plugin = self.get_plugin(name)
            if plugin:
                return plugin
        return None

    def execute_command(self, plugin_name: str, command: str, *args: Any, **kwargs: Any) -> Any:
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_name}' is not registered")

        if isinstance(plugin, IControllablePlugin):
            return plugin.handle_command(command, *args, **kwargs)

        target = getattr(plugin, command, None)
        if callable(target):
            return target(*args, **kwargs)

        raise AttributeError(f"Plugin '{plugin_name}' has no command '{command}'")

    def broadcast_event(self, event: str, payload: Any | None = None) -> None:
        if self.event_bus:
            if payload is None:
                self.event_bus.emit(event)
            else:
                self.event_bus.emit(event, payload)

    def _register_capabilities(self, plugin_name: str, plugin: Plugin) -> None:
        capabilities = self._gather_capabilities(plugin)
        for capability in capabilities:
            self._capability_map[capability].append(plugin_name)

    def _gather_capabilities(self, plugin: Plugin) -> tuple[str, ...]:
        capabilities = []
        meta = getattr(plugin, "_plugin_meta", {})
        declared = meta.get("capabilities")
        if isinstance(declared, str):
            capabilities.append(declared)
        elif isinstance(declared, Iterable):
            capabilities.extend(declared)

        attr_caps = getattr(plugin, "capabilities", None)
        if isinstance(attr_caps, str):
            capabilities.append(attr_caps)
        elif isinstance(attr_caps, Iterable):
            capabilities.extend(attr_caps)

        return tuple(dict.fromkeys(str(cap) for cap in capabilities if cap))

