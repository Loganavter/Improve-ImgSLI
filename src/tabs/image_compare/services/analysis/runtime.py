from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from core.events import CoreUIComponentsUpdateEvent, CoreUpdateRequestedEvent

class UIUpdateDispatcher:
    def __init__(self, event_bus: Any | None = None, signal: Any | None = None):
        self._event_bus = event_bus
        self._signal = signal

    def emit(self, components: tuple[str, ...] | list[str] | None = None) -> None:
        payload = tuple(components or ())
        if self._event_bus:
            self._event_bus.emit(CoreUIComponentsUpdateEvent(components=payload))
        elif self._signal is not None:
            self._signal.emit(list(payload))

class CoreUpdateDispatcher:
    def __init__(self, event_bus: Any | None = None, signal: Any | None = None):
        self._event_bus = event_bus
        self._signal = signal

    def emit(self) -> None:
        if self._event_bus:
            self._event_bus.emit(CoreUpdateRequestedEvent())
        elif self._signal is not None:
            self._signal.emit()

@dataclass
class AnalysisRuntime:
    thread_pool: Any | None
    ui_updates: UIUpdateDispatcher
    core_updates: CoreUpdateDispatcher
    toast_manager_getter: Callable[[], Any | None] | None = None

    def get_toast_manager(self) -> Any | None:
        if self.toast_manager_getter is None:
            return None
        try:
            return self.toast_manager_getter()
        except Exception:
            return None
