from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from shared.keyframing.adapters_base import ToolDescriptor
from tabs.image_compare.plugins.video_editor.services.keyframing.engine.validation import (
    validate_tool_descriptors,
    validate_tool_values,
)
from tabs.image_compare.plugins.video_editor.services.keyframing.types import (
    FrameSnapshot,
    KeyframeToolAdapter,
)

@dataclass(frozen=True)
class RegisteredTool:
    adapter: KeyframeToolAdapter
    descriptor: ToolDescriptor

class KeyframeAdapterRegistry:
    def __init__(self, adapters: tuple[KeyframeToolAdapter, ...] = ()) -> None:
        self._adapters = tuple(adapters)
        self._registered_tools: dict[str, RegisteredTool] = {}
        self._tool_id_by_track_id: dict[str, str] = {}

    @property
    def adapters(self) -> tuple[KeyframeToolAdapter, ...]:
        return self._adapters

    def describe_snapshot(
        self,
        snapshot: FrameSnapshot | None = None,
    ) -> tuple[RegisteredTool, ...]:
        pending: list[RegisteredTool] = []
        known_tool_ids = set(self._registered_tools.keys())
        known_track_ids = set(self._tool_id_by_track_id.keys())
        for adapter in self._adapters:
            tools = tuple(adapter.describe_tools(snapshot))
            unseen_tools = tuple(tool for tool in tools if tool.id not in known_tool_ids)
            if not unseen_tools:
                continue
            validate_tool_descriptors(
                unseen_tools,
                known_tool_ids=known_tool_ids,
                known_track_ids=known_track_ids,
            )
            for tool in unseen_tools:
                registered = RegisteredTool(adapter=adapter, descriptor=tool)
                self._registered_tools[tool.id] = registered
                known_tool_ids.add(tool.id)
                for track in tool.tracks:
                    self._tool_id_by_track_id[track.id] = tool.id
                    known_track_ids.add(track.id)
                pending.append(registered)
        return tuple(pending)

    def iter_tools(self) -> tuple[RegisteredTool, ...]:
        return tuple(self._registered_tools.values())

    def read_snapshot_values(
        self,
        snapshot: FrameSnapshot,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        self.describe_snapshot(snapshot)
        payload: dict[str, dict[str, dict[str, Any]]] = {}
        for registered in self.iter_tools():
            values = registered.adapter.read_tool_values(snapshot, registered.descriptor)
            normalized = {
                track_id: dict(channel_values)
                for track_id, channel_values in values.items()
            }
            validate_tool_values(registered.descriptor, normalized)
            payload[registered.descriptor.id] = normalized
        return payload

    def apply_snapshot_values(
        self,
        snapshot: FrameSnapshot,
        values_by_tool_id: Mapping[str, Mapping[str, Mapping[str, Any]]],
    ) -> None:
        for tool_id, tool_values in values_by_tool_id.items():
            registered = self._registered_tools.get(tool_id)
            if registered is None:
                continue
            registered.adapter.apply_tool_values(
                snapshot,
                registered.descriptor,
                tool_values,
            )
