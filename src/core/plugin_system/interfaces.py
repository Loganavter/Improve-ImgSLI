from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class IControllablePlugin(ABC):

    @abstractmethod
    def get_controller(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def handle_command(self, command: str, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

class IUIPlugin(ABC):

    def get_ui_components(self) -> dict[str, Any]:
        return {}

    def register_toolbar(self, toolbar_manager: Any) -> None:
        return None

    def register_menu(self, menu_manager: Any) -> None:
        return None

class IServicePlugin(ABC):

    @abstractmethod
    def get_service(self) -> Any:
        raise NotImplementedError

    def provides_capability(self, capability: str) -> bool:
        return False

class IRenderPlugin(ABC):

    @abstractmethod
    def get_render_entities(self) -> list[Any]:
        raise NotImplementedError

    def render_layer(self, renderer: Any) -> None:
        return None

