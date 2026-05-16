"""App-specific callbacks for the generic TimelineWidget."""

from __future__ import annotations

import math

from resources.translations import get_current_language, tr

_PROMINENT_TRACK_IDS = {
    "splitter.main.position",
}

_TOKEN_KEYS = {
    "ON": "common.switch.switch_on",
    "OFF": "common.switch.switch_off",
    "NEAREST": "magnifier.nearest_neighbor",
    "BILINEAR": "magnifier.bilinear",
    "BICUBIC": "magnifier.bicubic",
    "LANCZOS": "magnifier.lanczos",
    "EWA_LANCZOS": "magnifier.ewa_lanczos",
    "LEFT": "common.position.left",
    "CENTER": "common.position.center",
    "RIGHT": "common.position.right",
    "RGB": "video.rgb",
    "R": "video.red",
    "G": "video.green",
    "B": "video.blue",
    "L": "video.luminance",
    "HIGHLIGHT": "video.highlight",
    "GRAYSCALE": "video.grayscale",
    "EDGES": "video.edge_comparison",
    "SSIM": "video.ssim_map",
}

def _channel_has_changes(channel) -> bool:
    if len(channel.keyframes) < 2:
        return False
    first = channel.keyframes[0].value
    for keyframe in channel.keyframes[1:]:
        if keyframe.value != first:
            return True
    return False

def _find_track_in_model(timeline_model, track_id: str):
    if timeline_model is None:
        return None
    for group in timeline_model.groups.values():
        track = group.tracks.get(track_id)
        if track is not None:
            return track
    return None

def _evaluate_channel_at_timestamp(channel, timestamp: float):
    keyframes = channel.keyframes
    if not keyframes:
        return None
    if timestamp <= keyframes[0].timestamp:
        return keyframes[0].value
    previous = keyframes[0]
    for i in range(1, len(keyframes)):
        current = keyframes[i]
        if timestamp <= current.timestamp:
            if math.isclose(float(timestamp), float(current.timestamp), abs_tol=1e-9):
                while i + 1 < len(keyframes) and math.isclose(
                    float(keyframes[i + 1].timestamp),
                    float(current.timestamp),
                    abs_tol=1e-9,
                ):
                    previous = current
                    i += 1
                    current = keyframes[i]
                if math.isclose(
                    float(previous.timestamp),
                    float(current.timestamp),
                    abs_tol=1e-9,
                ):
                    return current.value
            return previous.value
        previous = current
    return keyframes[-1].value

def app_should_show_track(track) -> bool:
    if track.id.startswith("__") or track.kind in {"state", "source", "label"}:
        return False

    if track.id in _PROMINENT_TRACK_IDS:
        return any(_channel_has_changes(ch) for ch in track.channels.values())

    if track.kind == "mask3":
        return any(_channel_has_changes(ch) for ch in track.channels.values())

    if track.kind == "color":
        return any(_channel_has_changes(ch) for ch in track.channels.values())

    if track.kind in {"bool", "enum"}:
        return any(_channel_has_changes(ch) for ch in track.channels.values())

    return any(_channel_has_changes(ch) for ch in track.channels.values())

def app_visible_channels(track):
    if track.kind == "color":
        channels = [ch for ch in track.channels.values() if ch.keyframes]
        if not channels:
            return []
        changed = next((ch for ch in channels if _channel_has_changes(ch)), None)
        return [changed or channels[0]]
    channels = []
    for ch in track.channels.values():
        if not ch.keyframes:
            continue
        if _channel_has_changes(ch):
            channels.append(ch)
    return channels

def app_is_track_active(track, channel, timestamp: float) -> bool:
    if channel.kind == "bool":
        value = _evaluate_channel_at_timestamp(channel, timestamp)
        return bool(value)

    if channel.kind == "enum":
        value = _evaluate_channel_at_timestamp(channel, timestamp)
        if track.id == "comparison.diff_mode":
            return str(value).lower() != "off"
        if track.id == "comparison.channel_view_mode":
            return str(value).upper() != "RGB"
        return bool(value)

    if track.id.startswith("magnifier.default.") and track.id != "magnifier.default.enabled":

        return True

    return True

def app_localize_token(token: str) -> str:
    normalized = str(token).strip()
    if not normalized:
        return normalized
    key = _TOKEN_KEYS.get(normalized.upper())
    if key is None:
        return normalized
    translated = tr(key, get_current_language())
    return translated if translated != key else normalized

def app_localize_value(value) -> str:
    if isinstance(value, bool):
        return app_localize_token("ON" if value else "OFF")
    if isinstance(value, float):
        return f"{value:.2f}"
    if isinstance(value, str):
        if ";" in value:
            parts = [app_localize_token(part) for part in value.split(";") if part.strip()]
            return ";".join(parts) if parts else value
        return app_localize_token(value)
    return str(value)
