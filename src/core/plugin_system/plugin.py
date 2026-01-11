from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any

class PluginState(Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    INACTIVE = "inactive"
    SHUTDOWN = "shutdown"
    ERROR = "error"

class Plugin(ABC):

    def __init__(self):
        self.context: Any | None = None
        self._state = PluginState.CREATED

    @abstractmethod
    def initialize(self, context: Any) -> None:
        self.context = context
        self._set_state(PluginState.INITIALIZED)

    def activate(self) -> None:
        if self._state in {PluginState.SHUTDOWN, PluginState.ERROR}:
            return
        self._set_state(PluginState.ACTIVE)

    def deactivate(self) -> None:
        if self._state in {PluginState.SHUTDOWN, PluginState.ERROR}:
            return
        self._set_state(PluginState.INACTIVE)

    def shutdown(self) -> None:
        self._set_state(PluginState.SHUTDOWN)

    def get_state(self) -> PluginState:
        return self._state

    def _set_state(self, state: PluginState) -> None:
        self._state = state

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def get_toolbar_actions(self) -> list[Any]:
        return []

    def get_menu_items(self) -> list[Any]:
        return []

    def get_render_entities(self) -> list[Any]:
        return []

