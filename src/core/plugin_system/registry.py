from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Literal

if TYPE_CHECKING:
    from core.bootstrap import ApplicationContext

from core.plugin_system.decorators import get_registered_plugins
from core.plugin_system.discovery_scan import plugin_modules_for_tier
from core.plugin_system.plugin import Plugin
from resources.translations import add_i18n_root

logger = logging.getLogger("ImproveImgSLI.plugin.registry")

DiscoveryTier = Literal["bootstrap", "deferred", "all"]

class PluginRegistry:

    def __init__(self, app_context: ApplicationContext):
        self.app_context = app_context
        self._plugins: dict[str, Plugin] = {}
        self._discovered_tiers: set[str] = set()

    def discover_plugins(
        self, *, tier: DiscoveryTier = "all"
    ) -> Iterable[Plugin]:
        if tier == "all":
            if "all" not in self._discovered_tiers:
                from core.plugin_system.discovery_scan import iter_plugin_entry_points

                for entry in iter_plugin_entry_points():
                    self._import_plugin_module(entry.module_name)
                self._discovered_tiers.add("all")
        else:
            if tier in self._discovered_tiers:
                return ()
            modules = plugin_modules_for_tier(tier)
            for module_name in modules:
                self._import_plugin_module(module_name)
            self._discovered_tiers.add(tier)

        from core.startup_trace import startup_mark

        startup_mark(f"plugins.discover.{tier}")

        created: list[Plugin] = []
        for plugin_cls in get_registered_plugins():
            meta = getattr(plugin_cls, "_plugin_meta", {})
            plugin_name = meta.get("name", plugin_cls.__name__)
            if plugin_name in self._plugins:
                continue
            if tier in ("bootstrap", "deferred"):
                if meta.get("startup_tier", "deferred") != tier:
                    continue
            plugin_instance = plugin_cls()
            self._plugins[plugin_name] = plugin_instance
            created.append(plugin_instance)

        if tier in ("bootstrap", "deferred"):
            created.sort(
                key=lambda p: getattr(p, "_plugin_meta", {}).get("startup_order", 0)
            )

        return created

    def _import_plugin_module(self, module_name: str) -> None:
        try:
            importlib.import_module(module_name)
        except ImportError:
            logger.exception("Failed to import plugin module %s", module_name)
            return
        self._register_i18n_for_module(module_name)

    def _register_i18n_for_module(self, module_name: str) -> None:
        parts = module_name.split(".")
        if len(parts) < 2:
            return
        # plugins.export.plugin -> plugins/export/resources/i18n
        # tabs.image_compare.plugin -> tabs/image_compare/resources/i18n
        # tabs.image_compare.plugins.video_editor.plugin ->
        #   tabs/image_compare/plugins/video_editor/resources/i18n
        if parts[0] == "plugins" and parts[-1] == "plugin":
            pkg_parts = parts[:-1]
        elif parts[0] == "tabs" and parts[-1] == "plugin":
            pkg_parts = parts[:-1]
        else:
            return
        try:
            package = importlib.import_module(".".join(pkg_parts))
        except ImportError:
            return
        pkg_path = Path(package.__path__[0])
        i18n = pkg_path / "resources" / "i18n"
        if i18n.is_dir():
            add_i18n_root(i18n)

    def get_plugin(self, name: str) -> Plugin | None:
        return self._plugins.get(name)

    def all_plugins(self) -> Iterable[Plugin]:
        return tuple(self._plugins.values())

    @property
    def deferred_loaded(self) -> bool:
        return "deferred" in self._discovered_tiers or "all" in self._discovered_tiers
