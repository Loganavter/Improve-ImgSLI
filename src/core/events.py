from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, runtime_checkable

@runtime_checkable
class Event(Protocol):
    pass

T = TypeVar("T", bound=Event)

@dataclass(frozen=True)
class CoreUpdateRequestedEvent:
    pass

@dataclass(frozen=True)
class CoreErrorOccurredEvent:
    error: str
    details: str | None = None

@dataclass(frozen=True)
class CoreUIComponentsUpdateEvent:
    components: tuple = ()

@dataclass(frozen=True)
class PluginEvent:
    plugin_name: str
    stage: str

@dataclass(frozen=True)
class WorkspaceSessionCreatedEvent:
    session_id: str
    session_type: str

@dataclass(frozen=True)
class WorkspaceSessionClosedEvent:
    session_id: str
    session_type: str

@dataclass(frozen=True)
class WorkspaceSessionActivatedEvent:
    session_id: str
    session_type: str
    previous_session_id: str | None = None
