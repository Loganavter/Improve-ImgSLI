from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FrameSnapshot:
    timestamp: float
    viewport_state: Any
    settings_state: Any
    sources: tuple[str | None, ...]
    names: tuple[str | None, ...]

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "viewport_state": self.viewport_state,
            "settings_state": self.settings_state,
            "sources": self.sources,
            "names": self.names,
        }
