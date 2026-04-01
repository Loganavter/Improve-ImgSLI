from __future__ import annotations

from core.events import CoreUpdateRequestedEvent, SettingsUIModeChangedEvent

class SettingsUpdateNotifier:
    def __init__(self, store, event_bus=None, update_requested_signal=None):
        self.store = store
        self.event_bus = event_bus
        self.update_requested_signal = update_requested_signal

    def emit_state_change(self, scope: str | None = None):
        if scope is None:
            self.store.emit_state_change()
            return
        self.store.emit_state_change(scope)

    def invalidate_render_cache(self):
        self.store.invalidate_render_cache()

    def request_core_update(self):
        if self.event_bus:
            self.event_bus.emit(CoreUpdateRequestedEvent())
            return
        if self.update_requested_signal is not None:
            self.update_requested_signal.emit()

    def emit_ui_mode_changed(self, mode: str):
        if self.event_bus:
            self.event_bus.emit(SettingsUIModeChangedEvent(mode))
