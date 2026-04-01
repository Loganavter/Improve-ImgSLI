from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.events import ComparisonUIUpdateEvent, CoreUpdateRequestedEvent

class UIUpdateDispatcher:
    def __init__(self, event_bus: Any | None = None, signal: Any | None = None):
        self._event_bus = event_bus
        self._signal = signal

    def emit(self, components: tuple[str, ...] | list[str] | None = None) -> None:
        payload = tuple(components or ())
        if self._event_bus:
            self._event_bus.emit(ComparisonUIUpdateEvent(components=payload))
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

@dataclass(frozen=True)
class AnalysisRuntime:
    thread_pool: Any | None
    ui_updates: UIUpdateDispatcher
    core_updates: CoreUpdateDispatcher
