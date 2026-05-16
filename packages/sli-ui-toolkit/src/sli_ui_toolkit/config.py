from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

@dataclass(slots=True)
class FlyoutTimingConfig:
    transient_auto_hide_delay_ms: int = 180
    flyout_animation_duration_ms: int = 160
    text_settings_flyout_animation_duration_ms: int = 180

_timings = FlyoutTimingConfig()
_overlay_resolver: Callable[[object | None], object | None] | None = None
_rating_gesture_factory: Callable[..., object] | None = None
_dragdrop_service_getter: Callable[[], object | None] | None = None

def configure_toolkit(
    *,
    timings: FlyoutTimingConfig | None = None,
    overlay_resolver: Callable[[object | None], object | None] | None = None,
    rating_gesture_factory: Callable[..., object] | None = None,
    dragdrop_service_getter: Callable[[], object | None] | None = None,
) -> None:
    global _timings, _overlay_resolver, _rating_gesture_factory, _dragdrop_service_getter
    if timings is not None:
        _timings = timings
    if overlay_resolver is not None:
        _overlay_resolver = overlay_resolver
    if rating_gesture_factory is not None:
        _rating_gesture_factory = rating_gesture_factory
    if dragdrop_service_getter is not None:
        _dragdrop_service_getter = dragdrop_service_getter

def get_flyout_timings() -> FlyoutTimingConfig:
    return _timings

def resolve_overlay_layer(widget: object | None):
    if _overlay_resolver is None:
        return None
    try:
        return _overlay_resolver(widget)
    except Exception:
        return None

def create_rating_gesture(**kwargs):
    if _rating_gesture_factory is None:
        return None
    try:
        return _rating_gesture_factory(**kwargs)
    except Exception:
        return None

def get_dragdrop_service():
    if _dragdrop_service_getter is None:
        return None
    try:
        return _dragdrop_service_getter()
    except Exception:
        return None
