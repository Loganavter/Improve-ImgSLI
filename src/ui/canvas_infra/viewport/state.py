from __future__ import annotations

from dataclasses import dataclass

@dataclass(slots=True)
class ZoomViewportState:
    zoom_level: float = 1.0
    pan_offset_x: float = 0.0
    pan_offset_y: float = 0.0
    display_split_position: float = 0.5

def ensure_zoom_viewport_state(host) -> ZoomViewportState:
    runtime_state = getattr(host, "runtime_state", None)
    if runtime_state is not None:
        state = getattr(runtime_state, "_zoom_viewport_state", None)
        if state is None:
            state = ZoomViewportState()
            runtime_state._zoom_viewport_state = state
        if getattr(host, "zoom_level", None) is None:
            setattr(host, "zoom_level", state.zoom_level)
        if getattr(host, "pan_offset_x", None) is None:
            setattr(host, "pan_offset_x", state.pan_offset_x)
        if getattr(host, "pan_offset_y", None) is None:
            setattr(host, "pan_offset_y", state.pan_offset_y)
        if getattr(host, "display_split_position", None) is None:
            setattr(host, "display_split_position", state.display_split_position)
        return state

    state = getattr(host, "_zoom_viewport_state", None)
    if state is None:
        state = ZoomViewportState()
        setattr(host, "_zoom_viewport_state", state)
    if getattr(host, "zoom_level", None) is None:
        setattr(host, "zoom_level", state.zoom_level)
    if getattr(host, "pan_offset_x", None) is None:
        setattr(host, "pan_offset_x", state.pan_offset_x)
    if getattr(host, "pan_offset_y", None) is None:
        setattr(host, "pan_offset_y", state.pan_offset_y)
    if getattr(host, "display_split_position", None) is None:
        setattr(host, "display_split_position", state.display_split_position)
    return state

def get_zoom_level(host) -> float:
    return float(ensure_zoom_viewport_state(host).zoom_level)

def set_zoom_level(host, value: float) -> float:
    state = ensure_zoom_viewport_state(host)
    state.zoom_level = float(value)
    setattr(host, "zoom_level", state.zoom_level)
    return state.zoom_level

def get_pan_offset_x(host) -> float:
    return float(ensure_zoom_viewport_state(host).pan_offset_x)

def get_pan_offset_y(host) -> float:
    return float(ensure_zoom_viewport_state(host).pan_offset_y)

def set_pan_offsets(host, x: float, y: float) -> tuple[float, float]:
    state = ensure_zoom_viewport_state(host)
    state.pan_offset_x = float(x)
    state.pan_offset_y = float(y)
    setattr(host, "pan_offset_x", state.pan_offset_x)
    setattr(host, "pan_offset_y", state.pan_offset_y)
    return state.pan_offset_x, state.pan_offset_y

def get_display_split_position(host) -> float:
    return float(ensure_zoom_viewport_state(host).display_split_position)

def set_display_split_position(host, value: float) -> float:
    state = ensure_zoom_viewport_state(host)
    state.display_split_position = float(value)
    setattr(host, "display_split_position", state.display_split_position)
    return state.display_split_position
