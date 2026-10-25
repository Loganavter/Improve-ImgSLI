from __future__ import annotations

import logging
from typing import Any, Iterable

from core.plugin_system.event_bus import EventBus
from core.plugin_system.interfaces import IControllablePlugin, ISessionPlugin
from core.plugin_system.lifecycle import PluginLifecycleManager
from core.plugin_system.plugin import Plugin
from core.session_blueprints import SessionBlueprint
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(f"{APP_LOGGER_NAME}.plugin.coordinator")

class PluginCoordinator:
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus
        self.lifecycle = PluginLifecycleManager(event_bus)
        self._session_blueprints: dict[str, SessionBlueprint] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        plugin_name = self.lifecycle.plugin_name(plugin)
        self.lifecycle.register(plugin)
        try:
            self._register_session_blueprints(plugin_name, plugin)
        except Exception:
            # A duplicate session_type (or any blueprint error) is isolated
            # to the offending plugin; registration of the rest continues.
            logger.exception(
                "Plugin %s supplied unusable session blueprints; skipping them",
                plugin_name,
            )

    def register_plugins(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            try:
                self.register_plugin(plugin)
            except Exception:
                # Per-plugin containment: one bad plugin must not abort
                # registration of the remaining plugins.
                plugin_name = self.lifecycle.plugin_name(plugin)
                logger.exception(
                    "Failed to register plugin %s; skipping", plugin_name
                )
                continue

    def initialize(self, context: Any) -> None:
        self.lifecycle.initialize_all(context)
        self.lifecycle.activate_all()

    def register_and_start(
        self, plugins: Iterable[Plugin], context: Any
    ) -> tuple[str, ...]:
        """Register, initialize, and activate plugins not yet in the lifecycle."""
        started: list[str] = []
        for plugin in plugins:
            plugin_name = self.lifecycle.plugin_name(plugin)
            if self.lifecycle.get(plugin_name) is not None:
                continue
            try:
                self.register_plugin(plugin)
                self.lifecycle.initialize_one(plugin, context)
                self.lifecycle.activate_one(plugin)
            except Exception:
                logger.exception(
                    "Failed to start plugin %s; skipping", plugin_name
                )
                continue
            started.append(plugin_name)
        return tuple(started)

    def get_plugin(self, name: str) -> Plugin | None:
        return self.lifecycle.get(name)

    def execute_command(
        self, plugin_name: str, command: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Dispatch a command string to a plugin.

        Trust boundary: commands originate from in-app code (menu actions,
        main-window handlers, other plugins) — never from untrusted input
        such as files, network, or the clipboard. ``command`` is therefore
        treated as developer-controlled. Dunder/private attribute access
        is still rejected so a typo cannot reach internals; non-controllable
        plugins additionally expose only public callables.
        """
        if command.startswith("_"):
            raise AttributeError(
                f"Plugin '{plugin_name}' has no command '{command}'"
            )
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

    def _register_session_blueprints(self, plugin_name: str, plugin: Plugin) -> None:
        if not isinstance(plugin, ISessionPlugin):
            return
        for blueprint in plugin.get_session_blueprints():
            session_type = blueprint.session_type
            if session_type in self._session_blueprints:
                # Isolated duplicate: keep the first registration so one
                # misbehaving plugin cannot steal or break another plugin's
                # session type; the offender is skipped with a warning.
                logger.warning(
                    "Session type '%s' from plugin '%s' is already registered; "
                    "keeping the first registration",
                    session_type,
                    plugin_name,
                )
                continue
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
