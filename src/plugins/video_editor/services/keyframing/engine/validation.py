from __future__ import annotations

import math
from typing import Any, Mapping

from plugins.video_editor.services.keyframing.adapters.base import ToolDescriptor
from plugins.video_editor.services.keyframing.engine.errors import (
    KeyframingValidationError,
)

def validate_tool_descriptors(
    tools: tuple[ToolDescriptor, ...],
    *,
    known_tool_ids: set[str],
    known_track_ids: set[str],
) -> None:
    local_tool_ids: set[str] = set()
    local_track_ids: set[str] = set()
    for tool in tools:
        if tool.id in known_tool_ids or tool.id in local_tool_ids:
            raise KeyframingValidationError(
                "duplicate_tool_id",
                message=f"Duplicate keyframe tool id '{tool.id}'",
                tool_id=tool.id,
            )
        local_tool_ids.add(tool.id)

        for track in tool.tracks:
            if track.id in known_track_ids or track.id in local_track_ids:
                raise KeyframingValidationError(
                    "duplicate_track_id",
                    message=f"Duplicate keyframe track id '{track.id}'",
                    tool_id=tool.id,
                    track_id=track.id,
                )
            local_track_ids.add(track.id)

            seen_channels: set[str] = set()
            for channel in track.channels:
                if channel.id in seen_channels:
                    raise KeyframingValidationError(
                        "duplicate_channel_id",
                        message=(
                            f"Duplicate channel id '{channel.id}' inside track '{track.id}'"
                        ),
                        tool_id=tool.id,
                        track_id=track.id,
                        channel_id=channel.id,
                    )
                seen_channels.add(channel.id)

def validate_tool_values(
    tool: ToolDescriptor,
    values_by_track_id: Mapping[str, Mapping[str, Any]],
) -> None:
    track_map = {track.id: track for track in tool.tracks}
    for track_id, channel_values in values_by_track_id.items():
        track = track_map.get(track_id)
        if track is None:
            raise KeyframingValidationError(
                "unknown_track_id",
                message=f"Adapter produced values for unknown track '{track_id}'",
                tool_id=tool.id,
                track_id=track_id,
            )

        expected_channels = {channel.id: channel for channel in track.channels}
        for channel_id, value in channel_values.items():
            descriptor = expected_channels.get(channel_id)
            if descriptor is None:
                raise KeyframingValidationError(
                    "unknown_channel_id",
                    message=(
                        f"Adapter produced values for unknown channel '{channel_id}' "
                        f"in track '{track_id}'"
                    ),
                    tool_id=tool.id,
                    track_id=track_id,
                    channel_id=channel_id,
                )
            _validate_channel_value(tool.id, track_id, channel_id, descriptor.kind, value)

def validate_append_timestamp(timestamp: float, sample_timestamps: list[float]) -> None:
    if sample_timestamps and math.isclose(
        float(sample_timestamps[-1]),
        float(timestamp),
        abs_tol=1e-9,
    ):
        raise KeyframingValidationError(
            "duplicate_sample_timestamp",
            message=f"Duplicate sample timestamp '{timestamp}' is not allowed",
            timestamp=float(timestamp),
        )

def _validate_channel_value(
    tool_id: str,
    track_id: str,
    channel_id: str,
    kind: str,
    value: Any,
) -> None:
    if kind == "bool":
        if not isinstance(value, bool):
            raise _value_error(tool_id, track_id, channel_id, kind, value)
        return
    if kind == "enum":
        if not isinstance(value, str) and value is not None:
            raise _value_error(tool_id, track_id, channel_id, kind, value)
        return
    if kind in {"scalar", "color"}:
        if value is None or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise _value_error(tool_id, track_id, channel_id, kind, value)
        return
    if kind == "state":
        return

def _value_error(
    tool_id: str,
    track_id: str,
    channel_id: str,
    kind: str,
    value: Any,
) -> KeyframingValidationError:
    return KeyframingValidationError(
        "invalid_channel_value",
        message=(
            f"Invalid value for {tool_id}/{track_id}/{channel_id}: "
            f"expected '{kind}', got {type(value).__name__}"
        ),
        tool_id=tool_id,
        track_id=track_id,
        channel_id=channel_id,
    )
