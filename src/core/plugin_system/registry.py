from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Iterable

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext
from core.plugin_system.decorators import get_registered_plugins
from core.plugin_system.plugin import Plugin

class PluginRegistry:

    def __init__(self, app_context: ApplicationContext):
        self.app_context = app_context
        self._plugins: dict[str, Plugin] = {}

    def discover_plugins(self) -> Iterable[Plugin]:
        try:
            import plugins
        except ImportError:
            return []

        for finder, module_name, is_pkg in pkgutil.iter_modules(plugins.__path__):
            importlib.import_module(f"plugins.{module_name}")

        created: list[Plugin] = []
        for plugin_cls in get_registered_plugins():
            meta = getattr(plugin_cls, "_plugin_meta", {})
            plugin_name = meta.get("name", plugin_cls.__name__)
            if plugin_name in self._plugins:
                continue
            plugin_instance = plugin_cls()
            self._plugins[plugin_name] = plugin_instance
            created.append(plugin_instance)

        return created

    def get_plugin(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> Iterable[Plugin]:
        return tuple(self._plugins.values())

