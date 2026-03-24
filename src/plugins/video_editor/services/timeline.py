from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

@dataclass(frozen=True)
class ChannelKeyframe:
    timestamp: float
    value: Any
    interpolation: str = "linear"

@dataclass
class TimelineChannel:
    id: str
    label: str
    kind: str = "scalar"
    interpolate_values: bool = True
    source_track_id: str | None = None
    accent_color: str | None = None
    keyframes: list[ChannelKeyframe] = field(default_factory=list)

    def clear(self) -> None:
        self.keyframes.clear()

    def add_keyframe(
        self,
        timestamp: float,
        value: Any,
        *,
        interpolation: str = "linear",
        equals: Callable[[Any, Any], bool],
        clone: Callable[[Any], Any],
    ) -> bool:
        if self.keyframes and equals(self.keyframes[-1].value, value):
            return False
        self.keyframes.append(
            ChannelKeyframe(
                timestamp=float(timestamp),
                value=clone(value),
                interpolation=interpolation,
            )
        )
        return True

@dataclass
class TimelineTrack:
    id: str
    label: str
    kind: str = "scalar"
    enabled: bool = True
    channels: dict[str, TimelineChannel] = field(default_factory=dict)

    def clear(self) -> None:
        for channel in self.channels.values():
            channel.clear()

    def ensure_channel(
        self,
        channel_id: str,
        *,
        label: str | None = None,
        kind: str = "scalar",
        interpolate_values: bool = True,
        source_track_id: str | None = None,
        accent_color: str | None = None,
    ) -> TimelineChannel:
        channel = self.channels.get(channel_id)
        if channel is None:
            channel = TimelineChannel(
                id=channel_id,
                label=label or channel_id,
                kind=kind,
                interpolate_values=interpolate_values,
                source_track_id=source_track_id or self.id,
                accent_color=accent_color,
            )
            self.channels[channel_id] = channel
        elif source_track_id and channel.source_track_id != source_track_id:
            channel.source_track_id = source_track_id
        return channel

@dataclass
class TimelineGroup:
    id: str
    label: str
    kind: str = "group"
    tracks: dict[str, TimelineTrack] = field(default_factory=dict)

    def clear(self) -> None:
        for track in self.tracks.values():
            track.clear()

    def ensure_track(
        self,
        track_id: str,
        *,
        label: str | None = None,
        kind: str = "scalar",
    ) -> TimelineTrack:
        track = self.tracks.get(track_id)
        if track is None:
            track = TimelineTrack(id=track_id, label=label or track_id, kind=kind)
            self.tracks[track_id] = track
        return track

class TimelineModel:
    def __init__(self):
        self.sample_timestamps: list[float] = []
        self.groups: dict[str, TimelineGroup] = {}

    def clear(self) -> None:
        self.sample_timestamps.clear()
        for group in self.groups.values():
            group.clear()

    def ensure_group(
        self,
        group_id: str,
        *,
        label: str | None = None,
        kind: str = "group",
    ) -> TimelineGroup:
        group = self.groups.get(group_id)
        if group is None:
            group = TimelineGroup(id=group_id, label=label or group_id, kind=kind)
            self.groups[group_id] = group
        return group

    def ensure_track(
        self,
        group_id: str,
        track_id: str,
        *,
        group_label: str | None = None,
        track_label: str | None = None,
        track_kind: str = "scalar",
    ) -> TimelineTrack:
        group = self.ensure_group(group_id, label=group_label)
        return group.ensure_track(track_id, label=track_label, kind=track_kind)

    def iter_tracks(self) -> list[TimelineTrack]:
        tracks: list[TimelineTrack] = []
        for group in self.groups.values():
            tracks.extend(group.tracks.values())
        return tracks

    def get_duration(self) -> float:
        if not self.sample_timestamps:
            return 0.0
        return float(self.sample_timestamps[-1])

    def __bool__(self) -> bool:
        return bool(self.sample_timestamps)
