from __future__ import annotations

from dataclasses import dataclass

from core.events import CoreUIComponentsUpdateEvent

ComparisonUIUpdateEvent = CoreUIComponentsUpdateEvent


@dataclass(frozen=True)
class ComparisonErrorEvent:
    error: str


@dataclass(frozen=True)
class ComparisonUpdateRequestedEvent:
    pass
