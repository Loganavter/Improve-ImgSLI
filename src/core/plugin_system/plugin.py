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

    def _set_state(self, state: PluginState) -> None:
        self._state = state
