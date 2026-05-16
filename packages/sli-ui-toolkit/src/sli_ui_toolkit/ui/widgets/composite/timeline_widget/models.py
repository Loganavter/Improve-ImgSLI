from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class TimelineKeyframe(Protocol):
    @property
    def timestamp(self) -> float: ...
    @property
    def value(self) -> Any: ...
    @property
    def interpolation(self) -> str: ...

@runtime_checkable
class TimelineChannel(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def keyframes(self) -> list: ...
    @property
    def interpolate_values(self) -> bool: ...

@runtime_checkable
class TimelineTrack(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def channels(self) -> dict[str, Any]: ...

@runtime_checkable
class TimelineGroup(Protocol):
    @property
    def label(self) -> str: ...
    @property
    def tracks(self) -> dict[str, Any]: ...

@runtime_checkable
class TimelineModel(Protocol):
    @property
    def groups(self) -> dict[str, Any]: ...
    @property
    def sample_timestamps(self) -> list: ...
    def get_duration(self) -> float: ...

@dataclass
class TimelineCallbacks:
    """Callback hooks to customize timeline behavior without hardcoding app logic."""

    should_show_track: Any = None
    """(track) -> bool. If None, shows tracks with changed channels."""

    visible_channels: Any = None
    """(track) -> list[channel]. If None, returns channels with changes."""

    is_track_active: Any = None
    """(track, channel, timestamp) -> bool. If None, always True."""

    localize_token: Any = None
    """(token: str) -> str. If None, returns token as-is."""

    localize_value: Any = None
    """(value) -> str. If None, uses default formatting."""

    prominent_track_ids: set[str] = field(default_factory=set)
    """Track IDs that are shown only when they have changes."""
