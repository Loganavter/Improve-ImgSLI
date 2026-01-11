from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

class PluginUIRegistry:
    def __init__(self):
        self._actions: dict[str, dict[str, Callable[..., Any]]] = defaultdict(dict)

    def register_action(self, plugin_name: str, action_id: str, callback: Callable[..., Any]) -> None:
        self._actions[plugin_name][action_id] = callback

    def unregister_plugin(self, plugin_name: str) -> None:
        self._actions.pop(plugin_name, None)

    def get_action(self, action_id: str) -> Callable[..., Any] | None:
        for plugin_actions in self._actions.values():
            if action_id in plugin_actions:
                return plugin_actions[action_id]
        return None

def get_plugin_name(plugin: Any) -> str:
    meta = getattr(plugin, "_plugin_meta", {})
    return meta.get("name", plugin.__class__.__name__)

