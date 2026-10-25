from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any
from core.log_names import APP_LOGGER_NAME

logger = logging.getLogger(f"{APP_LOGGER_NAME}.plugin.base")

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
        if self.context is None:
            # Activation requires an initialized context: a plugin that was
            # never initialized (no context) must not go ACTIVE. Log and
            # skip instead of silently entering a half-wired state.
            logger.warning(
                "%s.activate() without initialized context; skipping",
                type(self).__name__,
            )
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
