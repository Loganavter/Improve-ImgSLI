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