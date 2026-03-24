from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from core.plugin_system.event_bus import EventBus
from core.plugin_system.interfaces import IControllablePlugin, ISessionPlugin
from core.plugin_system.lifecycle import PluginLifecycleManager
from core.plugin_system.plugin import Plugin
from core.session_blueprints import SessionBlueprint

class PluginCoordinator:
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus
        self.lifecycle = PluginLifecycleManager(event_bus)
        self._capability_map: dict[str, list[str]] = defaultdict(list)
        self._session_blueprints: dict[str, SessionBlueprint] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        plugin_name = self.lifecycle.plugin_name(plugin)
        self.lifecycle.register(plugin)
        self._register_capabilities(plugin_name, plugin)
        self._register_session_blueprints(plugin_name, plugin)

    def register_plugins(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            self.register_plugin(plugin)

    def initialize(self, context: Any) -> None:
        self.lifecycle.initialize_all(context)
        self.lifecycle.activate_all()

    def get_plugin(self, name: str) -> Plugin | None:
        return self.lifecycle.get(name)

    def iter_plugins(self) -> tuple[Plugin, ...]:
        return self.lifecycle.all_plugins()

    def get_plugin_by_capability(self, capability: str) -> Plugin | None:
        plugin_names = self._capability_map.get(capability, [])
        for name in plugin_names:
            plugin = self.get_plugin(name)
            if plugin:
                return plugin
        return None

    def execute_command(
        self, plugin_name: str, command: str, *args: Any, **kwargs: Any
    ) -> Any:
        plugin = self.get_plugin(plugin_name)
        if not plugin:
            raise ValueError(f"Plugin '{plugin_name}' is not registered")

        if isinstance(plugin, IControllablePlugin):
            return plugin.handle_command(command, *args, **kwargs)

        target = getattr(plugin, command, None)
        if callable(target):
            return target(*args, **kwargs)

        raise AttributeError(f"Plugin '{plugin_name}' has no command '{command}'")

    def list_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        return tuple(self._session_blueprints.values())

    def get_session_blueprint(self, session_type: str) -> SessionBlueprint | None:
        return self._session_blueprints.get(session_type)

    def create_session(
        self,
        store: Any,
        session_type: str,
        *,
        activate: bool = True,
        title: str | None = None,
    ) -> Any:
        blueprint = self.get_session_blueprint(session_type)
        if blueprint is None:
            raise ValueError(f"Session type '{session_type}' is not registered")
        return store.create_workspace_session(
            title=title,
            session_type=session_type,
            activate=activate,
            blueprint=blueprint,
        )

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

    def _register_session_blueprints(self, plugin_name: str, plugin: Plugin) -> None:
        if not isinstance(plugin, ISessionPlugin):
            return
        for blueprint in plugin.get_session_blueprints():
            session_type = blueprint.session_type
            if session_type in self._session_blueprints:
                raise ValueError(
                    f"Session type '{session_type}' is already registered"
                )
            if blueprint.plugin_name != plugin_name:
                blueprint = SessionBlueprint(
                    session_type=blueprint.session_type,
                    plugin_name=plugin_name,
                    title=blueprint.title,
                    state_slots=blueprint.state_slots,
                    resource_namespaces=blueprint.resource_namespaces,
                    metadata_defaults=dict(blueprint.metadata_defaults),
                )
            self._session_blueprints[session_type] = blueprint

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
