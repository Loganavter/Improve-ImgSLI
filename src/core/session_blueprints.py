from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass(frozen=True)
class SessionSlotBlueprint:
    name: str
    factory: Callable[[], Any] | None = None
    default: Any = None

@dataclass(frozen=True)
class SessionResourceBlueprint:
    namespace: str
    entries: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class SessionBlueprint:
    session_type: str
    plugin_name: str
    title: str | None = None
    state_slots: tuple[SessionSlotBlueprint, ...] = ()
    resource_namespaces: tuple[SessionResourceBlueprint, ...] = ()
    metadata_defaults: dict[str, Any] = field(default_factory=dict)

    def resolved_title(self) -> str | None:
        return self.title.strip() if isinstance(self.title, str) and self.title.strip() else None
