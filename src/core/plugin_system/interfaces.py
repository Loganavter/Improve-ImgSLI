from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.session_blueprints import SessionBlueprint

class IControllablePlugin(ABC):

    @abstractmethod
    def get_controller(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

class IServicePlugin(ABC):

    @abstractmethod
    def get_service(self) -> Any:
        raise NotImplementedError
class ISessionPlugin(ABC):

    @abstractmethod
    def get_session_blueprints(self) -> tuple[SessionBlueprint, ...]:
        raise NotImplementedError
