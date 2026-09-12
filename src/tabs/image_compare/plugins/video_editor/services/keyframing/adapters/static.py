from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from shared.keyframing.adapters_base import (
    ToolDescriptor,
    TrackDescriptor,
)
from tabs.image_compare.plugins.video_editor.services.keyframing.types import (
    FrameSnapshot,
    KeyframeToolAdapter,
)

@dataclass(frozen=True)
class StaticTrackBinding:
    descriptor: TrackDescriptor
    reader: Callable[[FrameSnapshot], Mapping[str, Any]]
    writer: Callable[[FrameSnapshot, Mapping[str, Any]], None]

@dataclass(frozen=True)
class StaticToolBinding:
    descriptor: ToolDescriptor
    tracks: tuple[StaticTrackBinding, ...]

class StaticToolAdapter(KeyframeToolAdapter):
    def __init__(
        self,
        adapter_id: str,
        tools: tuple[StaticToolBinding, ...],
    ) -> None:
        self.adapter_id = adapter_id
        self._tools = tools
        self._tools_by_id = {tool.descriptor.id: tool for tool in tools}
        self._bindings_by_tool_and_track = {
            (tool.descriptor.id, binding.descriptor.id): binding
            for tool in tools
            for binding in tool.tracks
        }

    def describe_tools(
        self,
        snapshot: FrameSnapshot | None = None,
    ) -> tuple[ToolDescriptor, ...]:
        return tuple(tool.descriptor for tool in self._tools)

    def read_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
    ) -> Mapping[str, Mapping[str, Any]]:
        tool_binding = self._tools_by_id[tool.id]
        return {
            binding.descriptor.id: dict(binding.reader(snapshot))
            for binding in tool_binding.tracks
        }

    def apply_tool_values(
        self,
        snapshot: FrameSnapshot,
        tool: ToolDescriptor,
        values_by_track_id: Mapping[str, Mapping[str, Any]],
    ) -> None:
        for track_id, channel_values in values_by_track_id.items():
            binding = self._bindings_by_tool_and_track.get((tool.id, track_id))
            if binding is None:
                continue
            binding.writer(snapshot, channel_values)
