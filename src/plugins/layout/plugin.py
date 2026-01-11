from typing import Any
from core.plugin_system import Plugin, plugin
from core.events import SettingsUIModeChangedEvent
from .manager import LayoutManager

@plugin(name="layout", version="1.0")
class LayoutPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.manager = None
        self.store = None

    def initialize(self, context: Any) -> None:
        super().initialize(context)
        self.store = getattr(context, "store", None)
        event_bus = getattr(context, "event_bus", None)

        if event_bus:

            event_bus.subscribe(SettingsUIModeChangedEvent, self._on_ui_mode_changed_event)

    def _on_ui_mode_changed_event(self, event: SettingsUIModeChangedEvent):
        self.on_ui_mode_changed(event.ui_mode)

    def setup_ui_reference(self, ui):
        self.manager = LayoutManager(ui)

        if self.store:
            current_mode = getattr(self.store.settings, 'ui_mode', 'beginner')
            self.manager.apply_mode(current_mode)

    def on_ui_mode_changed(self, mode_name: str):
        if self.manager:
            self.manager.apply_mode(mode_name)

