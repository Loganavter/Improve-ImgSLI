from typing import Any
from PyQt6.QtCore import QPointF

from core.plugin_system import Plugin, plugin
from core.events import MagnifierAddedEvent, MagnifierRemovedEvent

@plugin(name="magnifier", version="1.0")
class MagnifierPlugin(Plugin):

    def __init__(self):
        super().__init__()
        self.active_id: str | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)

    def add_magnifier(self, magnifier_id: str | None = None, position=None) -> Any:
        if magnifier_id is None:
            magnifier_id = "default"

        self.active_id = magnifier_id

        if self.event_bus:
            self.event_bus.emit(MagnifierAddedEvent(magnifier_id))
        return None

    def set_magnifier_visibility(self, magnifier_id: str | None, visible: bool) -> None:
        pass

    def remove_magnifier(self, magnifier_id: str) -> None:
        if self.event_bus:
            self.event_bus.emit(MagnifierRemovedEvent(magnifier_id))

    def get_ui_components(self) -> dict[str, Any]:
        return {
            "add_magnifier": self.add_magnifier,
        }

