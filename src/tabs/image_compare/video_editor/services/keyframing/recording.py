from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from tabs.image_compare.video_editor.services.keyframing.adapters.base import KeyframeToolAdapter
from tabs.image_compare.video_editor.services.keyframing.composition.defaults import (
    build_default_keyframe_adapters,
)
from tabs.image_compare.video_editor.services.keyframing.composition.registry import (
    KeyframeAdapterRegistry,
)
from tabs.image_compare.video_editor.services.keyframing.engine.validation import (
    validate_append_timestamp,
)
from tabs.image_compare.video_editor.services.keyframing.engine.values import (
    _prefers_continuous_curve,
    add_value_to_track,
    assemble_value_from_track,
    clone_value,
    evaluate_track_channels,
    frozen_value,
    values_close,
)
from tabs.image_compare.video_editor.services.keyframing.types import FrameSnapshot
from tabs.image_compare.video_editor.services.timeline import (
    ChannelKeyframe,
    TimelineChannel,
    TimelineModel,
    TimelineTrack,
)

CORE_VIEWPORT_TRACK_ID = "__snapshot.viewport_state"
CORE_SETTINGS_TRACK_ID = "__snapshot.settings_state"


def _source_track_id(index: int) -> str:
    return f"__snapshot.source[{index}]"


def _name_track_id(index: int) -> str:
    return f"__snapshot.name[{index}]"


CORE_SOURCE_COUNT = 2

@dataclass(frozen=True)
class Keyframe:
    timestamp: float
    value: Any
    interpolation: str = "linear"

class KeyframeTrack:
    def __init__(self, track: TimelineTrack):
        self._track = track

    @property
    def keyframes(self) -> list[Keyframe]:
        channel = self._primary_channel()
        if channel is None:
            return []
        return [
            Keyframe(
                timestamp=item.timestamp,
                value=item.value,
                interpolation=item.interpolation,
            )
            for item in channel.keyframes
        ]

    @property
    def channels(self) -> dict[str, TimelineChannel]:
        return self._track.channels

    @property
    def label(self) -> str:
        return self._track.label

    def clear(self) -> None:
        self._track.clear()

    def add_keyframe(self, timestamp: float, value: Any, *, fps: int = 60) -> bool:
        return add_value_to_track(self._track, timestamp, value, fps=fps)

    def evaluate_at(self, timestamp: float) -> Any:
        return assemble_value_from_track(self._track, timestamp)

    def _primary_channel(self) -> TimelineChannel | None:
        return self._track.channels.get("value") or next(
            iter(self._track.channels.values()), None
        )

