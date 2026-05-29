from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext

from core.plugin_system.decorators import get_registered_plugins
from core.plugin_system.plugin import Plugin
from resources.translations import add_i18n_root

class PluginRegistry:

    def __init__(self, app_context: ApplicationContext):
        self.app_context = app_context
        self._plugins: dict[str, Plugin] = {}

    def discover_plugins(self) -> Iterable[Plugin]:
        self._scan_package("plugins")
        self._scan_package("tabs")

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

    def _scan_package(self, package_name: str) -> None:
        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return

        pkg_path = Path(package.__path__[0])

        for finder, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
            pkg_i18n = pkg_path / module_name / "resources" / "i18n"
            if pkg_i18n.is_dir():
                add_i18n_root(pkg_i18n)

            module = None
            try:
                module = importlib.import_module(f"{package_name}.{module_name}.plugin")
            except ModuleNotFoundError as exc:
                if exc.name != f"{package_name}.{module_name}.plugin":
                    raise
            if module is None:
                importlib.import_module(f"{package_name}.{module_name}")

    def get_plugin(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> Iterable[Plugin]:
        return tuple(self._plugins.values())
