from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.store_document import DocumentModel
    from core.store_viewport import ViewportState

@dataclass
class WorkspaceSession:
    id: str
    title: str
    session_type: str
    document: "DocumentModel"
    viewport: "ViewportState"
    state_slots: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class WorkspaceState:
    sessions: list[WorkspaceSession] = field(default_factory=list)
    active_session_id: str | None = None
    _title_counters: dict[str, int] = field(default_factory=dict)

    def next_default_title(self, session_type: str) -> str:
        next_index = self._title_counters.get(session_type, 0) + 1
        self._title_counters[session_type] = next_index
        suffix = session_type.replace("_", " ").title()
        return f"{suffix} {next_index}"

    @staticmethod
    def new_session_id() -> str:
        return str(uuid.uuid4())