class KeyframedRecording:
    def __init__(
        self,
        fps: int = 60,
        extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
    ) -> None:
        self.fps = max(1, int(fps))
        self.timeline = TimelineModel()
        self.tracks: dict[str, KeyframeTrack] = {}
        self.extra_adapters = tuple(extra_adapters)
        self.registry = KeyframeAdapterRegistry(
            build_default_keyframe_adapters(self.extra_adapters)
        )
        self._core_track_ids = {
            CORE_VIEWPORT_TRACK_ID,
            CORE_SETTINGS_TRACK_ID,
            *(_source_track_id(i) for i in range(CORE_SOURCE_COUNT)),
            *(_name_track_id(i) for i in range(CORE_SOURCE_COUNT)),
        }
        self._last_hold_fingerprints: dict[str, Any] = {}

    @property
    def sample_timestamps(self) -> list[float]:
        return self.timeline.sample_timestamps

    @property
    def keyframes(self) -> dict[str, list[ChannelKeyframe]]:
        payload: dict[str, list[ChannelKeyframe]] = {}
        for name, wrapper in self.tracks.items():
            channel = wrapper.channels.get("value") or next(
                iter(wrapper.channels.values()), None
            )
            payload[name] = list(channel.keyframes) if channel is not None else []
        return payload

    @classmethod
    def from_snapshots(
        cls,
        snapshots: list[FrameSnapshot],
        fps: int = 60,
        extra_adapters: tuple[KeyframeToolAdapter, ...] = (),
    ) -> "KeyframedRecording":
        recording = cls(fps=fps, extra_adapters=extra_adapters)
        for snapshot in snapshots:
            recording.append(snapshot)
        recording.finalize_tail_keyframes()
        return recording

    def clear(self) -> None:
        self.timeline.clear()
        self._last_hold_fingerprints.clear()

    def append(self, snapshot: FrameSnapshot) -> None:
        timestamp = self._quantize_timestamp(snapshot.timestamp)
        if self.timeline.sample_timestamps and math.isclose(
            float(self.timeline.sample_timestamps[-1]),
            float(timestamp),
            abs_tol=1e-9,
        ):
            self.timeline.sample_timestamps[-1] = timestamp
        else:
            validate_append_timestamp(timestamp, self.timeline.sample_timestamps)
            self.timeline.sample_timestamps.append(timestamp)

        for registered in self.registry.describe_snapshot(snapshot):
            self._ensure_tool_tracks(registered.descriptor)

        values_by_tool_id = self.registry.read_snapshot_values(snapshot)
        for _tool_id, tool_values in values_by_tool_id.items():
            for track_id, value in tool_values.items():
                wrapper = self.tracks[track_id]
                if track_id in self._core_track_ids:
                    self._append_cached_hold_keyframe(
                        track_name=track_id,
                        timestamp=timestamp,
                        value=value["value"],
                        fingerprint=frozen_value(value["value"]),
                    )
                else:
                    wrapper.add_keyframe(timestamp, value, fps=self.fps)

    def evaluate_at(self, timestamp: float) -> FrameSnapshot:
        if not self.timeline.sample_timestamps:
            raise ValueError("Recording is empty")
        clamped_time = max(0.0, min(float(timestamp), self.get_duration()))
        snapshot = FrameSnapshot(
            timestamp=clamped_time,
            viewport_state=self.tracks[CORE_VIEWPORT_TRACK_ID].evaluate_at(clamped_time),
            settings_state=self.tracks[CORE_SETTINGS_TRACK_ID].evaluate_at(clamped_time),
            sources=tuple(
                self.tracks[_source_track_id(i)].evaluate_at(clamped_time)
                for i in range(CORE_SOURCE_COUNT)
            ),
            names=tuple(
                self.tracks[_name_track_id(i)].evaluate_at(clamped_time)
                for i in range(CORE_SOURCE_COUNT)
            ),
        )
        self.registry.apply_snapshot_values(snapshot, self._evaluate_tool_values(clamped_time))
        return snapshot

    def materialize_snapshots(self) -> list[FrameSnapshot]:
        return [self.evaluate_at(timestamp) for timestamp in self.timeline.sample_timestamps]

    def get_duration(self) -> float:
        return self.timeline.get_duration()

    def get_keyframe_count(self) -> int:
        return sum(
            len(channel.keyframes)
            for track in self.timeline.iter_tracks()
            for channel in track.channels.values()
        )

    def get_track(self, name: str) -> TimelineTrack | None:
        wrapper = self.tracks.get(name)
        return wrapper._track if wrapper is not None else None

    def finalize_tail_keyframes(self) -> None:
        if not self.timeline.sample_timestamps:
            return

        end_timestamp = float(self.timeline.sample_timestamps[-1])
        for track in self.timeline.iter_tracks():
            for channel in track.channels.values():
                if not channel.keyframes:
                    continue
                last = channel.keyframes[-1]
                if math.isclose(last.timestamp, end_timestamp, abs_tol=1e-9):
                    continue
                channel.keyframes.append(
                    ChannelKeyframe(
                        timestamp=end_timestamp,
                        value=clone_value(last.value),
                        interpolation=last.interpolation,
                    )
                )

    def apply_cut_markers(self, timestamps: list[float]) -> None:
        if not timestamps:
            return
        for cut_timestamp in timestamps:
            cut_timestamp = float(cut_timestamp)
            for track in self.timeline.iter_tracks():
                for channel in track.channels.values():
                    if not channel.interpolate_values or len(channel.keyframes) < 2:
                        continue
                    for index in range(1, len(channel.keyframes)):
                        current = channel.keyframes[index]
                        previous = channel.keyframes[index - 1]
                        if not math.isclose(
                            float(current.timestamp), cut_timestamp, abs_tol=1e-9
                        ):
                            continue
                        if values_close(previous.value, current.value, kind=channel.kind):
                            break
                        channel.keyframes[index] = ChannelKeyframe(
                            timestamp=current.timestamp,
                            value=clone_value(current.value),
                            interpolation="cut",
                        )
                        break

    def __bool__(self) -> bool:
        return bool(self.timeline)

    def _ensure_tool_tracks(self, tool_descriptor) -> None:
        for track_descriptor in tool_descriptor.tracks:
            timeline_track = self.timeline.ensure_track(
                group_id=tool_descriptor.group_id,
                track_id=track_descriptor.id,
                group_label=tool_descriptor.group_label,
                track_label=track_descriptor.label,
                track_kind=track_descriptor.kind,
                group_accent_color=tool_descriptor.accent_color,
                track_accent_color=track_descriptor.accent_color,
                group_metadata={
                    "tool_id": tool_descriptor.id,
                    "tool_type": tool_descriptor.tool_type,
                    "subclass_id": tool_descriptor.subclass_id,
                    "subclass_label": tool_descriptor.subclass_label,
                    **dict(tool_descriptor.metadata),
                },
                track_metadata=dict(track_descriptor.metadata),
            )
            for channel in track_descriptor.channels:
                timeline_track.ensure_channel(
                    channel.id,
                    label=channel.label,
                    kind=channel.kind,
                    interpolate_values=(
                        channel.interpolate_values
                        if channel.interpolate_values is not None
                        else channel.kind not in {"bool", "enum", "color"}
                    ),
                    source_track_id=track_descriptor.id,
                    accent_color=channel.accent_color,
                    prefer_continuous_curve=_prefers_continuous_curve(track_descriptor.id),
                )
            self.tracks[track_descriptor.id] = KeyframeTrack(timeline_track)

    def _append_cached_hold_keyframe(
        self,
        *,
        track_name: str,
        timestamp: float,
        value: Any,
        fingerprint: Any,
    ) -> None:
        channel = self.tracks[track_name].channels["value"]
        keyframes = channel.keyframes
        timestamp = float(timestamp)
        new_keyframe = ChannelKeyframe(
            timestamp=timestamp,
            value=clone_value(value),
            interpolation="hold",
        )

        if not keyframes:
            keyframes.append(new_keyframe)
            self._last_hold_fingerprints[track_name] = fingerprint
            return
        if math.isclose(keyframes[-1].timestamp, timestamp, abs_tol=1e-9):
            keyframes[-1] = new_keyframe
            self._last_hold_fingerprints[track_name] = fingerprint
            return
        if self._last_hold_fingerprints.get(track_name) == fingerprint:
            return
        keyframes.append(new_keyframe)
        self._last_hold_fingerprints[track_name] = fingerprint

    def _evaluate_tool_values(
        self,
        timestamp: float,
    ) -> dict[str, dict[str, dict[str, Any]]]:
        payload: dict[str, dict[str, dict[str, Any]]] = {}
        for registered in self.registry.iter_tools():
            tool_values: dict[str, dict[str, Any]] = {}
            for track in registered.descriptor.tracks:
                if track.id in self._core_track_ids:
                    continue
                tool_values[track.id] = evaluate_track_channels(
                    self.get_track(track.id),
                    timestamp,
                )
            payload[registered.descriptor.id] = tool_values
        return payload

    def _quantize_timestamp(self, timestamp: float) -> float:
        frame = int(round(max(0.0, float(timestamp)) * self.fps))
        return float(frame) / float(self.fps)
