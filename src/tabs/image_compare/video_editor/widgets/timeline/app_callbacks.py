"""Generic timeline callbacks that delegate tab-specific semantics to tabs.

Tab-owned track ids, token translations, and is_track_active branches are
supplied by tabs through `TabRegistry.create_service("video_timeline_semantics")`.
This module only implements truly generic channel/change tracking.
"""

from __future__ import annotations

import math

from resources.translations import get_current_language, tr

_GENERIC_TOKEN_KEYS = {
    "ON": "common.switch.switch_on",
    "OFF": "common.switch.switch_off",
}


def _collect_semantics() -> tuple:
    from tabs.registry import TabRegistry

    registry = TabRegistry()
    registry.discover()
    return registry.create_services_all("video_timeline_semantics")


def _get_semantics() -> tuple:
    global _CACHED_SEMANTICS
    if _CACHED_SEMANTICS is None:
        try:
            _CACHED_SEMANTICS = _collect_semantics()
        except Exception:
            _CACHED_SEMANTICS = ()
    return _CACHED_SEMANTICS


_CACHED_SEMANTICS: tuple | None = None


def get_prominent_track_ids() -> set[str]:
    ids: set[str] = set()
    for s in _get_semantics():
        ids.update(getattr(s, "prominent_track_ids", ()))
    return ids


def _channel_has_changes(channel) -> bool:
    if len(channel.keyframes) < 2:
        return False
    first = channel.keyframes[0].value
    for keyframe in channel.keyframes[1:]:
        if keyframe.value != first:
            return True
    return False


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
    if track.id in get_prominent_track_ids():
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
        for semantics in _get_semantics():
            hook = getattr(semantics, "is_track_active", None)
            if hook is None:
                continue
            result = hook(track, channel, value)
            if result is not None:
                return bool(result)
        return bool(value)

    for semantics in _get_semantics():
        hook = getattr(semantics, "is_track_active", None)
        if hook is None:
            continue
        result = hook(track, channel, None)
        if result is not None:
            return bool(result)
    return True


def _lookup_token_key(token: str) -> str | None:
    key = _GENERIC_TOKEN_KEYS.get(token)
    if key is not None:
        return key
    for semantics in _get_semantics():
        keys = getattr(semantics, "token_translation_keys", None) or {}
        key = keys.get(token)
        if key is not None:
            return key
    return None


def app_localize_token(token: str) -> str:
    normalized = str(token).strip()
    if not normalized:
        return normalized
    key = _lookup_token_key(normalized.upper())
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
