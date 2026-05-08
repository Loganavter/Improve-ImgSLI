from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class FrameSnapshot:
    timestamp: float
    viewport_state: Any
    settings_state: Any
    image1_path: str | None
    image2_path: str | None
    name1: str | None
    name2: str | None

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "viewport_state": self.viewport_state,
            "settings_state": self.settings_state,
            "image1_path": self.image1_path,
            "image2_path": self.image2_path,
            "name1": self.name1,
            "name2": self.name2,
        }
