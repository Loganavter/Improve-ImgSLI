from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from shared.keyframing.adapters_base import ToolDescriptor

@dataclass(frozen=True)
class FrameSnapshot:
    timestamp: float
    viewport_state: Any
    settings_state: Any
    image1_path: str | None = None
    image2_path: str | None = None
    name1: str | None = None
    name2: str | None = None

    def to_state_payload(self) -> dict[str, Any]:
        return {
            "viewport_state": self.viewport_state,
            "settings_state": self.settings_state,
            "image1_path": self.image1_path,
            "image2_path": self.image2_path,
            "name1": self.name1,
            "name2": self.name2,
        }

class KeyframeToolAdapter(Protocol):
    adapter_id: str

    def describe_tools(
        self,
        snapshot: FrameSnapshot | None = None,
    ) -> tuple[ToolDescriptor, ...]:
        ...

    def read_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
    ) -> Mapping[str, Mapping[str, Any]]:
        ...

    def apply_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
        values_by_track_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
        ...
