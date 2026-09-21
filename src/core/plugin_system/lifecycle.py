from __future__ import annotations

import logging
from typing import Any

from core.plugin_system.event_bus import EventBus
from core.plugin_system.plugin import Plugin, PluginState

logger = logging.getLogger("ImproveImgSLI.plugin.lifecycle")

class PluginLifecycleManager:

    def __init__(self, event_bus: EventBus | None = None):
        self._event_bus = event_bus
        self._plugins: dict[str, Plugin] = {}

    def register(self, plugin: Plugin) -> None:
        name = self._plugin_name(plugin)
        if name in self._plugins:
            # Duplicate isolation: keep the first registration so a second
            # plugin with the same name cannot steal the slot — but say so
            # loudly instead of silently dropping it.
            logger.warning(
                "Plugin '%s' (%s) already registered; keeping the first "
                "registration and ignoring %s",
                name,
                type(self._plugins[name]).__name__,
                type(plugin).__name__,
            )
            return
        self._plugins[name] = plugin

    def get(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> tuple[Plugin, ...]:
        return tuple(self._plugins.values())

    def initialize_all(self, context: Any) -> None:
        for name, plugin in self._plugins.items():
            self.initialize_one(plugin, context)

    def initialize_one(self, plugin: Plugin, context: Any) -> None:
        name = self._plugin_name(plugin)
        self._safe_call(
            plugin, "initialize", context, name, PluginState.INITIALIZED
        )

    def activate_all(self) -> None:
        for name, plugin in self._plugins.items():
            self.activate_one(plugin)

    def activate_one(self, plugin: Plugin) -> None:
        name = self._plugin_name(plugin)
        self._safe_call(plugin, "activate", None, name, PluginState.ACTIVE)

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
            logger.exception(
                "Plugin %s failed during %s: %s", plugin_name, method_name, err
            )
            plugin._set_state(PluginState.ERROR)
            return
        # Post-condition: the lifecycle call must leave the plugin in the
        # expected state. Base Plugin methods set it themselves; an override
        # that skips super() (or an early-return skip like activate() without
        # context) leaves a stale state — warn instead of crashing startup.
        actual = getattr(plugin, "_state", None)
        if actual is not expected_state:
            logger.warning(
                "Plugin %s after %s in state %s, expected %s",
                plugin_name,
                method_name,
                getattr(actual, "value", actual),
                expected_state.value,
            )

    def _plugin_name(self, plugin: Plugin) -> str:
        meta = getattr(plugin, "_plugin_meta", {})
        return meta.get("name", plugin.__class__.__name__)

    def plugin_name(self, plugin: Plugin) -> str:
        return self._plugin_name(plugin)
