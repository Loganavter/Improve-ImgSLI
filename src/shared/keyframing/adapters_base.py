from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ChannelDescriptor:
    id: str
    label: str
    kind: str
    accent_color: str | None = None
    interpolate_values: bool | None = None

@dataclass(frozen=True)
class TrackDescriptor:
    id: str
    label: str
    kind: str
    channels: tuple[ChannelDescriptor, ...]
    accent_color: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ToolDescriptor:
    id: str
    tool_type: str
    label: str
    group_id: str
    group_label: str
    subclass_id: str | None = None
    subclass_label: str | None = None
    accent_color: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    tracks: tuple[TrackDescriptor, ...] = ()
