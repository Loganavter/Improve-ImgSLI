from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

@dataclass(frozen=True, slots=True)
class StateSliceRegistration:
    key: str
    reducer: Any | None = None
    initial_state_factory: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class CommandRegistration:
    command_id: str
    handler: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class QueryRegistration:
    query_id: str
    handler: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class SceneContributionRegistration:
    contribution_id: str
    builder: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class UIContributionRegistration:
    contribution_id: str
    builder: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class PluginDefinition:
    id: str
    state_slices: tuple[StateSliceRegistration, ...] = ()
    commands: tuple[CommandRegistration, ...] = ()
    queries: tuple[QueryRegistration, ...] = ()
    scene_contributions: tuple[SceneContributionRegistration, ...] = ()
    ui_contributions: tuple[UIContributionRegistration, ...] = ()
    translation_namespaces: tuple[str, ...] = ()
    resource_namespaces: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

class PluginDefinitionRegistry:
    """Collects generic plugin contribution definitions without feature knowledge."""

    def __init__(self) -> None:
        self._definitions: dict[str, PluginDefinition] = {}

    def register(self, definition: PluginDefinition) -> None:
        plugin_id = str(definition.id or "").strip()
        if not plugin_id:
            raise ValueError("PluginDefinition.id must be a non-empty string")
        if plugin_id in self._definitions:
            raise ValueError(f"Plugin definition '{plugin_id}' is already registered")
        self._definitions[plugin_id] = definition

    def register_plugin(self, plugin: Any) -> None:
        provider = getattr(plugin, "get_definition", None)
        if not callable(provider):
            return
        definition = provider()
        if definition is None:
            return
        if not isinstance(definition, PluginDefinition):
            raise TypeError(
                f"{plugin.__class__.__name__}.get_definition() must return "
                "PluginDefinition | None"
            )
        self.register(definition)

    def register_plugins(self, plugins: Iterable[Any]) -> None:
        for plugin in plugins:
            self.register_plugin(plugin)

    def get(self, plugin_id: str) -> PluginDefinition | None:
        return self._definitions.get(plugin_id)

    def all_definitions(self) -> tuple[PluginDefinition, ...]:
        return tuple(self._definitions.values())

    def iter_state_slices(self) -> tuple[StateSliceRegistration, ...]:
        return tuple(
            slice_registration
            for definition in self._definitions.values()
            for slice_registration in definition.state_slices
        )

    def iter_commands(self) -> tuple[CommandRegistration, ...]:
        return tuple(
            command
            for definition in self._definitions.values()
            for command in definition.commands
        )

    def iter_queries(self) -> tuple[QueryRegistration, ...]:
        return tuple(
            query
            for definition in self._definitions.values()
            for query in definition.queries
        )

    def iter_scene_contributions(self) -> tuple[SceneContributionRegistration, ...]:
        return tuple(
            contribution
            for definition in self._definitions.values()
            for contribution in definition.scene_contributions
        )

    def iter_ui_contributions(self) -> tuple[UIContributionRegistration, ...]:
        return tuple(
            contribution
            for definition in self._definitions.values()
            for contribution in definition.ui_contributions
        )
