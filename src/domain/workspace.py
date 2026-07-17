from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.store_viewport import ViewportState

_DOCUMENT_SLOT = "document"
_VIEWPORT_SLOT = "viewport"


@dataclass
class WorkspaceSession:
    id: str
    title: str
    session_type: str
    state_slots: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def document(self) -> Any:
        return self.state_slots.get(_DOCUMENT_SLOT)

    @document.setter
    def document(self, value: Any) -> None:
        self.state_slots[_DOCUMENT_SLOT] = value

    @property
    def viewport(self) -> "ViewportState":
        return self.state_slots.get(_VIEWPORT_SLOT)

    @viewport.setter
    def viewport(self, value: "ViewportState") -> None:
        self.state_slots[_VIEWPORT_SLOT] = value


@dataclass
class WorkspaceState:
    sessions: list[WorkspaceSession] = field(default_factory=list)
    active_session_id: str | None = None

    @staticmethod
    def default_title_prefix(session_type: str) -> str:
        """Language-agnostic auto-title, e.g. ``image_compare`` → ``Image Compare``."""
        return session_type.replace("_", " ").title()

    @classmethod
    def is_auto_title(cls, title: str, session_type: str) -> bool:
        """True when ``title`` is still the store-side default (not a user rename).

        Accepts legacy numbered defaults (``Image Compare 2``) so old projects
        still localize as the bare type label.
        """
        prefix = cls.default_title_prefix(session_type)
        if title == prefix:
            return True
        if not title.startswith(f"{prefix} "):
            return False
        return title[len(prefix) + 1 :].isdigit()

    def next_default_title(self, session_type: str) -> str:
        return self.default_title_prefix(session_type)

    @staticmethod
    def new_session_id() -> str:
        return str(uuid.uuid4())
