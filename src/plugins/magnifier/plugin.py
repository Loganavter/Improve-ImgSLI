from typing import Any

from core.events import MagnifierAddedEvent, MagnifierRemovedEvent
from core.plugin_system import Plugin, plugin
from ui.canvas_features.magnifier import DEFAULT_MAGNIFIER_ID, MagnifierStoreService

@plugin(name="magnifier", version="1.0")
class MagnifierPlugin(Plugin):

    def __init__(self):
        super().__init__()
        self.active_id: str | None = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        self.event_bus = getattr(context, "event_bus", None)
        self.scene_state = (
            MagnifierStoreService(self.store) if self.store is not None else None
        )

    def add_magnifier(self, magnifier_id: str | None = None, position=None) -> Any:
        if magnifier_id is None:
            magnifier_id = self._next_magnifier_id()

        self.active_id = magnifier_id
        if self.scene_state is not None:
            self.scene_state.add_magnifier(magnifier_id=magnifier_id, position=position)

        if self.event_bus:
            self.event_bus.emit(MagnifierAddedEvent(magnifier_id))
        return None

    def _next_magnifier_id(self) -> str:
        models = {}
        if self.scene_state is not None:
            models = {model.id: model for model in self.scene_state.iter_magnifiers()}
        if DEFAULT_MAGNIFIER_ID not in models:
            return DEFAULT_MAGNIFIER_ID
        index = 2
        while f"magnifier-{index}" in models:
            index += 1
        return f"magnifier-{index}"

    def set_magnifier_visibility(self, magnifier_id: str | None, visible: bool) -> None:
        if self.scene_state is not None:
            self.scene_state.set_object_visibility(magnifier_id, visible)

    def remove_magnifier(self, magnifier_id: str) -> None:
        if self.scene_state is not None:
            self.scene_state.remove_object(magnifier_id)
        if self.event_bus:
            self.event_bus.emit(MagnifierRemovedEvent(magnifier_id))

    def get_ui_components(self) -> dict[str, Any]:
        return {
            "add_magnifier": self.add_magnifier,
        }
